import os
from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache

# 自动定位项目根目录的 .env 文件
# config.py 在 src/ 下 → 往上一级就是项目根目录
_THIS_DIR = Path(__file__).resolve().parent          # D:\dnd-rules-ai\src
_PROJECT_ROOT = _THIS_DIR.parent                      # D:\dnd-rules-ai
_ENV_FILE = _PROJECT_ROOT / ".env"

# 如果 .env 在当前目录也行
if not _ENV_FILE.exists() and (_THIS_DIR / ".env").exists():
    _ENV_FILE = _THIS_DIR / ".env"


class Settings(BaseSettings):
    # ── LLM 模式 ──────────────────────────────────────────────────────────
    # llm_mode="embedded" → 进程内 llama-cpp-python 加载 GGUF 模型（默认，无需外部服务）
    # llm_mode="api"      → 调用远程 OpenAI 兼容 API
    # llm_mode="local"    → 调用本地 Ollama / LM Studio（OpenAI 兼容接口）
    # llm_mode="auto"     → 启动时探测本地服务，可用则用 local，否则回退 api
    llm_mode: str = "embedded"

    # embedded 模式：进程内 GGUF 推理
    # 相对路径基于项目根目录；也可填绝对路径
    local_llm_model_path: str = "models/Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    local_llm_gpu_layers: int = -1    # -1 = 全部层放 GPU；0 = 纯 CPU
    local_llm_ctx_size: int = 8192    # 上下文窗口大小（tokens）；4096 太小放不下 RAG 内容

    # api / local / auto 模式
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"
    local_llm_url: str = "http://localhost:11434/v1"   # Ollama 默认地址
    local_llm_model: str = ""    # 空 = 自动选第一个可用模型

    # ── Embedding 模式 ────────────────────────────────────────────────────
    # embedding_mode="local" → 进程内 sentence-transformers（默认，无需外部服务）
    #                          GPU≥4GB 优先 bge-m3，否则 bge-small-zh-v1.5
    # embedding_mode="api"   → 强制 OpenAI 兼容 API
    # embedding_mode="auto"  → 优先本地，本地不可用时回退 API
    embedding_mode: str = "local"
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1024

    # DB
    sqlite_path: str = str(_THIS_DIR / "dnd_rules.db")
    database_type: str = "sqlite"   # "sqlite" | "mysql"

    # MySQL Database
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "dnd_rules_db"
    mysql_user: str = "root"
    mysql_password: str = ""

    # 地图图片生成
    map_generator: str = "pillow"          # "pillow" | "doubao" | "dalle" | "sdwebui"
    doubao_api_key: str = ""               # 火山引擎 ARK API Key
    doubao_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    doubao_image_model: str = "doubao-seedream-3-0-t2i-250415"  # 豆包文生图模型
    dalle_api_key: str = ""
    sdwebui_url: str = "http://127.0.0.1:7860"

    # D&D 资源文件根目录（import_monsters.py / import_htm_books.py 读取 HTM 源文件的位置）
    dnd5e_chm_dir: str = ""

    # Retrieval
    # top_k=4 是 RAG 实践甜点：足够覆盖常见问题，又不会超出小上下文窗口
    # API 模式上下文充足时可在请求中临时传 top_k=6 覆盖
    retrieval_top_k: int = 4
    max_cross_references: int = 2

    @property
    def effective_embedding_key(self) -> str:
        return self.embedding_api_key or self.openai_api_key

    @property
    def effective_embedding_base_url(self) -> str:
        return self.embedding_base_url or self.openai_base_url

    class Config:
        env_file = str(_ENV_FILE)          # ← 关键：用绝对路径
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()

    key_preview = settings.openai_api_key[:8] + "..." if len(settings.openai_api_key) > 8 else "(空!)"
    emb_key_preview = settings.effective_embedding_key[:8] + "..." if len(settings.effective_embedding_key) > 8 else "(空!)"

    import sys
    _out = sys.stdout
    def _p(s):
        try:
            print(s)
        except UnicodeEncodeError:
            print(s.encode('ascii', 'replace').decode('ascii'))

    _p(f"[Config] Loaded:")
    _p(f"   .env path:       {_ENV_FILE} ({'exists' if _ENV_FILE.exists() else 'missing!'})")
    _p(f"   LLM Mode:        {settings.llm_mode}")
    if settings.llm_mode == "embedded":
        _p(f"   GGUF Model Path: {settings.local_llm_model_path}")
        _p(f"   GPU Layers:      {settings.local_llm_gpu_layers} (-1=全部)")
        _p(f"   Context Size:    {settings.local_llm_ctx_size}")
    elif settings.llm_mode in ("local", "auto"):
        _p(f"   Local LLM URL:   {settings.local_llm_url}")
        _p(f"   Local LLM Model: {settings.local_llm_model or '(自动探测)'}")
    else:
        _p(f"   LLM Model:       {settings.llm_model}")
        _p(f"   LLM Base URL:    {settings.openai_base_url}")
        _p(f"   LLM API Key:     {key_preview}")
    _p(f"   Embed Mode:      {settings.embedding_mode}")
    if settings.embedding_mode != "local":
        _p(f"   Embed Model:     {settings.embedding_model}")
        _p(f"   Embed Base URL:  {settings.effective_embedding_base_url}")
        _p(f"   Embed API Key:   {emb_key_preview}")

    if settings.llm_mode in ("api", "auto") and not settings.openai_api_key:
        _p(f"\n[WARNING] LLM_MODE={settings.llm_mode} 但 OPENAI_API_KEY 为空！")
        _p(f"   Check .env file: {_ENV_FILE}")

    return settings