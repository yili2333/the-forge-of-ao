"""
本地模型效果测试

测试分四个阶段：

A. 本地嵌入模型（sentence-transformers）
   - 模型加载 & 维度确认
   - 语义相似度（同义 vs 无关）
   - 中英文跨语言检索能力
   - 批量嵌入速度基准

B. 本地 LLM 连通性探测
   - 自动探测 Ollama (localhost:11434) / LM Studio (localhost:1234)
   - 列出可用模型
   - 基础 ping（发一条最短的消息，确认能返回 token）

C. 端到端问答（本地 LLM × 知识库）
   - 与 test_import_quality.py 相同的 5 道测试题
   - 验证：答案包含必要关键词、不输出拒答套话、
           超出范围时给出合理 hedge
   - 反幻觉检测：系统提示里没有规则库的内容不能被编造出来
   - 延迟 & tokens/s 统计

D. 本地嵌入 + 本地 LLM 全链路（可选，加 --full-pipeline）
   - 用本地 embedding 重建向量索引 (in-memory, 不写 DB)
   - 用本地 LLM 生成回答
   - 对比同一问题在"全本地"和"默认配置"下的 Top-5 检索结果差异

用法：
    cd src

    # 仅测嵌入模型（不需要本地 LLM）
    python test_local_model.py

    # 自动探测本地 LLM 并跑问答
    python test_local_model.py --llm

    # 指定 Ollama 地址 + 模型名
    python test_local_model.py --llm --llm-url http://localhost:11434/v1 --llm-model qwen2.5:7b

    # 指定 LM Studio
    python test_local_model.py --llm --llm-url http://localhost:1234/v1 --llm-model local-model

    # 全链路（嵌入 + LLM 都用本地）
    python test_local_model.py --llm --full-pipeline --verbose
"""

from __future__ import annotations

import sys
import asyncio
import argparse
import time
import math
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

# ================================================================
#  计数器
# ================================================================

PASS_COUNT = 0
FAIL_COUNT = 0
SKIP_COUNT = 0


def ok(label: str, detail: str = "") -> None:
    global PASS_COUNT
    PASS_COUNT += 1
    suffix = f"  ({detail})" if detail else ""
    print(f"  ✅ {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    global FAIL_COUNT
    FAIL_COUNT += 1
    suffix = f"  ← {detail}" if detail else ""
    print(f"  ❌ {label}{suffix}")


def skip(label: str, reason: str = "") -> None:
    global SKIP_COUNT
    SKIP_COUNT += 1
    suffix = f"  ({reason})" if reason else ""
    print(f"  ⏭️  {label}{suffix}")


def check_true(label: str, value: bool, detail: str = "") -> None:
    if value:
        ok(label, detail)
    else:
        fail(label, detail)


def check_ge(label: str, actual: float, minimum: float, fmt: str = "") -> None:
    if actual >= minimum:
        ok(label, fmt or f"{actual:.4f} >= {minimum}")
    else:
        fail(label, f"{actual:.4f} < {minimum}")


def check_lt(label: str, actual: float, maximum: float, fmt: str = "") -> None:
    if actual < maximum:
        ok(label, fmt or f"{actual:.4f} < {maximum}")
    else:
        fail(label, f"{actual:.4f} >= {maximum}")


# ================================================================
#  A. 本地嵌入模型
# ================================================================

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def test_embedding_model(verbose: bool = False):
    print(f"\n{'─'*55}")
    print("  A. 本地嵌入模型（sentence-transformers）")
    print(f"{'─'*55}")

    # ── A1. 加载 ──
    print("\n  A1. 模型加载")
    try:
        from embedding_service import EmbeddingService
        svc = EmbeddingService()
    except Exception as e:
        fail("EmbeddingService 初始化", str(e))
        return None

    if svc.mode != "local":
        skip("本地模型加载", f"当前模式: {svc.mode}（未安装 sentence-transformers 或无模型）")
        skip("A2–A5 全部跳过", "需要本地模型")
        return svc

    model_name = getattr(svc, 'model_name', '?')
    dims = svc.dimensions
    ok("模型加载成功", f"{model_name}  维度={dims}")

    # ── A2. 维度检查 ──
    print("\n  A2. 嵌入维度")
    check_true("维度 > 0", dims > 0, str(dims))
    check_true("维度是 2 的幂次或常见值",
               dims in {128, 256, 384, 512, 768, 1024, 1536, 3072},
               str(dims))

    # ── A3. 语义相似度 ──
    print("\n  A3. 语义相似度验证")

    # 判断是否为多语言模型（bge-m3、multilingual-e5 等）
    is_multilingual = any(
        tag in model_name.lower()
        for tag in ["m3", "multilingual", "mte5", "labse", "paraphrase-multilingual"]
    )
    if is_multilingual:
        cross_lingual_threshold = 0.60
        print(f"      ℹ️  多语言模型 ({model_name})，跨语言阈值 = 0.60")
    else:
        # 纯中文模型（bge-small-zh 等）中英跨语言对齐能力有限：
        #   - 短词对（"偷袭" ↔ "Sneak Attack"）约 0.30~0.40
        #   - 完整短语对（"火球术" ↔ "Fireball"）约 0.45~0.60
        # 阈值设为 0.30，仅用于保底检测（模型完全没有跨语言能力时会低于此值）
        cross_lingual_threshold = 0.30
        print(f"      ⚠️  单语模型 ({model_name})，跨语言保底阈值 = 0.30")
        print(f"      已知局限：中英短词对相似度约 0.30~0.45，无法可靠检索英文条目")
        print(f"      建议：EMBEDDING_MODE=auto 且 GPU >=4GB 时会自动升级到 bge-m3（多语言）")

    sim_cases = [
        # (文本A, 文本B, 预期关系, 阈值, 描述)
        ("偷袭", "Sneak Attack",
         "high", cross_lingual_threshold, "中英同义"),
        ("火球术", "Fireball",
         "high", cross_lingual_threshold, "法术中英"),
        ("战士", "Fighter",
         "high", cross_lingual_threshold * 0.9, "职业中英"),
        # 中文同义 — 任何模型都应该高
        ("偷袭", "游荡者偷袭伤害",
         "high", 0.50, "中文同义"),
        # 无关对 — 阈值不随模型类型变化
        ("偷袭", "长休眠",
         "low",  0.55, "无关概念"),
        ("火球术伤害", "城镇地图生成器",
         "low",  0.50, "完全无关"),
    ]

    for text_a, text_b, relation, threshold, desc in sim_cases:
        try:
            emb_a = await svc.embed_text(text_a)
            emb_b = await svc.embed_text(text_b)
            sim = _cosine(emb_a, emb_b)
            if relation == "high":
                check_ge(f"[{desc}] 相似度 >= {threshold:.2f}",
                         sim, threshold, f"{sim:.4f}")
            else:
                check_lt(f"[{desc}] 相似度 < {threshold:.2f}",
                         sim, threshold, f"{sim:.4f}")
            if verbose:
                print(f"      cos({text_a!r}, {text_b!r}) = {sim:.4f}")
        except Exception as e:
            fail(f"[{desc}] 相似度计算失败", str(e))

    # ── A4. 中英跨语言 Top-1 命中 ──
    print("\n  A4. 中文问句 → 英文规则条目检索能力")

    cross_lingual_cases = [
        ("偷袭需要什么条件",
         ["Sneak Attack - PHB 2024", "Sneak Attack", "游荡者偷袭"]),
        ("火焰吐息伤害",
         ["Fire Breath", "Breath Weapon", "火焰吐息"]),
    ]

    for query, candidates in cross_lingual_cases:
        try:
            q_emb = await svc.embed_text(query)
            scored = []
            for c in candidates:
                c_emb = await svc.embed_text(c)
                scored.append((_cosine(q_emb, c_emb), c))
            scored.sort(reverse=True)
            best_score, best_cand = scored[0]
            check_ge(f"[{query}] 最高候选相似度 >= 0.45",
                     best_score, 0.45, f"{best_score:.4f} → {best_cand!r}")
        except Exception as e:
            fail(f"[{query}] 跨语言测试失败", str(e))

    # ── A5. 批量速度基准 ──
    print("\n  A5. 批量嵌入速度")

    texts_32 = [f"D&D 5e 规则测试文本 #{i}，包含一些常见规则词汇：攻击、豁免、法术、伤害" for i in range(32)]
    t0 = time.time()
    try:
        _ = await svc.embed_texts(texts_32)
        elapsed = time.time() - t0
        speed = 32 / elapsed
        check_ge("32 条批量速度 >= 5 条/秒", speed, 5.0,
                 f"{speed:.1f} 条/秒  ({elapsed:.2f}s 总计)")
    except Exception as e:
        fail("批量嵌入速度测试失败", str(e))

    return svc


# ================================================================
#  B. 本地 LLM 连通性探测
# ================================================================

class LocalLLMInfo(NamedTuple):
    url: str
    model: str
    backend: str   # "ollama" | "lmstudio" | "custom"


PROBE_ENDPOINTS = [
    ("http://localhost:11434/v1", "ollama"),
    ("http://localhost:1234/v1",  "lmstudio"),
    ("http://127.0.0.1:11434/v1", "ollama"),
    ("http://127.0.0.1:1234/v1",  "lmstudio"),
]


async def probe_local_llm(
    explicit_url: str | None = None,
    explicit_model: str | None = None,
) -> LocalLLMInfo | None:
    """
    探测本地 LLM 服务。
    优先使用命令行指定的 URL；否则逐一尝试已知端点。
    返回第一个成功的 LocalLLMInfo，找不到则返回 None。
    """
    try:
        from openai import AsyncOpenAI
        import httpx
    except ImportError:
        return None

    probes = (
        [(explicit_url, "custom")] if explicit_url
        else PROBE_ENDPOINTS
    )

    for url, backend in probes:
        try:
            client = AsyncOpenAI(
                api_key="local",   # Ollama / LM Studio 不验证 key
                base_url=url,
                timeout=5.0,
            )
            models_resp = await client.models.list()
            model_ids = [m.id for m in models_resp.data]
            if not model_ids:
                continue

            chosen = explicit_model or model_ids[0]
            # 如果指定模型不在列表里（LM Studio 返回的 id 可能是路径），放宽匹配
            if chosen not in model_ids:
                # 尝试模糊匹配
                match = next(
                    (mid for mid in model_ids
                     if chosen.lower() in mid.lower() or mid.lower() in chosen.lower()),
                    model_ids[0]
                )
                chosen = match

            return LocalLLMInfo(url=url, model=chosen, backend=backend)
        except Exception:
            continue

    return None


async def test_llm_connectivity(
    explicit_url: str | None = None,
    explicit_model: str | None = None,
    verbose: bool = False,
) -> LocalLLMInfo | None:
    print(f"\n{'─'*55}")
    print("  B. 本地 LLM 连通性探测")
    print(f"{'─'*55}")

    info = await probe_local_llm(explicit_url, explicit_model)

    if info is None:
        skip("本地 LLM 服务", "未发现 Ollama/LM Studio（或 openai 未安装）")
        skip("C、D 阶段跳过", "需要本地 LLM")
        return None

    ok(f"发现本地 LLM ({info.backend})", f"url={info.url}  model={info.model}")

    # 列出所有可用模型
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key="local", base_url=info.url, timeout=5.0)
        models_resp = await client.models.list()
        model_ids = [m.id for m in models_resp.data]
        ok(f"模型列表（{len(model_ids)} 个）",
           ", ".join(model_ids[:6]) + ("..." if len(model_ids) > 6 else ""))
    except Exception as e:
        fail("获取模型列表", str(e))

    # Ping：发一条最短消息
    print("\n  B-ping: 发送最短消息验证推理可用")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key="local", base_url=info.url, timeout=30.0)
        t0 = time.time()
        resp = await client.chat.completions.create(
            model=info.model,
            messages=[{"role": "user", "content": "说「ok」"}],
            max_tokens=10,
            temperature=0,
        )
        elapsed = time.time() - t0
        token_text = resp.choices[0].message.content or ""
        usage = resp.usage
        tps = (usage.completion_tokens / elapsed) if usage and elapsed > 0 else 0
        ok("Ping 成功",
           f"回复={token_text.strip()!r}  {elapsed:.2f}s  ~{tps:.1f} tok/s")
        if verbose:
            print(f"      usage: {usage}")
    except Exception as e:
        fail("Ping 失败", str(e))
        return None

    return info


# ================================================================
#  C. 端到端问答（本地 LLM × 知识库）
# ================================================================

# 与 test_import_quality.py 保持相同的测试用例，方便横向对比
QA_CASES = [
    {
        "question": "偷袭怎么用？需要什么条件？",
        "must_contain": ["偷袭", "优势", "灵巧"],
        "must_not_contain": ["我不知道", "无法回答"],
        "desc": "PHB 游荡者核心特性",
        "anti_hallucination_probe": None,
    },
    {
        "question": "成年红龙的挑战等级是多少，有什么特殊能力？",
        "must_contain": ["红龙", "17"],
        "must_not_contain": ["无法回答", "没有相关"],
        "desc": "MM2025 怪物属性",
        "anti_hallucination_probe": None,
    },
    {
        "question": "哥布林有什么特殊动作？",
        "must_contain": ["哥布林"],
        "must_not_contain": [],
        "desc": "MM2025 哥布林动作",
        "anti_hallucination_probe": None,
    },
    {
        "question": "魔法物品有哪些稀有度等级？",
        "must_contain": ["普通", "罕见"],
        "must_not_contain": ["不知道"],
        "desc": "DMG2024 魔法物品稀有度",
        "anti_hallucination_probe": None,
    },
    {
        "question": "请问2024年D&D的股票代码是多少？",
        "must_contain": [],
        "must_not_contain": [],
        "should_hedge": True,
        "desc": "超出范围问题（应坦诚不知道）",
        # 反幻觉探针：这串字符不应出现在规则库或 LLM 回答里
        "anti_hallucination_probe": "HASBRO:WOC",
    },
]

# 只测引用合规性，不依赖规则库内容
CITATION_PROBE = {
    "question": "长休可以恢复什么资源？",
    "expected_citation_patterns": ["PHB", "DMG", "MM", "📭 知识库未收录", "来源"],
    "desc": "来源引用格式合规性",
}


async def test_local_llm_qa(
    info: LocalLLMInfo,
    verbose: bool = False,
) -> None:
    print(f"\n{'─'*55}")
    print(f"  C. 端到端问答（{info.backend} / {info.model}）")
    print(f"{'─'*55}")

    # 初始化检索器
    try:
        import db as db_module
        from embedding_service import EmbeddingService
        from vector_store import VectorStore
        from keyword_store import KeywordStore
        from retriever import HybridRetriever

        await db_module.init_db()
        embedding_svc = EmbeddingService()
        vector_store = VectorStore()
        keyword_store = KeywordStore()
        retriever = HybridRetriever(vector_store, keyword_store, embedding_svc)

        existing = await db_module.get_all_chunks()
        if not existing:
            skip("C 阶段全部跳过", "知识库为空，请先导入规则书")
            return

        keyword_store.build_index(existing)
        print(f"  🔄 重建向量索引（{len(existing)} 条规则）...")
        texts = [f"{c.title}\n{c.content}" for c in existing]
        embeddings = await embedding_svc.embed_texts(texts)
        vector_store.upsert_chunks(existing, embeddings)
        print("  ✅ 向量索引就绪\n")

    except Exception as e:
        fail("检索器初始化失败", str(e))
        import traceback; traceback.print_exc()
        return

    # 初始化本地 LLM Generator（临时覆盖配置，不影响全局 settings）
    try:
        from openai import AsyncOpenAI
        from generator import RuleAnswerGenerator, SYSTEM_PROMPT
        from models import QueryResponse, SourceRef

        local_client = AsyncOpenAI(
            api_key="local",
            base_url=info.url,
            timeout=120.0,
        )
    except Exception as e:
        fail("本地 LLM 客户端初始化", str(e))
        return

    # 包一个临时生成函数，用本地 client 而非 settings 里的 API Key
    async def local_generate(question: str, chunks) -> tuple[str, float, int, int]:
        """返回 (answer, elapsed_sec, prompt_tokens, completion_tokens)"""
        from generator import RuleAnswerGenerator
        # 借用 _build_context（不实例化完整的 generator 以避免读取 settings key）
        gen = object.__new__(RuleAnswerGenerator)
        context = gen._build_context.__func__(gen, chunks)  # type: ignore[attr-defined]

        user_msg = (
            f"【知识库规则文本】（以下是从知识库检索到的全部相关规则，你只能使用这些内容作答）\n\n"
            f"{context}\n\n---\n\n"
            f"【用户问题】\n\n{question}\n\n"
            f"⚠️ 强制提醒：你必须且只能根据上方【知识库规则文本】中的内容作答。"
            f"若上方内容不足以回答此问题，输出\"📭 知识库未收录\"后停止。禁止使用训练数据补充。"
        )

        t0 = time.time()
        resp = await local_client.chat.completions.create(
            model=info.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=2000,
        )
        elapsed = time.time() - t0
        answer = resp.choices[0].message.content or ""
        usage = resp.usage
        p_tok = usage.prompt_tokens if usage else 0
        c_tok = usage.completion_tokens if usage else 0
        return answer, elapsed, p_tok, c_tok

    # ── C1. 功能性问答 ──
    print("  C1. 功能性问答（5 道题）\n")

    latencies: list[float] = []
    all_c_toks: list[int] = []

    for case in QA_CASES:
        q = case["question"]
        desc = case["desc"]
        print(f"  ❓ {q}")
        print(f"     ({desc})")

        try:
            chunks = await retriever.retrieve(q, top_k=5)
            if not chunks:
                skip(f"[{q[:25]}] 检索无结果", "跳过生成")
                continue

            answer, elapsed, p_tok, c_tok = await local_generate(q, chunks)
            latencies.append(elapsed)
            all_c_toks.append(c_tok)
            tps = c_tok / elapsed if elapsed > 0 else 0

            if verbose:
                print(f"\n     回答:\n     {answer[:600].replace(chr(10), chr(10)+'     ')}")
            else:
                preview = answer[:140].replace("\n", " ")
                print(f"     回答预览: {preview}...")

            print(f"     延迟: {elapsed:.2f}s  |  {p_tok}+{c_tok} tokens  |  ~{tps:.1f} tok/s")

            # 必须包含关键词
            for kw in case.get("must_contain", []):
                check_true(f"  回答含 '{kw}'", kw in answer,
                           f"未找到 '{kw}'")

            # 不能出现拒答套话
            for kw in case.get("must_not_contain", []):
                check_true(f"  回答不含拒答词 '{kw}'", kw not in answer,
                           f"意外出现了 '{kw}'")

            # 超出范围问题：hedge 检测
            if case.get("should_hedge"):
                hedge_words = ["无法", "不确定", "规则", "没有", "超出",
                               "不知道", "抱歉", "📭", "未收录"]
                has_hedge = any(w in answer for w in hedge_words)
                check_true("  超出范围时给出合适 hedge",
                           has_hedge or len(answer) < 150,
                           "可能出现了无依据的回答")

            # 反幻觉探针
            probe = case.get("anti_hallucination_probe")
            if probe:
                check_true(f"  反幻觉：回答不含编造内容 '{probe}'",
                           probe not in answer,
                           "LLM 编造了不存在于规则库的内容")

        except Exception as e:
            fail(f"[{q[:25]}] 生成失败", str(e))
            import traceback; traceback.print_exc()

        print()

    # ── C2. 来源引用格式合规性 ──
    print("  C2. 来源引用格式合规性")
    try:
        q = CITATION_PROBE["question"]
        chunks = await retriever.retrieve(q, top_k=5)
        if chunks:
            answer, elapsed, _, c_tok = await local_generate(q, chunks)
            patterns = CITATION_PROBE["expected_citation_patterns"]
            found = [p for p in patterns if p in answer]
            check_true(
                f"回答包含至少一种引用格式标志",
                len(found) >= 1,
                f"命中: {found}"
            )
            if verbose:
                print(f"\n     引用测试回答:\n     {answer[:400].replace(chr(10), chr(10)+'     ')}\n")
        else:
            skip("来源引用测试", "检索无结果")
    except Exception as e:
        fail("来源引用格式测试失败", str(e))

    # ── C3. 性能统计 ──
    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        avg_tps = (
            sum(all_c_toks) / sum(latencies)
            if sum(latencies) > 0 else 0
        )
        print(f"\n  C3. 性能统计")
        print(f"      平均延迟:  {avg_lat:.2f}s")
        print(f"      最大延迟:  {max_lat:.2f}s")
        print(f"      平均速度:  ~{avg_tps:.1f} tokens/s")

        # 宽松阈值：本地小模型 2 tok/s 已可接受
        check_ge("平均生成速度 >= 2 tok/s", avg_tps, 2.0,
                 f"{avg_tps:.1f} tok/s")


# ================================================================
#  D. 全链路：本地嵌入 + 本地 LLM（in-memory 向量库）
# ================================================================

async def test_full_local_pipeline(
    info: LocalLLMInfo,
    embed_svc,
    verbose: bool = False,
) -> None:
    print(f"\n{'─'*55}")
    print("  D. 全链路本地管道（本地 Embedding + 本地 LLM）")
    print(f"{'─'*55}")

    if embed_svc is None or embed_svc.mode != "local":
        skip("D 阶段跳过", "需要本地嵌入模型（sentence-transformers）")
        return

    try:
        import db as db_module
        from vector_store import VectorStore
        from keyword_store import KeywordStore
        from retriever import HybridRetriever

        await db_module.init_db()
        existing = await db_module.get_all_chunks()
        if not existing:
            skip("D 阶段跳过", "知识库为空")
            return

        # 用已初始化的本地 embed_svc（避免重复加载模型）
        vs = VectorStore()
        ks = KeywordStore()
        retriever = HybridRetriever(vs, ks, embed_svc)

        ks.build_index(existing)
        print(f"  🔄 全本地向量索引（{len(existing)} 条，使用 {embed_svc.model_name}）...")
        texts = [f"{c.title}\n{c.content}" for c in existing]
        embeddings = await embed_svc.embed_texts(texts)
        vs.upsert_chunks(existing, embeddings)
        print("  ✅ 全本地索引就绪\n")

        # 取一道代表性问题做对比
        probe_q = "偷袭怎么用？需要什么条件？"
        print(f"  对比查询: {probe_q!r}")

        chunks = await retriever.retrieve(probe_q, top_k=5)
        ok(f"全本地检索返回 {len(chunks)} 条规则块")
        if verbose:
            for c in chunks:
                tag = "🏠" if c.source.value == "Homebrew" else "📖"
                print(f"    {tag} [{c.score:.4f}] {c.title} ({c.source.value})")

        # 检查 Top-1 是否命中偷袭相关内容
        if chunks:
            top_text = chunks[0].title + " " + chunks[0].content
            hit = any(kw.lower() in top_text.lower()
                      for kw in ["偷袭", "Sneak Attack", "sneak"])
            check_true("全本地管道 Top-1 命中偷袭规则", hit,
                       f"Top-1={chunks[0].title!r}")

    except Exception as e:
        fail("全本地管道测试失败", str(e))
        import traceback; traceback.print_exc()


# ================================================================
#  主流程
# ================================================================

async def main() -> None:
    parser = argparse.ArgumentParser(
        description="D&D Rules AI — 本地模型效果测试"
    )
    parser.add_argument(
        "--llm", action="store_true",
        help="运行本地 LLM 连通性 + 问答测试（B、C 阶段）"
    )
    parser.add_argument(
        "--llm-url", default=None,
        help="本地 LLM 服务地址，如 http://localhost:11434/v1"
    )
    parser.add_argument(
        "--llm-model", default=None,
        help="本地模型名称，如 qwen2.5:7b 或 llama3.2"
    )
    parser.add_argument(
        "--full-pipeline", action="store_true",
        help="运行全链路测试（D 阶段，需要 --llm）"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="打印完整回答内容"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("  D&D Rules AI — 本地模型效果测试")
    print("=" * 60)

    # A. 嵌入模型
    embed_svc = await test_embedding_model(verbose=args.verbose)

    # B + C + D
    if args.llm:
        llm_info = await test_llm_connectivity(
            explicit_url=args.llm_url,
            explicit_model=args.llm_model,
            verbose=args.verbose,
        )
        if llm_info:
            await test_local_llm_qa(llm_info, verbose=args.verbose)

            if args.full_pipeline:
                await test_full_local_pipeline(
                    llm_info, embed_svc, verbose=args.verbose
                )
            else:
                print(f"\n  ℹ️  D 阶段跳过（加 --full-pipeline 启用全链路测试）")
    else:
        print(f"\n  ℹ️  B、C、D 阶段跳过（加 --llm 启用本地 LLM 测试）")

    # 汇总
    total = PASS_COUNT + FAIL_COUNT + SKIP_COUNT
    print(f"\n{'═'*60}")
    status = "✅ 全部通过" if FAIL_COUNT == 0 else f"❌ {FAIL_COUNT} 项失败"
    print(f"  {status}  |  通过 {PASS_COUNT}  失败 {FAIL_COUNT}  跳过 {SKIP_COUNT}  (共 {total})")
    print("═" * 60)

    if FAIL_COUNT > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
