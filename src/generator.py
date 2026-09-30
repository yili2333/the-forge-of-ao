from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from openai import AsyncOpenAI
from models import RuleChunk, QueryResponse, SourceRef
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  运行时 LLM 模式状态（不需要重启服务即可切换）
#
#  _runtime_mode:    当前生效模式，None = 跟随 settings.llm_mode
#  _local_model:     Ollama/local 模式的模型名（探测到或用户指定）
#  _local_available: 上次探测本地服务是否可达
#  _embedded_llm:    embedded 模式的 llama-cpp-python 实例（全局单例，懒加载）
# ──────────────────────────────────────────────────────────────
_runtime_mode: str | None = None
_local_model: str = ""
_local_available: bool | None = None
_embedded_llm = None          # llama_cpp.Llama 实例，首次调用时加载
_embedded_loading = False     # 防止并发重复加载


def get_active_mode() -> str:
    """返回当前生效的 LLM 模式（embedded / api / local）"""
    mode = _runtime_mode or settings.llm_mode
    if mode == "auto":
        return "local" if _local_available else "api"
    return mode


def set_runtime_mode(mode: str, local_model: str = "") -> None:
    """
    运行时切换 LLM 模式，不需要重启服务。
    mode: "embedded" | "api" | "local"
    """
    global _runtime_mode, _local_model
    if mode not in ("embedded", "api", "local"):
        raise ValueError(f"mode 必须是 'embedded' / 'api' / 'local'，收到: {mode!r}")
    _runtime_mode = mode
    if local_model:
        _local_model = local_model


# ── embedded 模式：llama-cpp-python 进程内推理 ────────────────

def _resolve_model_path() -> str:
    """将配置中的模型路径解析为绝对路径（相对路径基于项目根目录）。"""
    p = Path(settings.local_llm_model_path)
    if p.is_absolute():
        return str(p)
    # config.py 在 src/ 下，项目根 = src/ 的父目录
    project_root = Path(__file__).resolve().parent.parent
    return str(project_root / p)


def _load_embedded_llm():
    """
    加载 llama-cpp-python 模型（同步，首次调用时执行）。
    全局单例，进程内只加载一次。
    """
    global _embedded_llm, _embedded_loading
    if _embedded_llm is not None:
        return _embedded_llm

    if _embedded_loading:
        raise RuntimeError("模型正在加载中，请稍后重试")

    _embedded_loading = True
    try:
        from llama_cpp import Llama
    except ImportError:
        _embedded_loading = False
        raise RuntimeError(
            "LLM_MODE=embedded 但 llama-cpp-python 未安装。\n"
            "CPU 版：pip install llama-cpp-python\n"
            "GPU 版：CMAKE_ARGS=\"-DLLAMA_CUDA=on\" pip install llama-cpp-python --force-reinstall"
        )

    model_path = _resolve_model_path()
    if not Path(model_path).exists():
        _embedded_loading = False
        raise FileNotFoundError(
            f"GGUF 模型文件不存在: {model_path}\n"
            f"请将 Qwen2.5-7B-Instruct-Q4_K_M.gguf 放入项目 models/ 目录，\n"
            f"或在 .env 中修改 LOCAL_LLM_MODEL_PATH 指向正确路径。"
        )

    logger.info("[Generator] 加载内嵌 LLM: %s (gpu_layers=%d, ctx=%d)",
                model_path, settings.local_llm_gpu_layers, settings.local_llm_ctx_size)
    print(f"[Generator] 正在加载 GGUF 模型: {Path(model_path).name} ...")

    _embedded_llm = Llama(
        model_path=model_path,
        n_gpu_layers=settings.local_llm_gpu_layers,
        n_ctx=settings.local_llm_ctx_size,
        verbose=False,
    )
    _embedded_loading = False
    print(f"[Generator] ✅ 内嵌 LLM 加载完成")
    return _embedded_llm


async def _generate_embedded(messages: list[dict], max_tokens: int = 800) -> str:
    """在线程池中运行同步的 llama-cpp 推理，避免阻塞 asyncio 事件循环。"""
    def _sync():
        llm = _load_embedded_llm()
        output = llm.create_chat_completion(
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )
        return output["choices"][0]["message"]["content"]

    return await asyncio.to_thread(_sync)


# ── Ollama / 外部 API 模式 ────────────────────────────────────

async def probe_local_llm(url: str | None = None) -> tuple[bool, str, list[str]]:
    """
    探测本地 Ollama/LM Studio 服务是否可达。
    返回 (可达, 选中模型名, 所有模型列表)
    """
    global _local_available, _local_model
    target_url = url or settings.local_llm_url
    try:
        client = AsyncOpenAI(api_key="local", base_url=target_url, timeout=3.0)
        models_resp = await asyncio.wait_for(client.models.list(), timeout=3.0)
        model_ids = [m.id for m in models_resp.data]
        if not model_ids:
            _local_available = False
            return False, "", []
        preferred = _local_model or settings.local_llm_model
        chosen = preferred if preferred in model_ids else model_ids[0]
        _local_available = True
        _local_model = chosen
        return True, chosen, model_ids
    except Exception:
        _local_available = False
        return False, "", []


def _make_client(mode: str) -> tuple[AsyncOpenAI, str]:
    """创建 OpenAI 兼容客户端（local / api 模式用）。"""
    if mode == "local":
        return (
            AsyncOpenAI(api_key="local", base_url=settings.local_llm_url, timeout=120.0),
            _local_model or settings.local_llm_model or "unknown",
        )
    else:
        return (
            AsyncOpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url),
            settings.llm_model,
        )


SYSTEM_PROMPT = """你是一个专用于线上跑团平台的 D&D 5e 规则裁判助手。

════════════════════════════════════════
  !! 知识来源铁律（最高优先级，不可违反）!!
════════════════════════════════════════

你的唯一合法知识来源是：用户消息中"【知识库规则文本】"标签内提供的规则条目。

▶ 禁止事项（违反即为错误输出）：
  ✗ 禁止使用你训练数据中关于 D&D 的任何知识来补充、推断或替代知识库内容
  ✗ 禁止说"根据我的了解"、"一般来说"、"通常规则是"等暗示使用外部知识的表达
  ✗ 禁止在知识库未提及的情况下给出肯定性规则结论
  ✗ 禁止编造页码、来源名称或规则原文

▶ 知识库未覆盖时的强制行为：
  当检索到的条目中找不到问题的答案时，你必须回答：
  "📭 知识库未收录：当前检索到的规则文本中没有关于「[问题关键词]」的记载，
   无法给出基于规则的结论。建议 DM 自行裁定或查阅原书。"
  然后停止，不得追加任何基于推断的内容。

▶ 部分覆盖时：
  明确区分哪些内容来自知识库（可引用），哪些是知识库空白（不可回答）。

════════════════════════════════════════
  回答规范
════════════════════════════════════════

**来源标注**（每处引用必须标注）
  格式：[PHB 2024, p.XX] 或 [DMG 2024, p.XX] 或 [MM 2024] 或 [🏠 自定义规则]
  来源信息已包含在规则文本的元数据中，直接使用，不得伪造。

**版本区分**
  RAW（规则原文字面意思）vs RAI（设计意图/常见裁定）需明确标注。
  若知识库同时存在 2024 版与旧版规则，优先引用 2024 版，并注明差异。

**状态标记**
  ⚠️ 已被覆盖的旧版规则 → 仅作对比参考，不作为最终裁定依据
  🏠 自定义/Homebrew 规则 → 明确标注，不与官方规则混同

════════════════════════════════════════
  回答格式模板
════════════════════════════════════════

**📜 裁定结论**
[直接给出结论，仅基于知识库内容]

**📖 规则依据**
[逐条引用知识库原文，每条标注来源]

**💡 补充说明**（仅在知识库有相关内容时才写）
[边界情况、常见误解、相关联的其他规则]

**📋 引用来源**
[列出本次回答使用的所有规则条目]

如果知识库无内容可引用，直接输出"📭 知识库未收录"段落，省略其他所有节。"""


class RuleAnswerGenerator:
    def __init__(self):
        # 不在 __init__ 里固定 client，每次 generate 时按当前模式动态创建
        pass

    async def generate(
        self,
        question: str,
        chunks: list[RuleChunk],
        conversation_history: list[dict] | None = None,
    ) -> QueryResponse:

        context = self._build_context(chunks)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if conversation_history:
            messages.extend(conversation_history[-6:])

        user_message = f"""【知识库规则文本】（以下是从知识库检索到的全部相关规则，你只能使用这些内容作答）

{context}

---

【用户问题】

{question}

⚠️ 强制提醒：你必须且只能根据上方【知识库规则文本】中的内容作答。若上方内容不足以回答此问题，输出"📭 知识库未收录"后停止。禁止使用训练数据补充。"""

        messages.append({"role": "user", "content": user_message})

        # 按当前运行时模式动态选择推理后端
        mode = get_active_mode()

        max_out = self._max_output_tokens()

        if mode == "embedded":
            print(f"[Generator] 模式=embedded  模型={Path(settings.local_llm_model_path).name}  max_tokens={max_out}")
            answer = await _generate_embedded(messages, max_tokens=max_out)
        else:
            client, model_name = _make_client(mode)
            print(f"[Generator] 模式={mode}  模型={model_name}  max_tokens={max_out}")
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.1,
                max_tokens=max_out,
            )
            answer = response.choices[0].message.content

        sources = []
        seen = set()
        for chunk in chunks:
            key = (chunk.title, chunk.source.value)
            if key not in seen:
                seen.add(key)
                sources.append(SourceRef(
                    title=chunk.title,
                    source=chunk.source.value,
                    category=chunk.category.value,
                    is_homebrew=(chunk.source.value == "Homebrew"),
                    edition=getattr(chunk, 'edition', ''),
                    status=chunk.status,
                ))

        has_version_diff = any(
            c.is_overridden or c.status == "superseded"
            for c in chunks
        )

        version_note = ""
        if has_version_diff:
            editions = set()
            for c in chunks:
                if hasattr(c, 'edition') and c.edition:
                    editions.add(c.edition)
                editions.add(c.source.value)
            version_note = f"本回答涉及以下版本的规则: {', '.join(editions)}"

        confidence = self._estimate_confidence(question, chunks, answer)

        return QueryResponse(
            answer=answer,
            sources=sources,
            confidence=confidence,
            chunks_used=len(chunks),
            has_version_diff=has_version_diff,
            version_note=version_note,
        )

    # ── token 预算常量 ────────────────────────────────────────────
    # 粗估：1 个中文字符 ≈ 1.8 token
    _CHARS_PER_TOKEN = 1.8

    # 固定开销估算（system prompt + 用户问题包装 + 安全余量），单位 token
    _FIXED_OVERHEAD = 1200   # system ~800 + 用户包装 ~200 + 余量 ~200

    # 各模式最大输出 token 数（影响窗口消耗）
    _MAX_OUTPUT: dict[str, int] = {
        "embedded": 800,    # 本地小模型窗口紧，规则问答 800t 已足够
        "api":      2000,   # API 模式窗口大，允许更详细回答
        "local":    1200,   # Ollama 介于两者之间
    }

    # API 模式的固定 token 预算（API 模型窗口通常 ≥32K，直接设上限即可）
    _API_CHUNK_BUDGET = 28000

    def _max_output_tokens(self) -> int:
        """返回当前模式下的输出 token 上限。"""
        return self._MAX_OUTPUT.get(get_active_mode(), 2000)

    def _budget_chars(self) -> int:
        """
        按当前运行模式动态计算 chunk 内容的字符预算。

        embedded / local 模式：从 ctx_size 反推可用空间
            available = ctx_size - fixed_overhead - max_output
        api 模式：直接取保守上限，不依赖未知的 API ctx 大小
        """
        mode = get_active_mode()
        if mode == "api":
            return int(self._API_CHUNK_BUDGET * self._CHARS_PER_TOKEN)

        # embedded / local：从配置的上下文窗口动态计算
        ctx = settings.local_llm_ctx_size          # 默认 8192（已修改）
        max_out = self._MAX_OUTPUT.get(mode, 1200)
        available_tokens = max(ctx - self._FIXED_OVERHEAD - max_out, 512)
        return int(available_tokens * self._CHARS_PER_TOKEN)

    def _build_context(self, chunks: list[RuleChunk]) -> str:
        # ── 按预算裁剪 chunks（保留高分的，丢弃超出的）────────────
        budget = self._budget_chars()
        # 预留 metadata 开销（每块约 200 字符）
        meta_overhead = 200
        selected: list[RuleChunk] = []
        used_chars = 0
        dropped = 0
        for chunk in chunks:
            cost = len(chunk.content) + meta_overhead
            if used_chars + cost > budget and selected:
                # 已有至少 1 块且会超出预算 → 停止
                dropped += 1
                continue
            selected.append(chunk)
            used_chars += cost

        if dropped:
            print(f"[Generator] ⚠️  上下文预算裁剪：丢弃 {dropped} 个低分 chunk"
                  f"（已用 {used_chars} 字符 / 预算 {budget} 字符）")

        sections = []
        has_version_diff = False

        for i, chunk in enumerate(selected):
            source_tag = f"[{chunk.source.value}"
            if chunk.page:
                source_tag += f", p.{chunk.page}"
            source_tag += "]"

            markers = []
            if chunk.source.value == "Homebrew":
                markers.append("🏠 自定义规则")
            if chunk.is_overridden:
                markers.append("⚠️ 此规则已被更新版本覆盖")
                has_version_diff = True
            if chunk.status == "superseded":
                markers.append("📦 旧版本 (已被取代)")
                has_version_diff = True
            if chunk.errata_note:
                markers.append(f"📝 {chunk.errata_note}")
            if chunk.source.value == "Errata":
                markers.append("🔧 勘误更新")

            marker_str = "\n".join(markers)
            if marker_str:
                marker_str += "\n"

            edition_tag = ""
            if hasattr(chunk, 'edition') and chunk.edition:
                edition_tag = f" | **版本**: {chunk.edition}"

            sections.append(
                f"### 规则 {i + 1}: {chunk.title}\n"
                f"{marker_str}"
                f"**分类**: {chunk.category.value} | **来源**: {source_tag}{edition_tag}\n"
                f"**状态**: {chunk.status} | **上下文**: {chunk.parent_context or 'N/A'}\n\n"
                f"{chunk.content}\n"
            )

        context = "\n---\n".join(sections)

        if has_version_diff:
            header = (
                "注意: 以下规则中包含不同版本，请在回答中说明版本差异。\n"
                "已被覆盖或旧版本的规则仅供参考对比。\n"
                "请优先引用最新的生效版本。\n\n"
            )
            context = header + context

        return context

    def _estimate_confidence(
        self,
        question: str,
        chunks: list[RuleChunk],
        answer: str
    ) -> float:
        """简单的置信度估算"""
        score = 0.5

        # 检索到的结果数量
        if len(chunks) >= 3:
            score += 0.1
        if len(chunks) >= 1:
            score += 0.1

        # 最高检索分数
        max_score = max((c.score for c in chunks), default=0)
        if max_score > 0.5:
            score += 0.15

        # 回答中的不确定信号
        uncertain = ["不确定", "可能", "大概", "我认为", "不太清楚",
                      "无法确认", "not sure", "probably", "might"]
        for word in uncertain:
            if word in answer:
                score -= 0.15
                break

        # 回答中有引用信号
        if "[PHB" in answer or "[DMG" in answer or "规则" in answer:
            score += 0.1

        return max(0.1, min(1.0, round(score, 2)))