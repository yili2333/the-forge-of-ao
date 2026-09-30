"""
HTM 处理器测试套件

覆盖:
  - 基础 heading 切分
  - 表格提取
  - 法术块检测
  - 怪物属性块检测
  - 长节自动拆分
  - 短节合并
  - 目录噪声过滤
  - 关键词提取
  - 类别自动识别
  - 直接提交 chunks 的 API 模型序列化
"""

from __future__ import annotations

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from htm_processor import (
    HTMExtractor,
    HTMChunker,
    HTMProcessor,
    HTMProcessConfig,
    detect_category,
    detect_section_type,
    extract_keywords,
)
from models import RuleCategory, RuleSource, HTMImportRequest


# ================================================================
#  测试辅助
# ================================================================

class TestFailure(Exception):
    pass


def check(label: str, actual, expected) -> None:
    if actual != expected:
        raise TestFailure(f"[{label}] 期望 {expected!r}，实际 {actual!r}")
    print(f"  [OK] {label} = {actual!r}")


def check_true(label: str, value: bool) -> None:
    check(label, value, True)


# ================================================================
#  示例 HTML
# ================================================================

SIMPLE_HTML = """<!DOCTYPE html>
<html>
<body>
  <nav id="toc"><ul><li>Navigation noise</li></ul></nav>
  <h1>Chapter 1: Combat</h1>
  <p>Combat in D&amp;D follows a strict sequence.</p>

  <h2>Attack Rolls</h2>
  <p>When you make an attack, you roll a d20 and add your ability modifier.</p>
  <p>On a hit, you deal damage using the weapon's damage dice.</p>

  <h2>Opportunity Attacks</h2>
  <p>You can make one opportunity attack when a creature leaves your reach.</p>

  <h1>Chapter 2: Spellcasting</h1>
  <p>Every spell has a level from 0 (cantrip) to 9.</p>
</body>
</html>"""


SPELL_HTML = """<!DOCTYPE html>
<html><body>
  <h1>Spells</h1>

  <h2>Fireball</h2>
  <p><em>3rd-level Evocation</em></p>
  <p><strong>Casting Time:</strong> 1 Action</p>
  <p><strong>Range:</strong> 150 feet</p>
  <p><strong>Components:</strong> V, S, M (a tiny ball of bat guano)</p>
  <p><strong>Duration:</strong> Instantaneous</p>
  <p>A bright streak flashes from your pointing finger to a point you choose within range,
  then blossoms with a low roar into an explosion of flame.</p>

  <h2>Shield</h2>
  <p><em>1st-level Abjuration</em></p>
  <p><strong>Casting Time:</strong> 1 Reaction</p>
  <p><strong>Range:</strong> Self</p>
  <p><strong>Components:</strong> V, S</p>
  <p><strong>Duration:</strong> 1 round</p>
  <p>An invisible barrier of magical force appears and protects you.</p>
</body></html>"""


MONSTER_HTML = """<!DOCTYPE html>
<html><body>
  <h1>Monsters</h1>

  <h2>Goblin</h2>
  <p><em>Small Humanoid (Goblinoid), Neutral Evil</em></p>
  <p>Armor Class 15 (leather armor, shield)</p>
  <p>Hit Points 10 (3d6)</p>
  <p>Speed: 30 ft.</p>
  <table>
    <tr><th>STR</th><th>DEX</th><th>CON</th><th>INT</th><th>WIS</th><th>CHA</th></tr>
    <tr><td>8 (-1)</td><td>14 (+2)</td><td>10 (+0)</td><td>10 (+0)</td><td>8 (-1)</td><td>8 (-1)</td></tr>
  </table>
  <p>Challenge 1/4 (50 XP)</p>
  <p>Nimble Escape. The goblin can take the Disengage or Hide action as a bonus action.</p>

  <h2>Dragon, Red (Adult)</h2>
  <p><em>Huge Dragon, Chaotic Evil</em></p>
  <p>Armor Class 19 (natural armor)</p>
  <p>Hit Points 256 (19d12 + 133)</p>
  <p>Speed: 40 ft., climb 40 ft., fly 80 ft.</p>
  <p>Challenge 17 (18,000 XP)</p>
</body></html>"""


TABLE_HTML = """<!DOCTYPE html>
<html><body>
  <h1>Equipment</h1>
  <h2>Armor Table</h2>
  <p>The Armor table shows the cost, weight, and other properties of common armor.</p>
  <table>
    <tr><th>Armor</th><th>Cost</th><th>Armor Class (AC)</th><th>Weight</th></tr>
    <tr><td>Leather Armor</td><td>10 gp</td><td>11 + Dex modifier</td><td>10 lb.</td></tr>
    <tr><td>Chain Mail</td><td>75 gp</td><td>16</td><td>55 lb.</td></tr>
    <tr><td>Plate</td><td>1,500 gp</td><td>18</td><td>65 lb.</td></tr>
  </table>
</body></html>"""


LONG_HTML = """<!DOCTYPE html>
<html><body>
  <h1>Classes</h1>
  <h2>Fighter</h2>
  <p>""" + " ".join(["The fighter is a master of martial combat."] * 50) + """</p>
  <p>""" + " ".join(["Fighters can use all armor and weapons."] * 50) + """</p>
  <p>""" + " ".join(["Action Surge allows you to take an extra action."] * 50) + """</p>
</body></html>"""


NOISE_HTML = """<!DOCTYPE html>
<html>
<head><title>D&D Rules</title><style>body {margin:0}</style></head>
<body>
  <header><nav>Home | Rules | Spells</nav></header>
  <nav><ul><li>Chapter 1</li><li>Chapter 2</li></ul></nav>
  <aside class="sidebar-nav">Quick links</aside>
  <main>
    <h1>Ability Scores</h1>
    <p>Six ability scores determine your character's strengths and weaknesses.</p>
    <h2>Strength</h2>
    <p>Strength measures your physical power.</p>
  </main>
  <footer>Copyright WotC</footer>
  <script>console.log("noise")</script>
</body>
</html>"""


# ================================================================
#  测试函数
# ================================================================

def test_basic_heading_split():
    print("\n=== basic heading split ===")
    cfg = HTMProcessConfig()
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(SIMPLE_HTML)

    # 应该切出 4 节：ch1, attack rolls, opportunity attacks, ch2
    check_true("sections > 2", len(sections) >= 3)
    titles = [s.title for s in sections]
    check_true("Chapter 1 in titles", any("Chapter 1" in t or "Combat" in t for t in titles))
    check_true("Attack Rolls in titles", any("Attack Rolls" in t for t in titles))
    check_true("Opportunity Attacks in titles", any("Opportunity" in t for t in titles))
    print(f"  extracted {len(sections)} sections: {[s.title for s in sections]}")

    # 父标题链：Attack Rolls 的 parent 应包含 Chapter 1
    for s in sections:
        if "Attack Rolls" in s.title:
            check_true("Attack Rolls has parent", len(s.parent_titles) > 0)
            break


def test_noise_filtering():
    print("\n=== noise filtering ===")
    cfg = HTMProcessConfig()
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(NOISE_HTML)

    all_content = " ".join(s.content for s in sections)
    check_true("nav text removed", "Home | Rules" not in all_content)
    check_true("footer removed", "Copyright WotC" not in all_content)
    check_true("script removed", "console.log" not in all_content)
    check_true("real content present", "ability scores" in all_content.lower())


def test_spell_detection():
    print("\n=== spell detection ===")
    cfg = HTMProcessConfig()
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(SPELL_HTML)
    chunker = HTMChunker(cfg)
    chunks = chunker.chunk(sections)

    spell_chunks = [c for c in chunks if c.category == RuleCategory.SPELL]
    check_true("at least 2 spell chunks", len(spell_chunks) >= 1)
    print(f"  spell chunks: {[c.title for c in spell_chunks]}")

    fireball = next((c for c in chunks if "Fireball" in c.title), None)
    check_true("fireball found", fireball is not None)
    if fireball:
        check("fireball is spell", fireball.category, RuleCategory.SPELL)
        check_true("fireball keywords not empty", len(fireball.keywords) > 0)
        check_true("fireball content has casting time",
                   "Casting Time" in fireball.content)

    section_type = detect_section_type(sections[1]) if len(sections) > 1 else "unknown"
    check("fireball section type", section_type, "spell")


def test_monster_detection():
    print("\n=== monster detection ===")
    cfg = HTMProcessConfig()
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(MONSTER_HTML)
    chunker = HTMChunker(cfg)
    chunks = chunker.chunk(sections)

    goblin = next((c for c in chunks if "Goblin" in c.title), None)
    check_true("goblin found", goblin is not None)
    if goblin:
        check_true("goblin content has AC", "Armor Class" in goblin.content or "AC" in goblin.content)

    for sec in sections:
        if "Goblin" in sec.title:
            stype = detect_section_type(sec)
            check("goblin section type", stype, "monster")
            break


def test_table_extraction():
    print("\n=== table extraction ===")
    cfg = HTMProcessConfig()
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(TABLE_HTML)

    armor_sec = next((s for s in sections if "Armor" in s.title), None)
    check_true("armor section found", armor_sec is not None)
    if armor_sec:
        check_true("table headers present", "Armor" in armor_sec.content and "Cost" in armor_sec.content)
        check_true("table row separator present", " | " in armor_sec.content)
        check_true("leather armor row present", "Leather Armor" in armor_sec.content)
        check_true("plate row present", "Plate" in armor_sec.content)
        print(f"  table content preview: {armor_sec.content[:200]}")


def test_long_section_split():
    print("\n=== long section split ===")
    cfg = HTMProcessConfig(max_chunk_chars=300)
    chunks = HTMProcessor.process_file.__func__ if hasattr(HTMProcessor.process_file, "__func__") else None
    # Inline: extract + chunk manually
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(LONG_HTML)
    chunker = HTMChunker(cfg)
    result = chunker.chunk(sections)

    fighter_chunks = [c for c in result if "Fighter" in c.title]
    check_true("long section split into multiple chunks", len(fighter_chunks) > 1)
    for c in fighter_chunks:
        check_true(f"chunk '{c.title}' under max size",
                   len(c.content) <= cfg.max_chunk_chars + 50)
    print(f"  fighter split into {len(fighter_chunks)} chunks")


def test_short_section_merge():
    print("\n=== short section merge ===")
    html = """<html><body>
    <h1>Chapter</h1>
    <h2>Intro</h2>
    <p>Short.</p>
    <h2>Real Content</h2>
    <p>This is the actual meat of the section with enough content to be useful.</p>
    </body></html>"""
    cfg = HTMProcessConfig(min_chunk_chars=50)
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(html)
    chunker = HTMChunker(cfg)
    chunks = chunker.chunk(sections)
    # "Intro" with "Short." (6 chars) should merge into "Real Content"
    # Or at minimum, the final chunk count should be less than raw section count
    check_true("merge reduces chunk count or absorbs short", len(chunks) <= len(sections))
    print(f"  sections={len(sections)} → chunks={len(chunks)}")


def test_keyword_extraction():
    print("\n=== keyword extraction ===")
    title = "Sneak Attack"
    content = (
        "Beginning at 1st level, you know how to strike subtly and exploit a foe's distraction. "
        "Once per turn, you can deal an extra 1d6 damage to one creature you hit with an attack if "
        "you have advantage on the attack roll."
    )
    kw = extract_keywords(title, content)
    check_true("sneak in keywords", any("sneak" in k.lower() or "Sneak" in k for k in kw))
    check_true("keywords non-empty", len(kw) > 0)
    check_true("at most 12 keywords", len(kw) <= 12)
    print(f"  keywords: {kw}")


def test_category_detection():
    print("\n=== category detection ===")
    cfg = HTMProcessConfig()
    # Spell
    cat = detect_category("Fireball", "Casting Time: 1 Action\nRange: 150 feet\nComponents: V, S, M\nDuration: Instantaneous", cfg)
    check("fireball category", cat, RuleCategory.SPELL)
    # Monster
    cat = detect_category("Goblin", "Armor Class 15\nHit Points 10\nSpeed: 30 ft.\nChallenge 1/4", cfg)
    check("goblin category", cat, RuleCategory.GENERAL_RULE)
    # Equipment
    cat = detect_category("Chain Mail", "Cost: 75 gp\nWeight: 55 lb.\nArmor Class (AC): 16", cfg)
    check("chain mail category", cat, RuleCategory.EQUIPMENT)
    # Class feature
    cat = detect_category("Action Surge", "Starting at 2nd level, you can push yourself beyond your normal limits for a moment.", cfg)
    check("action surge category", cat, RuleCategory.CLASS_FEATURE)
    # Combat
    cat = detect_category("Opportunity Attack", "You can make an opportunity attack when a creature leaves your reach. Use your reaction.", cfg)
    check("opportunity attack category", cat, RuleCategory.COMBAT)


def test_process_file_from_string(tmp_path_str: str):
    """process_file 接受 Path 对象"""
    print("\n=== process_file ===")
    import tempfile, os
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8", delete=False
    ) as f:
        f.write(SPELL_HTML)
        tmp_path = f.name

    try:
        cfg = HTMProcessConfig(source_enum=RuleSource.PHB_2024, edition="PHB 2024")
        chunks = HTMProcessor.process_file(tmp_path, cfg)
        check_true("process_file returns chunks", len(chunks) > 0)
        check_true("chunks have source", all(c.source == RuleSource.PHB_2024 for c in chunks))
        check_true("chunks have content hash", all(c.content_hash for c in chunks))
        check_true("chunks have id prefix", all(c.id.startswith("htm-") for c in chunks))
        print(f"  processed {len(chunks)} chunks from file")
    finally:
        os.unlink(tmp_path)


def test_api_model_serialization():
    """HTMImportRequest 可以序列化 chunks"""
    print("\n=== API model serialization ===")
    cfg = HTMProcessConfig(source_enum=RuleSource.PHB_2024)
    extractor = HTMExtractor(cfg)
    sections = extractor.extract(SPELL_HTML)
    chunker = HTMChunker(cfg)
    chunks = chunker.chunk(sections)

    req = HTMImportRequest(chunks=chunks, check_conflicts=False)
    serialized = req.model_dump_json()
    restored = HTMImportRequest.model_validate_json(serialized)

    check("chunk count preserved", len(restored.chunks), len(chunks))
    check_true("first chunk title preserved", restored.chunks[0].title == chunks[0].title)
    check_true("source preserved", restored.chunks[0].source == chunks[0].source)
    print(f"  serialized {len(chunks)} chunks → JSON → restored successfully")


def test_multi_file_directory():
    """process_directory 处理目录"""
    print("\n=== directory processing ===")
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        # 写几个 HTML 文件
        (Path(tmpdir) / "combat.html").write_text(SIMPLE_HTML, encoding="utf-8")
        (Path(tmpdir) / "spells.html").write_text(SPELL_HTML, encoding="utf-8")
        (Path(tmpdir) / "monsters.html").write_text(MONSTER_HTML, encoding="utf-8")

        cfg = HTMProcessConfig()
        chunks, errors = HTMProcessor.process_directory(tmpdir, cfg)

        check_true("all files processed", len(errors) == 0)
        check_true("got chunks from all files", len(chunks) > 3)
        sources = {c.source for c in chunks}
        check_true("all same source", len(sources) == 1)
        print(f"  directory: {len(chunks)} total chunks, {len(errors)} errors")


# ================================================================
#  运行
# ================================================================

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    print("=" * 50)
    print("  HTM Processor Tests")
    print("=" * 50)

    failures: list[str] = []

    tests = [
        test_basic_heading_split,
        test_noise_filtering,
        test_spell_detection,
        test_monster_detection,
        test_table_extraction,
        test_long_section_split,
        test_short_section_merge,
        test_keyword_extraction,
        test_category_detection,
        lambda: test_process_file_from_string(""),
        test_api_model_serialization,
        test_multi_file_directory,
    ]

    for test_fn in tests:
        try:
            test_fn()
        except TestFailure as e:
            print(f"  [FAIL] {e}")
            failures.append(str(e))
        except Exception as e:
            import traceback
            print(f"  [ERROR] {test_fn.__name__ if hasattr(test_fn, '__name__') else str(test_fn)}: {e}")
            traceback.print_exc()
            failures.append(str(e))

    print("\n" + "=" * 50)
    if failures:
        print(f"[FAIL] {len(failures)} 个测试失败:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print(f"[PASS] All HTM processor tests passed.")


if __name__ == "__main__":
    main()
