"""
导入质量测试 —— 验证三本规则书导入后的检索与问答表现

覆盖三类测试：

A. 数据完整性
   - 数据库规则总数
   - 三本书来源分布
   - 乱码检测

B. 检索质量（Retrieval）
   - 精确名称查询：能取回目标 chunk
   - 语义查询：中文问句能取回正确的英/中内容
   - 跨书查询：一次检索能跨来源召回
   - 类别正确性：法术问题 → 法术 chunk 排在前面
   - 怪物属性查询：成年红龙能取回 AC/HP/CR

C. 端到端问答（LLM，真实 API 调用）
   - 简单规则问题（答案在 PHB2024）
   - 怪物问题（答案在 MM2025）
   - 装备问题（答案在 DMG2024）
   - 多来源综合问题
   - 消极测试：问题超出规则库，AI 应坦诚不知道

用法:
    cd src
    python test_import_quality.py              # 快速模式（跳过 LLM 调用）
    python test_import_quality.py --llm        # 含 LLM 问答测试（会消耗 API）
    python test_import_quality.py --llm --verbose  # 打印完整回答
"""

from __future__ import annotations

import sys
import asyncio
import argparse
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

import db
from embedding_service import EmbeddingService
from vector_store import VectorStore
from keyword_store import KeywordStore
from retriever import HybridRetriever
from generator import RuleAnswerGenerator
from models import RuleSource, RuleCategory


# ================================================================
#  辅助
# ================================================================

class TestFailure(Exception):
    pass


PASS_COUNT = 0
FAIL_COUNT = 0


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


def check(label: str, actual, expected, detail: str = "") -> None:
    if actual == expected:
        ok(label, str(actual) if not detail else detail)
    else:
        fail(label, f"期望 {expected!r}，实际 {actual!r}")


def check_ge(label: str, actual: int, minimum: int) -> None:
    if actual >= minimum:
        ok(label, f"{actual} >= {minimum}")
    else:
        fail(label, f"{actual} < {minimum}")


def check_true(label: str, value: bool, detail: str = "") -> None:
    if value:
        ok(label, detail)
    else:
        fail(label, detail)


# ================================================================
#  A. 数据完整性
# ================================================================

async def test_data_integrity():
    print(f"\n{'─'*50}")
    print("  A. 数据完整性")
    print(f"{'─'*50}")

    chunks = await db.get_all_chunks()
    total = len(chunks)
    check_ge("总规则数 >= 2800", total, 2800)

    by_source = Counter(c.source.value for c in chunks)
    print(f"\n  来源分布:")
    for src, cnt in by_source.most_common():
        print(f"    {src:30s}  {cnt}")

    # 三本书均在
    check_ge("怪物图鉴 MM 2025 规则 >= 600",
             by_source.get("MM 2024", 0), 600)
    check_ge("玩家手册 PHB 2024 规则 >= 700",
             by_source.get("PHB 2024", 0), 700)
    check_ge("城主指南 DMG 2024 规则 >= 600",
             by_source.get("DMG 2024", 0), 600)

    # 乱码检测：标题或内容含大量替换字符
    garbled = [c for c in chunks if c.title.count("\ufffd") + c.content.count("\ufffd") > 3]
    check("乱码 chunk 数为 0", len(garbled), 0, f"发现 {len(garbled)} 个" if garbled else "")

    # 内容非空（允许 <= 2 个空 chunk，因为书籍封面/目录页可能没有正文）
    empty_content = [c for c in chunks if not c.content.strip()]
    check_true("空内容 chunk 极少 (<= 2)",
               len(empty_content) <= 2,
               f"有 {len(empty_content)} 个空 chunk" if empty_content else "")

    # 各书应有法术/怪物/装备
    mm_chunks = [c for c in chunks if c.source == RuleSource.MM_2024]
    phb_chunks = [c for c in chunks if c.source == RuleSource.PHB_2024]
    dmg_chunks = [c for c in chunks if c.source == RuleSource.DMG_2024]

    check_ge("MM: 战斗类 chunk >= 100",
             sum(1 for c in mm_chunks if c.category == RuleCategory.COMBAT), 100)
    check_ge("PHB: 法术类 chunk >= 50",
             sum(1 for c in phb_chunks if c.category == RuleCategory.SPELL), 50)
    check_ge("DMG: 装备类 chunk >= 30",
             sum(1 for c in dmg_chunks if c.category == RuleCategory.EQUIPMENT), 30)

    return chunks


# ================================================================
#  B. 检索质量
# ================================================================

async def test_retrieval_quality(retriever: HybridRetriever, verbose: bool = False):
    print(f"\n{'─'*50}")
    print("  B. 检索质量")
    print(f"{'─'*50}")

    # ---- 精确名称查询 ----
    print("\n  B1. 精确名称查询")

    cases_exact = [
        ("火球术",      ["火球", "Fireball"],       RuleSource.PHB_2024),
        ("成年红龙",    ["红龙", "Red Dragon"],      RuleSource.MM_2024),
        ("偷袭",        ["偷袭", "Sneak Attack"],    RuleSource.PHB_2024),
        ("魔法飞弹",    ["魔法飞弹", "Magic Missile"], RuleSource.PHB_2024),
        ("致盲斩",      ["致盲斩", "Blinding Smite"], RuleSource.PHB_2024),
    ]

    for query, keywords, expected_source in cases_exact:
        t0 = time.time()
        results = await retriever.retrieve(query, top_k=5)
        elapsed = time.time() - t0

        if not results:
            fail(f"  [{query}] 无结果", f"耗时 {elapsed:.2f}s")
            continue

        top = results[0]
        hit = any(kw.lower() in (top.title + top.content).lower() for kw in keywords)
        src_ok = any(r.source == expected_source for r in results[:3])

        check_true(f"[{query}] Top-1 命中关键词",
                   hit, f"Top-1标题={top.title!r}")
        check_true(f"[{query}] 前3含正确来源",
                   src_ok, f"来源={[r.source.value for r in results[:3]]}")
        if verbose:
            print(f"      Top-1: {top.title!r} [{top.source.value}] (score={top.score:.3f})")

    # ---- 语义查询（中文问句） ----
    print("\n  B2. 语义查询（自然语言问句）")

    cases_semantic = [
        ("偷袭需要什么条件",    ["偷袭", "Sneak", "灵巧", "优势"]),
        ("狂暴状态有什么效果",  ["狂暴", "Rage", "伤害", "野蛮人"]),
        ("魔法物品分哪些稀有度", ["普通", "罕见", "稀有", "传说", "Rarity"]),
        ("红龙的火焰吐息有多强",  ["火焰", "吐息", "红龙", "DC"]),
        ("集中法术怎么打断",    ["集中", "Concentration", "专注", "伤害"]),
    ]

    for query, any_keywords in cases_semantic:
        results = await retriever.retrieve(query, top_k=5)
        if not results:
            fail(f"[{query}] 无结果")
            continue

        combined_text = " ".join(r.title + " " + r.content for r in results)
        matched = [kw for kw in any_keywords if kw.lower() in combined_text.lower()]
        check_true(
            f"[{query}] 至少命中 2 个关键词",
            len(matched) >= 2,
            f"命中 {matched}"
        )

    # ---- 怪物属性查询 ----
    print("\n  B3. 怪物属性查询")

    monster_cases = [
        ("成年红龙的AC", ["AC", "19", "护甲"]),
        ("哥布林的生命值", ["HP", "10", "哥布林", "Goblin"]),
        ("龙龟的挑战等级", ["龙龟", "CR", "挑战"]),
    ]

    for query, any_keywords in monster_cases:
        results = await retriever.retrieve(query, top_k=5)
        combined = " ".join(r.content for r in results)
        matched = [kw for kw in any_keywords if kw in combined]
        check_true(
            f"[{query}] 属性值命中",
            len(matched) >= 1,
            f"命中: {matched}"
        )

    # ---- 类别检索质量 ----
    print("\n  B4. 类别相关性（法术检索）")

    spell_queries = ["火球术详细规则", "治愈术", "秘法飞弹 magic missile"]
    for q in spell_queries:
        results = await retriever.retrieve(q, top_k=5)
        spell_count = sum(1 for r in results if r.category == RuleCategory.SPELL)
        check_true(
            f"[{q}] 前5含 >= 1 个 SPELL 类别 chunk",
            spell_count >= 1,
            f"法术chunk={spell_count}/5"
        )

    # ---- 跨来源查询 ----
    print("\n  B5. 跨书来源覆盖")

    cross_query = "战士战斗风格和魔法护甲"
    results = await retriever.retrieve(cross_query, top_k=10)
    sources = {r.source for r in results}
    check_true(
        f"[{cross_query}] 召回来自 >= 2 个来源",
        len(sources) >= 2,
        f"来源: {[s.value for s in sources]}"
    )

    # ---- 空查询健壮性 ----
    print("\n  B6. 边界情况")

    edge_cases = [
        "哈哈哈哈啦啦啦",   # 无意义
        "a",                # 极短
        "D&D 5e 2024 版核心规则概述",  # 宽泛
    ]
    for q in edge_cases:
        try:
            results = await retriever.retrieve(q, top_k=3)
            check_true(f"[{q!r}] 不崩溃", True, f"返回 {len(results)} 条")
        except Exception as e:
            fail(f"[{q!r}] 崩溃", str(e))


# ================================================================
#  C. 端到端问答（LLM）
# ================================================================

async def test_llm_qa(retriever: HybridRetriever,
                      generator: RuleAnswerGenerator,
                      verbose: bool = False):
    print(f"\n{'─'*50}")
    print("  C. 端到端问答（LLM）")
    print(f"{'─'*50}")

    cases = [
        {
            "question": "偷袭怎么用？需要什么条件？",
            "must_contain": ["偷袭", "优势", "灵巧"],
            "must_not_contain": ["我不知道", "无法回答"],
            "desc": "PHB 游荡者核心特性",
        },
        {
            "question": "成年红龙的挑战等级是多少，有什么特殊能力？",
            "must_contain": ["红龙", "17"],
            "must_not_contain": ["无法回答", "没有相关"],
            "desc": "MM2025 怪物属性",
        },
        {
            "question": "哥布林有什么特殊动作？",
            "must_contain": ["哥布林", "敏捷逃脱"],
            "must_not_contain": [],
            "desc": "MM2025 哥布林",
        },
        {
            "question": "魔法物品有哪些稀有度等级？",
            "must_contain": ["普通", "罕见"],
            "must_not_contain": ["不知道"],
            "desc": "DMG2024 魔法物品",
        },
        {
            "question": "请问2024年D&D的股票代码是多少？",
            "must_contain": [],
            "must_not_contain": [],
            "should_hedge": True,
            "desc": "超出范围问题（应坦诚不知道）",
        },
    ]

    for case in cases:
        q = case["question"]
        print(f"\n  ❓ {q}")
        print(f"     ({case['desc']})")

        t0 = time.time()
        try:
            chunks = await retriever.retrieve(q, top_k=5)
            if not chunks:
                print("     ⚠️  检索无结果，跳过生成")
                continue

            response = await generator.generate(
                question=q,
                chunks=chunks,
                conversation_history=[],
            )
            answer = response.answer
            elapsed = time.time() - t0

            if verbose:
                print(f"\n     回答:\n     {answer[:500].replace(chr(10), chr(10)+'     ')}")
                print(f"\n     来源: {[s.title for s in response.sources[:3]]}")
            else:
                preview = answer[:120].replace("\n", " ")
                print(f"     回答预览: {preview}...")

            print(f"     耗时: {elapsed:.2f}s  chunks_used: {response.chunks_used}")

            # 验证
            for kw in case.get("must_contain", []):
                check_true(
                    f"  回答含 '{kw}'",
                    kw in answer,
                    f"实际未找到 '{kw}'"
                )

            for kw in case.get("must_not_contain", []):
                check_true(
                    f"  回答不含拒答词 '{kw}'",
                    kw not in answer,
                    f"意外出现了 '{kw}'"
                )

            # 超出范围问题：验证 AI 没有瞎编
            if case.get("should_hedge"):
                hedge_words = ["无法", "不确定", "规则", "没有", "超出", "不知道", "抱歉"]
                has_hedge = any(w in answer for w in hedge_words)
                check_true(
                    "  超出范围时 AI 给出了合适回应",
                    has_hedge or len(answer) < 100,
                    "AI 可能给出了无根据的回答"
                )

        except Exception as e:
            fail(f"  [{q[:30]}] 生成失败", str(e))
            import traceback
            traceback.print_exc()


# ================================================================
#  主流程
# ================================================================

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--llm", action="store_true", help="运行 LLM 端到端测试（消耗 API）")
    parser.add_argument("--verbose", action="store_true", help="打印完整回答")
    args = parser.parse_args()

    print("=" * 60)
    print("  导入质量测试 — D&D 规则书三册")
    print("=" * 60)

    await db.init_db()

    # 初始化服务
    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    keyword_store = KeywordStore()
    retriever = HybridRetriever(vector_store, keyword_store, embedding_service)

    existing = await db.get_all_chunks()
    keyword_store.build_index(existing)

    # 将规则嵌入并加载到向量库（使用缓存，速度快）
    print(f"\n  🔄 重建向量索引（{len(existing)} 条规则）...")
    texts = [f"{c.title}\n{c.content}" for c in existing]
    embeddings = await embedding_service.embed_texts(texts)
    vector_store.upsert_chunks(existing, embeddings)
    print(f"  ✅ 向量索引就绪")

    # A. 数据完整性
    await test_data_integrity()

    # B. 检索质量
    await test_retrieval_quality(retriever, verbose=args.verbose)

    # C. LLM 问答（可选）
    if args.llm:
        generator = RuleAnswerGenerator()
        await test_llm_qa(retriever, generator, verbose=args.verbose)
    else:
        print(f"\n  ℹ️  跳过 LLM 测试（用 --llm 启用）")

    # 汇总
    print(f"\n{'='*60}")
    total = PASS_COUNT + FAIL_COUNT
    if FAIL_COUNT == 0:
        print(f"  [PASS] 全部 {total} 项测试通过 ✓")
    else:
        print(f"  [FAIL] {FAIL_COUNT}/{total} 项失败，{PASS_COUNT} 项通过")
    print("=" * 60)

    if FAIL_COUNT > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
