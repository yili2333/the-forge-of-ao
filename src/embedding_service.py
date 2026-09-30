"""
嵌入服务 — 修复版
解决:
1. bge-m3 太大，CPU 跑不动 → 自动选择合适的模型
2. 没有进度反馈 → 加入逐条进度
3. 批量处理卡死 → 小批次 + 超时保护
"""

import hashlib
import json
import os
import time
import sys
from pathlib import Path
from config import get_settings

# 修复 Windows 控制台中文输出乱码（cp936 → utf-8）
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

settings = get_settings()

# 项目根目录 & 缓存/模型目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CACHE_DIR = str(_PROJECT_ROOT / ".embedding_cache")
_LOCAL_MODELS_DIR = _PROJECT_ROOT / "models"


class EmbeddingService:
    def __init__(self):
        os.makedirs(_CACHE_DIR, exist_ok=True)
        self.cache_dir = _CACHE_DIR

        self.mode = "local"
        self.dimensions = 384  # 默认值，会被实际模型覆盖
        self.local_model = None
        self.api_client = None

        mode_pref = settings.embedding_mode  # "auto" | "local" | "api"

        if mode_pref == "api":
            print("📡 嵌入模式: API（由 EMBEDDING_MODE=api 指定）")
            self.mode = "api"
            self._init_api_client()
        elif mode_pref == "local":
            print("🖥️  嵌入模式: 本地（由 EMBEDDING_MODE=local 指定）")
            self._init_local_model(force=True)
        else:
            # "auto"：优先本地，不可用时回退 API
            print("🔍 嵌入模式: auto（优先本地，回退 API）")
            self._init_local_model(force=False)

    def _init_local_model(self, force: bool = False):
        """
        初始化本地嵌入模型，自动选择合适大小。
        force=True：未安装 sentence-transformers 时直接抛出异常（EMBEDDING_MODE=local）。
        force=False：未安装时静默回退到 API 模式（EMBEDDING_MODE=auto）。
        """
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except ImportError:
            if force:
                raise RuntimeError(
                    "EMBEDDING_MODE=local 但 sentence-transformers 未安装。\n"
                    "请执行: pip install sentence-transformers torch\n"
                    "或将 .env 中 EMBEDDING_MODE 改为 api 或 auto"
                )
            print("⚠️  sentence-transformers 未安装，回退到 API 模式")
            print("   提示：执行 pip install sentence-transformers torch 可启用本地嵌入")
            self.mode = "api"
            self._init_api_client()
            return

        # 检测硬件
        import torch
        has_cuda = torch.cuda.is_available()
        device = "cuda" if has_cuda else "cpu"

        if has_cuda:
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            gpu_mem = getattr(props, 'total_memory', getattr(props, 'total_mem', 0)) / 1024 ** 3
            print(f"🖥️  检测到 GPU: {gpu_name} ({gpu_mem:.1f}GB)")
        else:
            print("🖥️  未检测到 GPU，使用 CPU 模式")

        # 根据硬件选择模型
        # 项目内置模型目录：models/BAAI--bge-m3 和 models/BAAI--bge-small-zh-v1.5
        # GPU≥4GB → bge-m3（高质量多语言）；其余 → bge-small-zh-v1.5（CPU 友好）
        if has_cuda and gpu_mem >= 4:
            models_by_priority = [
                ("BAAI/bge-m3", "多语言大模型，最佳质量"),
                ("BAAI/bge-small-zh-v1.5", "中文小模型，备选"),
            ]
        else:
            models_by_priority = [
                ("BAAI/bge-small-zh-v1.5", "中文小模型(93MB)，CPU友好"),
                ("BAAI/bge-m3", "多语言大模型(2GB)，CPU较慢⚠️"),
            ]

        for model_name, desc in models_by_priority:
            try:
                # 优先从项目内 models/ 目录加载（离线打包场景）
                local_path = _LOCAL_MODELS_DIR / model_name.replace("/", "--")
                if local_path.exists():
                    print(f"📦 从本地加载: {local_path.name} ({desc})...")
                    self.local_model = SentenceTransformer(
                        str(local_path), device=device
                    )
                else:
                    print(f"📦 在线加载: {model_name} ({desc})...")
                    self.local_model = SentenceTransformer(
                        model_name, device=device
                    )

                self.dimensions = self.local_model.get_sentence_embedding_dimension()
                self.model_name = model_name
                print(f"✅ 加载成功: {model_name} (维度: {self.dimensions}, 设备: {device})")
                return
            except Exception as e:
                print(f"   ❌ 加载失败: {e}")
                continue

        if force:
            raise RuntimeError(
                "EMBEDDING_MODE=local 但所有本地模型加载失败。\n"
                "请检查 models/ 目录或网络连接，或将 EMBEDDING_MODE 改为 api"
            )
        print("⚠️  所有本地模型加载失败，回退到 API 模式")
        self.mode = "api"
        self._init_api_client()

    def _init_api_client(self):
        """API 模式"""
        from openai import AsyncOpenAI

        api_key = settings.effective_embedding_key
        base_url = settings.effective_embedding_base_url

        if not api_key:
            raise ValueError(
                "无法加载本地模型且 API Key 为空！\n"
                "请: pip install sentence-transformers\n"
                "或设置 OPENAI_API_KEY"
            )

        self.api_client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.api_model = settings.embedding_model
        self.dimensions = settings.embedding_dimensions
        self.mode = "api"
        print(f"📡 使用 API 嵌入: {self.api_model}")

    async def embed_text(self, text: str) -> list[float]:
        """嵌入单条文本"""
        cache_key = self._cache_key(text)
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        if self.mode == "local":
            embedding = self._local_embed_single(text)
        else:
            embedding = await self._api_embed_single(text)

        self._save_cache(cache_key, embedding)
        return embedding

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """
        批量嵌入 — 带进度显示和缓存
        """
        if not texts:
            return []

        results = [None] * len(texts)
        uncached_indices = []
        uncached_texts = []

        # 1. 检查缓存
        for i, text in enumerate(texts):
            cache_key = self._cache_key(text)
            cached = self._load_cache(cache_key)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        cached_count = len(texts) - len(uncached_texts)

        if uncached_texts:
            print(f"   📊 嵌入任务: {len(uncached_texts)} 条待计算, {cached_count} 条已缓存")

            if self.mode == "local":
                embeddings = self._local_embed_batch(uncached_texts)
            else:
                embeddings = await self._api_embed_batch(uncached_texts)

            for j, emb in enumerate(embeddings):
                idx = uncached_indices[j]
                results[idx] = emb
                self._save_cache(self._cache_key(uncached_texts[j]), emb)
        else:
            print(f"   💾 全部命中缓存 ({cached_count} 条)")

        return results

    # ===== 本地模型嵌入 =====

    def _local_embed_single(self, text: str) -> list[float]:
        emb = self.local_model.encode(
            text, normalize_embeddings=True
        )
        return emb.tolist()

    def _local_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量本地嵌入，带进度显示"""
        all_embeddings = []
        batch_size = 16  # 小批次，避免内存爆炸
        total = len(texts)

        start_time = time.time()

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            embs = self.local_model.encode(
                batch,
                normalize_embeddings=True,
                show_progress_bar=False,
                batch_size=batch_size,
            )

            for emb in embs:
                all_embeddings.append(emb.tolist())

            # 进度显示
            done = min(i + batch_size, total)
            elapsed = time.time() - start_time
            speed = done / elapsed if elapsed > 0 else 0
            eta = (total - done) / speed if speed > 0 else 0

            # \r 覆盖同一行
            progress_bar = self._make_progress_bar(done, total)
            sys.stdout.write(
                f"\r   {progress_bar} {done}/{total} "
                f"({speed:.1f} 条/秒, 剩余 {eta:.0f}秒)"
            )
            sys.stdout.flush()

        print()  # 换行
        elapsed = time.time() - start_time
        print(f"   ✅ 嵌入完成: {total} 条, 耗时 {elapsed:.1f}秒")

        return all_embeddings

    def _make_progress_bar(self, current: int, total: int, width: int = 30) -> str:
        """生成进度条字符串"""
        if total == 0:
            return "[" + "=" * width + "]"
        ratio = current / total
        filled = int(width * ratio)
        bar = "█" * filled + "░" * (width - filled)
        percent = ratio * 100
        return f"[{bar}] {percent:.0f}%"

    # ===== API 嵌入 =====

    async def _api_embed_single(self, text: str) -> list[float]:
        response = await self.api_client.embeddings.create(
            model=self.api_model, input=text
        )
        return response.data[0].embedding

    async def _api_embed_batch(self, texts: list[str]) -> list[list[float]]:
        all_embeddings = []
        batch_size = 100
        total = len(texts)

        for i in range(0, total, batch_size):
            batch = texts[i:i + batch_size]
            response = await self.api_client.embeddings.create(
                model=self.api_model, input=batch
            )
            sorted_data = sorted(response.data, key=lambda x: x.index)
            all_embeddings.extend([d.embedding for d in sorted_data])

            done = min(i + batch_size, total)
            print(f"   📡 API 嵌入: {done}/{total}")

        return all_embeddings

    # ===== 缓存 =====

    def _cache_key(self, text: str) -> str:
        model_tag = getattr(self, 'model_name', 'unknown') if self.mode == "local" else getattr(self, 'api_model', 'api')
        h = hashlib.md5(f"{model_tag}:{text}".encode()).hexdigest()
        return h

    def _load_cache(self, key: str) -> list[float] | None:
        path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
        return None

    def _save_cache(self, key: str, embedding: list[float]):
        path = os.path.join(self.cache_dir, f"{key}.json")
        try:
            with open(path, 'w') as f:
                json.dump(embedding, f)
        except IOError:
            pass