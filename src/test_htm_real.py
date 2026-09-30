"""
真实数据导入测试：DND5e_chm-main 三本规则书

测试目标:
  - 编码自动检测（GBK/GB2312 中文规则书）
  - 章节切分与标题层级
  - 法术、怪物、装备等类别自动识别
  - 长文本分块
  - 关键词提取
  - 三本书合并后的规模统计

用法:
  cd src
  python test_htm_real.py            # 快速模式（每本抽 20 文件）
  python test_htm_real.py --full     # 全量（1124 个文件）
"""

from __future__ import annotations

import sys
import time
import argparse
import traceback
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))

from htm_processor import HTMProcessor, HTMProcessConfig
from models import RuleCategory, RuleSource

# ================================================================
#  路径
# ================================================================

BASE = Path(__file__).parent.parent / "DND5e_chm-main"
BOOKS = {
    "怪物图鉴2025": {
        "path": BASE / "怪物图鉴2025",
        "source": RuleSource.MM_2024,
        "edition": "MM 2025",
        "source_name": "怪物图鉴 2025",
    },
    "玩家手册2024": {
        "path": BASE / "玩家手册2024",
        "source": RuleSource.PHB_2024,
        "edition": "PHB 2024",
        "source_name": "玩家手册 2024",
    },
    "城主指南2024": {
        "path": BASE / "城主指南2024",
        "source": RuleSource.DMG_2024,
        "edition": "DMG 2024",
        "source_name": "城主指南 2024",
    },
}


# ================================================================
#  辅助
# ================================================================

class TestFailure(Exception):
    pass


def check(label: str, actual, expected) -> None:
    if actual != expected:
        raise TestFailure(f"[{label}] 期望 {expected!r}，实际 {actual!r}")


def check_true(label: str, value: bool) -> None:
    if not value:
        raise TestFailure(f"[{label}] 期望 True，实际 False")


def check_ge(label: str, actual: int, minimum: int) -> None:
    if actual < minimum:
        raise TestFailure(f"[{label}] 期望 >= {minimum}，实际 {actual}")


# ================================================================
#  按书逐一测试
# ================================================================

def test_book(name: str, meta: dict, max_files: int = 0) -> dict:
    """
    处理单本书并返回统计信息。
    max_files=0 表示全量处理。
    """
    print(f"\n{'='*60}")
    print(f"  📖 {name}  ({meta['edition']})")
    print(f"  路径: {meta['path']}")
    print(f"{'='*60}")

    path = Path(meta["path"])
    if not path.exists():
        raise TestFailure(f"路径不存在: {path}")

    cfg = HTMProcessConfig(
        source_name=meta["source_name"],
        source_enum=meta["source"],
        edition=meta["edition"],
        split_at_levels=[1, 2, 3],
        max_chunk_chars=2500,
        min_chunk_chars=60,
    )

    t0 = time.time()
    chunks, errors = HTMProcessor.process_directory(path, cfg, max_files=max_files)
    elapsed = time.time() - t0

    # ---------- 基础断言 ----------
    check_true(f"{name}: 有 chunk 产出", len(chunks) > 0)
    check_true(f"{name}: 错误数合理", len(errors) == 0 or len(errors) / max(1, len(chunks)) < 0.1)

    # ---------- 编码测试：所有 chunk 内容不含乱码替换字符 ----------
    garbled = [c for c in chunks if "\ufffd" in c.title + c.content]
    garbled_ratio = len(garbled) / len(chunks) if chunks else 0
    check_true(
        f"{name}: 乱码率 < 5%（实际 {garbled_ratio:.1%}）",
        garbled_ratio < 0.05,
    )

    # ---------- 标题非空 ----------
    empty_title = [c for c in chunks if not c.title.strip()]
    check_true(f"{name}: 无空标题", len(empty_title) == 0)

    # ---------- 内容长度合理 ----------
    too_short = [c for c in chunks if len(c.content) < 10]
    too_long = [c for c in chunks if len(c.content) > cfg.max_chunk_chars + 100]
    check_true(
        f"{name}: 过短chunk({len(too_short)}) < 20%",
        len(too_short) / len(chunks) < 0.20,
    )
    check_true(
        f"{name}: 无超长chunk（{len(too_long)} 个）",
        len(too_long) == 0,
    )

    # ---------- 类别分布 ----------
    cat_counter = Counter(c.category.value for c in chunks)

    # ---------- 关键词 ----------
    no_kw = [c for c in chunks if not c.keywords]
    check_true(
        f"{name}: 有关键词的 chunk > 50%（无关键词 {len(no_kw)}/{len(chunks)}）",
        len(no_kw) / len(chunks) < 0.50,
    )

    # ---------- content_hash 唯一性（近似去重能力验证） ----------
    hashes = [c.content_hash for c in chunks]
    unique_hashes = len(set(hashes))

    # ---------- source 统一 ----------
    sources = {c.source for c in chunks}
    check(f"{name}: source 统一", len(sources), 1)

    # ====== 书籍特有断言（不依赖随机抽样命中特定文件） ======
    if name == "怪物图鉴2025":
        # 至少有带 HP/AC 字样的怪物块
        has_stat = sum(
            1 for c in chunks
            if ("HP" in c.content or "AC " in c.content
                or "生命值" in c.content or "护甲等级" in c.content)
        )
        check_true(f"{name}: 含怪物属性的 chunk > 0", has_stat > 0)

    elif name == "玩家手册2024":
        # 抽样到法术或职业内容至少一种
        has_rules = any(
            c.category in (RuleCategory.SPELL, RuleCategory.CLASS_FEATURE,
                           RuleCategory.COMBAT, RuleCategory.EQUIPMENT)
            for c in chunks
        )
        check_true(f"{name}: 含规则内容 chunk", has_rules)

    elif name == "城主指南2024":
        # 抽样到任何非空内容即可（多数文件是规则文本）
        check_true(f"{name}: 有 chunk 产出", len(chunks) > 0)

    # ---------- 打印统计 ----------
    print(f"\n  ✅ 通过所有断言")
    print(f"  ⏱  耗时: {elapsed:.1f}s")
    print(f"  📦 chunk 总数: {len(chunks)}")
    print(f"  ⚠️  错误文件: {len(errors)}")
    print(f"  🔤 乱码 chunk: {len(garbled)} ({garbled_ratio:.1%})")
    print(f"  📏 过短 chunk: {len(too_short)}")
    print(f"  🔑 无关键词:   {len(no_kw)}")
    print(f"  🆔 去重哈希:   {unique_hashes}/{len(chunks)} 唯一")
    print(f"\n  类别分布:")
    for cat, cnt in sorted(cat_counter.items(), key=lambda x: -x[1]):
        bar = "█" * min(30, cnt // max(1, len(chunks) // 30))
        print(f"    {cat:20s}  {cnt:5d}  {bar}")

    if errors:
        print(f"\n  错误文件 (前 5):")
        for e in errors[:5]:
            print(f"    ❌ {e}")

    # 返回统计供汇总
    return {
        "name": name,
        "chunks": len(chunks),
        "errors": len(errors),
        "garbled": len(garbled),
        "too_short": len(too_short),
        "no_kw": len(no_kw),
        "categories": dict(cat_counter),
        "elapsed": elapsed,
        "all_chunks": chunks,
    }


def test_encoding_detail():
    """详细验证一个典型的 GBK 文件解析结果"""
    print(f"\n{'='*60}")
    print("  🔬 编码细节测试（成年红龙）")
    print(f"{'='*60}")

    path = BASE / "怪物图鉴2025" / "龙类" / "红龙" / "成年红龙.htm"
    if not path.exists():
        print("  ⚠️  文件不存在，跳过")
        return

    cfg = HTMProcessConfig(
        source_name="怪物图鉴 2025",
        source_enum=RuleSource.MM_2024,
        edition="MM 2025",
    )
    chunks = HTMProcessor.process_file(path, cfg)

    check_true("成年红龙: 有chunk", len(chunks) > 0)
    combined = " ".join(c.title + " " + c.content for c in chunks)
    check_true("成年红龙: 无乱码", "\ufffd" not in combined)
    check_true("成年红龙: 标题含龙", any("龙" in c.title or "Dragon" in c.title for c in chunks))
    check_true("成年红龙: 内容含AC", "AC" in combined or "护甲" in combined)

    print(f"  ✅ 解码成功，chunk 数: {len(chunks)}")
    print(f"  第一个 chunk 标题: {chunks[0].title}")
    print(f"  第一个 chunk 内容预览: {chunks[0].content[:200]}")


def test_spell_extraction_detail():
    """详细验证法术解析（火球术）"""
    print(f"\n{'='*60}")
    print("  🔬 法术解析细节测试")
    print(f"{'='*60}")

    # 在法术目录下找任意一个法术文件
    spell_dir = BASE / "玩家手册2024" / "法术详述"
    if not spell_dir.exists():
        print(f"  ⚠️  {spell_dir} 不存在，跳过")
        return

    files = list(spell_dir.glob("**/*.htm"))[:5]
    if not files:
        print("  ⚠️  未找到法术文件，跳过")
        return

    cfg = HTMProcessConfig(
        source_name="玩家手册 2024",
        source_enum=RuleSource.PHB_2024,
        edition="PHB 2024",
    )

    print(f"  测试文件: {[f.name for f in files]}")
    for f in files:
        chunks = HTMProcessor.process_file(f, cfg)
        check_true(f"{f.name}: 有 chunk", len(chunks) > 0)
        check_true(f"{f.name}: 无乱码", all("\ufffd" not in c.title + c.content for c in chunks))
        # h4 切分后，每个法术应该是独立 chunk，标题不该只是文件名
        non_filename_chunks = [c for c in chunks if c.title.rstrip(".htm") != f.stem]
        check_true(
            f"{f.name}: h4 切分生效（有法术名作标题）",
            len(non_filename_chunks) > 0,
        )
        print(f"  ✅ {f.name}: {len(chunks)} chunk(s)，标题示例: {[c.title for c in chunks[:4]]}")


def test_cross_book_dedup_signal():
    """验证 content_hash 能信号级区分两本书的同名条目"""
    print(f"\n{'='*60}")
    print("  🔬 跨书去重信号测试")
    print(f"{'='*60}")

    # 取两本书各少量文件
    results = {}
    for name, meta in list(BOOKS.items())[:2]:
        cfg = HTMProcessConfig(
            source_name=meta["source_name"],
            source_enum=meta["source"],
            edition=meta["edition"],
        )
        chunks, _ = HTMProcessor.process_directory(Path(meta["path"]), cfg, max_files=10)
        results[name] = chunks

    all_hashes_a = {c.content_hash for c in results[list(BOOKS.keys())[0]]}
    all_hashes_b = {c.content_hash for c in results[list(BOOKS.keys())[1]]}
    overlap = all_hashes_a & all_hashes_b

    # 两本不同书内容哈希重合率应很低（< 20%）
    overlap_ratio = len(overlap) / max(1, min(len(all_hashes_a), len(all_hashes_b)))
    check_true(
        f"跨书哈希重合率 < 20%（实际 {overlap_ratio:.1%}）",
        overlap_ratio < 0.20,
    )
    print(f"  ✅ 哈希重合: {len(overlap)} / {min(len(all_hashes_a), len(all_hashes_b))} = {overlap_ratio:.1%}")


# ================================================================
#  主函数
# ================================================================

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="全量处理（默认每本抽样20文件）")
    args = parser.parse_args()

    max_files = 0 if args.full else 20

    print("=" * 60)
    print("  D&D 规则书 HTM 导入真实数据测试")
    print(f"  模式: {'全量' if max_files == 0 else f'抽样 {max_files} 文件/本'}")
    print("=" * 60)

    failures: list[str] = []
    all_stats: list[dict] = []
    total_t0 = time.time()

    # === 编码细节 ===
    try:
        test_encoding_detail()
    except Exception as e:
        failures.append(f"encoding_detail: {e}")
        traceback.print_exc()

    # === 法术细节 ===
    try:
        test_spell_extraction_detail()
    except Exception as e:
        failures.append(f"spell_detail: {e}")

    # === 跨书去重 ===
    try:
        test_cross_book_dedup_signal()
    except Exception as e:
        failures.append(f"cross_book_dedup: {e}")

    # === 三本书逐一测试 ===
    for book_name, book_meta in BOOKS.items():
        try:
            stats = test_book(book_name, book_meta, max_files=max_files)
            all_stats.append(stats)
        except TestFailure as e:
            print(f"\n  [FAIL] {e}")
            failures.append(str(e))
        except Exception as e:
            print(f"\n  [ERROR] {book_name}: {e}")
            traceback.print_exc()
            failures.append(f"{book_name}: {e}")

    # === 汇总 ===
    total_elapsed = time.time() - total_t0
    total_chunks = sum(s["chunks"] for s in all_stats)
    total_errors = sum(s["errors"] for s in all_stats)

    print(f"\n{'='*60}")
    print(f"  📊 汇总统计")
    print(f"{'='*60}")
    print(f"  总 chunk 数 : {total_chunks}")
    print(f"  总错误文件  : {total_errors}")
    print(f"  总耗时      : {total_elapsed:.1f}s")

    if all_stats:
        all_cats: Counter = Counter()
        for s in all_stats:
            for cat, cnt in s["categories"].items():
                all_cats[cat] += cnt
        print(f"\n  合并类别分布:")
        for cat, cnt in sorted(all_cats.items(), key=lambda x: -x[1]):
            pct = cnt / total_chunks * 100
            print(f"    {cat:20s}  {cnt:6d}  ({pct:.1f}%)")

    print(f"\n{'='*60}")
    if failures:
        print(f"[FAIL] {len(failures)} 个失败:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"[PASS] 所有真实数据测试通过 ✓")


if __name__ == "__main__":
    main()
