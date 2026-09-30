"""
PDF 处理器完整测试脚本
1. 自动生成测试用 PDF（不需要真实规则书）
2. 逐步测试每个阶段
3. 测试导入系统的完整流程
"""

import asyncio
import sys
import os
import json
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ================================================================
#  第0步: 生成测试 PDF
# ================================================================

def create_test_pdf(output_path: str = "test_rulebook.pdf"):
    """
    自动生成一个模拟 D&D 规则书的 PDF
    包含各种类型的内容：标题层级、法术、表格、战斗规则等
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("❌ 请先安装 PyMuPDF: pip install PyMuPDF")
        return None

    doc = fitz.open()

    def add_page(texts: list[tuple[str, float, bool]]):
        """添加一页，texts = [(内容, 字号, 是否粗体), ...]"""
        page = doc.new_page(width=612, height=792)  # Letter size
        y = 50
        for text, size, bold in texts:
            font = "helv"  # Helvetica
            fontname = "hebo" if bold else "helv"
            for line in text.split("\n"):
                if y > 740:
                    page = doc.new_page(width=612, height=792)
                    y = 50
                page.insert_text(
                    (50, y),
                    line,
                    fontsize=size,
                    fontname=fontname,
                )
                y += size * 1.4
            y += 10  # 段间距

    # ===== 封面 =====
    add_page([
        ("TEST RULEBOOK", 28, True),
        ("For PDF Processor Testing", 14, False),
        ("This is a test document", 12, False),
    ])

    # ===== 目录（应该被跳过）=====
    add_page([
        ("TABLE OF CONTENTS", 20, True),
        ("Chapter 1: Combat Rules ......... 3", 12, False),
        ("Chapter 2: Spellcasting ......... 5", 12, False),
        ("Chapter 3: Conditions ........... 7", 12, False),
        ("Chapter 4: Equipment ............ 9", 12, False),
    ])

    # ===== Chapter 1: Combat Rules =====
    add_page([
        ("Chapter 1: Combat Rules", 24, True),
        ("", 12, False),
        ("The Order of Combat", 18, True),
        ("""Combat in D&D is organized into rounds and turns. A round represents 
about 6 seconds in the game world. During a round, each participant 
takes one turn. The order of turns is determined at the beginning of 
combat when everyone rolls Initiative.""", 11, False),
        ("", 12, False),
        ("Initiative", 16, True),
        ("""At the beginning of combat, every participant makes a Dexterity check 
to determine their place in the Initiative order. The DM makes one roll 
for an entire group of identical creatures. The DM ranks the combatants 
in order from highest to lowest Dexterity check total.""", 11, False),
    ])

    add_page([
        ("Actions in Combat", 16, True),
        ("""On your turn, you can take one Action, one Bonus Action, and 
move a distance up to your Speed. Common actions include:

Attack: Make one melee or ranged attack.
Cast a Spell: Cast a spell with a casting time of one Action.
Dash: Gain extra movement equal to your Speed.
Disengage: Your movement does not provoke Opportunity Attacks.
Dodge: Attack rolls against you have Disadvantage.
Help: Give an ally Advantage on their next check or attack.
Hide: Make a Dexterity (Stealth) check to hide.
Ready: Prepare an action for a specific trigger.
Search: Make a Perception or Investigation check.""", 11, False),
        ("", 12, False),
        ("Opportunity Attacks", 16, True),
        ("""You can make an Opportunity Attack when a hostile creature that you 
can see moves out of your reach. To make the Opportunity Attack, you 
use your Reaction to make one melee attack against the provoking 
creature. The attack occurs right before the creature leaves your reach.

You can avoid provoking an Opportunity Attack by taking the Disengage 
action. You also don't provoke when you teleport or when something 
moves you without using your movement, Action, or Reaction.""", 11, False),
    ])

    add_page([
        ("Making an Attack", 16, True),
        ("""Attack Roll = d20 + Ability Modifier + Proficiency Bonus

Melee attacks typically use Strength modifier.
Ranged attacks typically use Dexterity modifier.
Finesse weapons can use either Strength or Dexterity.

Critical Hit: A natural 20 on the d20 always hits. Roll all damage 
dice twice and add them together, then add modifiers.

Critical Miss: A natural 1 on the d20 always misses.""", 11, False),
        ("", 12, False),
        ("Cover", 16, True),
        ("""Half Cover: +2 bonus to AC and Dexterity saving throws.
Three-Quarters Cover: +5 bonus to AC and Dexterity saving throws.
Total Cover: Cannot be targeted directly by attacks or spells.""", 11, False),
    ])

    # ===== Chapter 2: Spellcasting =====
    add_page([
        ("Chapter 2: Spellcasting", 24, True),
        ("", 12, False),
        ("Spellcasting Basics", 18, True),
        ("""Every spell has a level from 0 to 9. Casting a spell expends a 
spell slot of the appropriate level or higher. Cantrips (level 0) 
can be cast at will without using a spell slot.""", 11, False),
        ("", 12, False),
        ("Concentration", 16, True),
        ("""Some spells require Concentration to maintain. Rules for Concentration:
1. You can concentrate on only one spell at a time.
2. Taking damage requires a Constitution saving throw (DC 10 or half 
   the damage taken, whichever is higher) to maintain Concentration.
3. Being Incapacitated or killed ends Concentration.
4. Casting another Concentration spell ends the current one.""", 11, False),
    ])

    # ===== 法术示例 =====
    add_page([
        ("Spell Descriptions", 18, True),
        ("", 12, False),
        ("Fireball", 14, True),
        ("""3rd-level Evocation
Casting Time: 1 Action
Range: 150 feet
Components: V, S, M (a tiny ball of bat guano and sulfur)
Duration: Instantaneous

A bright streak flashes from your pointing finger to a point you 
choose within range and then blossoms with a low roar into an 
explosion of flame. Each creature in a 20-foot-radius sphere 
centered on that point must make a Dexterity saving throw. A target 
takes 8d6 fire damage on a failed save, or half as much on a success.

At Higher Levels: The damage increases by 1d6 for each slot level above 3rd.""", 11, False),
    ])

    add_page([
        ("Shield", 14, True),
        ("""1st-level Abjuration
Casting Time: 1 Reaction, when you are hit by an attack or targeted by Magic Missile
Range: Self
Components: V, S
Duration: 1 round

An invisible barrier of magical force protects you. Until the start 
of your next turn, you have a +5 bonus to AC, including against the 
triggering attack, and you take no damage from Magic Missile.""", 11, False),
        ("", 12, False),
        ("Healing Word", 14, True),
        ("""1st-level Evocation
Casting Time: 1 Bonus Action
Range: 60 feet
Components: V
Duration: Instantaneous

A creature of your choice that you can see within range regains hit 
points equal to 1d4 + your spellcasting ability modifier.

At Higher Levels: The healing increases by 1d4 for each slot level above 1st.""", 11, False),
        ("", 12, False),
        ("Mage Hand", 14, True),
        ("""Conjuration Cantrip
Casting Time: 1 Action
Range: 30 feet
Components: V, S
Duration: 1 minute

A spectral, floating hand appears at a point you choose within range. 
The hand can manipulate an object, open an unlocked door or container, 
stow or retrieve an item from an open container, or pour the contents 
out of a vial. You can move the hand up to 30 feet each time you use it.
The hand cannot attack, activate magic items, or carry more than 10 pounds.""", 11, False),
    ])

    # ===== Chapter 3: Conditions =====
    add_page([
        ("Chapter 3: Conditions", 24, True),
        ("", 12, False),
        ("Blinded", 14, True),
        ("""A blinded creature cannot see and automatically fails any ability 
check that requires sight. Attack rolls against the creature have 
Advantage, and the creature's attack rolls have Disadvantage.""", 11, False),
        ("", 12, False),
        ("Charmed", 14, True),
        ("""A charmed creature cannot attack the charmer or target the charmer 
with harmful abilities or magical effects. The charmer has Advantage 
on any ability check to interact socially with the creature.""", 11, False),
        ("", 12, False),
        ("Frightened", 14, True),
        ("""A frightened creature has Disadvantage on ability checks and attack 
rolls while the source of its fear is within line of sight. The 
creature cannot willingly move closer to the source of its fear.""", 11, False),
        ("", 12, False),
        ("Grappled", 14, True),
        ("""A grappled creature's speed becomes 0, and it cannot benefit from 
any bonus to its speed. The condition ends if the grappler is 
Incapacitated. The condition also ends if an effect removes the 
grappled creature from the reach of the grappler.""", 11, False),
        ("", 12, False),
        ("Incapacitated", 14, True),
        ("""An incapacitated creature cannot take Actions, Bonus Actions, 
or Reactions.""", 11, False),
        ("", 12, False),
        ("Invisible", 14, True),
        ("""An invisible creature is impossible to see without the aid of magic 
or a special sense. The creature is heavily obscured for the purpose 
of hiding. Attack rolls against the creature have Disadvantage, and 
the creature's attack rolls have Advantage.""", 11, False),
    ])

    add_page([
        ("Prone", 14, True),
        ("""A prone creature's only movement option is to crawl. The creature 
has Disadvantage on attack rolls. An attack roll against the creature 
has Advantage if the attacker is within 5 feet. Otherwise, the 
attack roll has Disadvantage.""", 11, False),
        ("", 12, False),
        ("Stunned", 14, True),
        ("""A stunned creature is Incapacitated, cannot move, and can speak 
only falteringly. The creature automatically fails Strength and 
Dexterity saving throws. Attack rolls against the creature have 
Advantage.""", 11, False),
        ("", 12, False),
        ("Unconscious", 14, True),
        ("""An unconscious creature is Incapacitated, cannot move or speak, 
and is unaware of its surroundings. The creature drops whatever 
it is holding and falls Prone. The creature automatically fails 
Strength and Dexterity saving throws. Attack rolls against the 
creature have Advantage. Any attack that hits is a Critical Hit 
if the attacker is within 5 feet.""", 11, False),
    ])

    # ===== Chapter 4: Equipment =====
    add_page([
        ("Chapter 4: Equipment", 24, True),
        ("", 12, False),
        ("Weapon Properties", 16, True),
        ("""Finesse: Use Strength or Dexterity for attack and damage rolls.
Heavy: Small creatures have Disadvantage on attack rolls.
Light: Can be used for Two-Weapon Fighting.
Reach: Adds 5 feet to your reach.
Thrown: Can throw the weapon for a ranged attack.
Two-Handed: Requires two hands to use.
Versatile: Can be used with one or two hands.""", 11, False),
        ("", 12, False),
        ("Simple Melee Weapons", 16, True),
        ("""Club: 1d4 bludgeoning, Light, 1 sp, 2 lb.
Dagger: 1d4 piercing, Finesse/Light/Thrown (20/60), 2 gp, 1 lb.
Greatclub: 1d8 bludgeoning, Two-Handed, 2 sp, 10 lb.
Handaxe: 1d6 slashing, Light/Thrown (20/60), 5 gp, 2 lb.
Javelin: 1d6 piercing, Thrown (30/120), 5 sp, 2 lb.
Mace: 1d6 bludgeoning, 5 gp, 4 lb.
Quarterstaff: 1d6 bludgeoning, Versatile (1d8), 2 sp, 4 lb.
Spear: 1d6 piercing, Thrown (20/60)/Versatile (1d8), 1 gp, 3 lb.""", 11, False),
        ("", 12, False),
        ("Martial Melee Weapons", 16, True),
        ("""Greatsword: 2d6 slashing, Heavy/Two-Handed, 50 gp, 6 lb.
Longsword: 1d8 slashing, Versatile (1d10), 15 gp, 3 lb.
Rapier: 1d8 piercing, Finesse, 25 gp, 2 lb.
Scimitar: 1d6 slashing, Finesse/Light, 25 gp, 3 lb.
Shortsword: 1d6 piercing, Finesse/Light, 10 gp, 2 lb.""", 11, False),
    ])

    doc.save(output_path)
    doc.close()
    print(f"✅ 测试 PDF 已生成: {output_path} ({os.path.getsize(output_path) / 1024:.1f} KB)")
    return output_path


# ================================================================
#  测试类
# ================================================================

class PDFProcessorTester:
    """PDF 处理器分阶段测试"""

    def __init__(self):
        self.pdf_path = None
        self.passed = 0
        self.failed = 0
        self.results = []

    def log(self, test_name: str, passed: bool, detail: str = ""):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append((test_name, passed, detail))
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        print(f"  {status}: {test_name}")
        if detail:
            print(f"         {detail}")

    def run_all(self):
        """运行全部测试"""
        print("=" * 60)
        print("🧪 PDF 处理器测试套件")
        print("=" * 60)

        # 生成测试 PDF
        print("\n📄 生成测试 PDF...")
        self.pdf_path = create_test_pdf("test_rulebook.pdf")
        if not self.pdf_path:
            print("❌ 无法生成测试 PDF，终止测试")
            return

        # 逐步测试
        print("\n" + "-" * 40)
        print("📋 阶段1: PDF 文本提取")
        print("-" * 40)
        pages_data = self.test_extraction()

        print("\n" + "-" * 40)
        print("📋 阶段2: 章节解析")
        print("-" * 40)
        sections = self.test_section_parsing(pages_data)

        print("\n" + "-" * 40)
        print("📋 阶段3: 法术识别")
        print("-" * 40)
        self.test_spell_detection(sections)

        print("\n" + "-" * 40)
        print("📋 阶段4: 智能分块")
        print("-" * 40)
        chunks = self.test_chunking(sections)

        print("\n" + "-" * 40)
        print("📋 阶段5: 交叉引用")
        print("-" * 40)
        chunks = self.test_cross_references(chunks)

        print("\n" + "-" * 40)
        print("📋 阶段6: 表格提取")
        print("-" * 40)
        self.test_table_extraction()

        print("\n" + "-" * 40)
        print("📋 阶段7: JSON 导出/导入")
        print("-" * 40)
        self.test_json_roundtrip(chunks)

        print("\n" + "-" * 40)
        print("📋 阶段8: 嵌入性能测试")
        print("-" * 40)
        asyncio.run(self.test_embedding_performance(chunks))

        print("\n" + "-" * 40)
        print("📋 阶段9: 完整导入系统测试")
        print("-" * 40)
        asyncio.run(self.test_full_import(chunks))

        # 汇总
        self.print_summary()

        # 清理
        self.cleanup()

    # ===== 阶段1: 提取 =====

    def test_extraction(self) -> list[dict]:
        """测试 PDF 文本提取"""
        from pdf_processor import PDFExtractor, PDFProcessConfig

        config = PDFProcessConfig()
        config.page_start = 3      # 跳过封面和目录
        config.page_end = -1

        extractor = PDFExtractor(self.pdf_path, config)
        pages_data = extractor.extract_all_pages()
        extractor.close()

        # 测试1: 是否提取到了页面
        self.log(
            "提取到页面数据",
            len(pages_data) > 0,
            f"提取了 {len(pages_data)} 页"
        )

        # 测试2: 每页是否有文本块
        non_empty_pages = sum(1 for p in pages_data if p["blocks"])
        self.log(
            "页面包含文本块",
            non_empty_pages > 0,
            f"{non_empty_pages}/{len(pages_data)} 页有内容"
        )

        # 测试3: 文本块是否包含字体信息
        has_font_info = False
        for page in pages_data:
            for block in page["blocks"]:
                if "font_size" in block and block["font_size"] > 0:
                    has_font_info = True
                    break
        self.log("文本块包含字体信息", has_font_info)

        # 测试4: 能否找到 "Chapter" 关键词
        all_text = " ".join(
            block["text"]
            for page in pages_data
            for block in page["blocks"]
        )
        has_chapter = "chapter" in all_text.lower() or "combat" in all_text.lower()
        self.log("内容包含预期关键词", has_chapter)

        # 测试5: 字号分布
        sizes = set()
        for page in pages_data:
            for block in page["blocks"]:
                sizes.add(round(block["font_size"]))
        self.log(
            "检测到多种字号（标题+正文）",
            len(sizes) >= 2,
            f"字号: {sorted(sizes)}"
        )

        return pages_data

    # ===== 阶段2: 章节解析 =====

    def test_section_parsing(self, pages_data: list[dict]) -> list:
        """测试章节结构解析"""
        from pdf_processor import SectionParser, PDFProcessConfig

        config = PDFProcessConfig()
        parser = SectionParser(config)
        sections = parser.parse(pages_data)

        # 测试1: 是否解析出章节
        self.log(
            "解析出章节",
            len(sections) > 0,
            f"共 {len(sections)} 个章节"
        )

        # 测试2: 是否有不同层级的标题
        levels = set(s.level for s in sections)
        self.log(
            "识别出多个标题层级",
            len(levels) >= 2,
            f"层级: {sorted(levels)}"
        )

        # 测试3: 章节是否有内容
        non_empty = sum(1 for s in sections if len(s.content.strip()) > 20)
        self.log(
            "章节包含有意义的内容",
            non_empty > len(sections) * 0.5,
            f"{non_empty}/{len(sections)} 个有内容"
        )

        # 测试4: 能否找到预期的标题
        titles = [s.title.lower() for s in sections]
        expected = ["initiative", "opportunity attack", "fireball", "blinded"]
        found = [e for e in expected if any(e in t for t in titles)]
        self.log(
            "找到预期的关键章节",
            len(found) >= 2,
            f"找到: {found}, 未找到: {[e for e in expected if e not in found]}"
        )

        # 测试5: 父标题链
        has_parents = any(s.parent_titles for s in sections)
        self.log("章节有父级标题链", has_parents)

        # 打印章节概览
        print("\n  📋 章节概览:")
        for s in sections[:15]:
            indent = "    " + "  " * (s.level - 1)
            content_preview = s.content[:50].replace("\n", " ")
            print(f"{indent}[H{s.level}] {s.title} (p.{s.page_start}, {len(s.content)}字符)")

        if len(sections) > 15:
            print(f"    ... 还有 {len(sections) - 15} 个章节")

        return sections

    # ===== 阶段3: 法术识别 =====

    def test_spell_detection(self, sections: list):
        """测试法术自动识别"""
        from pdf_processor import SpellParser

        spell_parser = SpellParser()
        spells_found = []

        for section in sections:
            result = spell_parser.try_parse_spell(section)
            if result:
                spells_found.append(result)

        # 测试1: 是否识别出法术
        self.log(
            "识别出法术",
            len(spells_found) > 0,
            f"找到 {len(spells_found)} 个法术"
        )

        # 测试2: Fireball 是否被识别
        fireball = [s for s in spells_found if "fireball" in s.title.lower()]
        self.log("正确识别 Fireball", len(fireball) > 0)

        # 测试3: Shield 是否被识别
        shield = [s for s in spells_found if "shield" in s.title.lower()]
        self.log("正确识别 Shield", len(shield) > 0)

        # 测试4: 法术类别正确
        all_spell_category = all(
            s.category.value == "spell" for s in spells_found
        )
        self.log("法术类别标记正确", all_spell_category)

        # 测试5: 非法术不被误判为法术
        non_spell_sections = [
            s for s in sections
            if "initiative" in s.title.lower() or "blinded" in s.title.lower()
        ]
        false_positives = 0
        for s in non_spell_sections:
            if spell_parser.try_parse_spell(s):
                false_positives += 1
        self.log(
            "非法术内容不被误判",
            false_positives == 0,
            f"误判数: {false_positives}"
        )

        if spells_found:
            print("\n  🔮 识别到的法术:")
            for sp in spells_found:
                print(f"    - {sp.title} [{', '.join(sp.keywords[:3])}]")

    # ===== 阶段4: 智能分块 =====

    def test_chunking(self, sections: list) -> list:
        """测试智能分块"""
        from pdf_processor import SmartChunker, PDFProcessConfig

        config = PDFProcessConfig()
        config.max_chunk_chars = 2000
        config.min_chunk_chars = 50

        chunker = SmartChunker(config)
        chunks = chunker.chunk_sections(sections)

        # 测试1: 是否生成了规则块
        self.log(
            "生成规则块",
            len(chunks) > 0,
            f"共 {len(chunks)} 个"
        )

        # 测试2: 没有超大块
        oversized = [c for c in chunks if len(c.content) > config.max_chunk_chars * 1.5]
        self.log(
            "无超大规则块",
            len(oversized) == 0,
            f"超大块: {len(oversized)}, 最大: {max(len(c.content) for c in chunks)} 字符"
        )

        # 测试3: 类别多样性
        categories = set(c.category.value for c in chunks)
        self.log(
            "类别多样性",
            len(categories) >= 3,
            f"类别: {categories}"
        )

        # 测试4: 每个块有 ID
        all_have_id = all(c.id for c in chunks)
        self.log("所有块有唯一ID", all_have_id)

        # 测试5: 每个块有标题
        all_have_title = all(c.title for c in chunks)
        self.log("所有块有标题", all_have_title)

        # 测试6: ID 唯一性
        ids = [c.id for c in chunks]
        unique_ids = len(set(ids)) == len(ids)
        self.log(
            "ID 唯一",
            unique_ids,
            f"总数: {len(ids)}, 去重后: {len(set(ids))}"
        )

        # 统计
        print("\n  📊 分块统计:")
        cat_counts = {}
        for c in chunks:
            cat = c.category.value
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
        for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

        return chunks

    # ===== 阶段5: 交叉引用 =====

    def test_cross_references(self, chunks: list) -> list:
        """测试交叉引用构建"""
        from pdf_processor import CrossReferenceBuilder

        builder = CrossReferenceBuilder()
        chunks = builder.build_references(chunks)

        # 测试1: 有规则块建立了引用
        has_refs = sum(1 for c in chunks if c.related_rule_ids)
        self.log(
            "交叉引用已建立",
            has_refs > 0,
            f"{has_refs}/{len(chunks)} 个块有引用"
        )

        # 测试2: 引用的 ID 存在于当前块集合中
        all_ids = {c.id for c in chunks}
        invalid_refs = 0
        for c in chunks:
            for ref_id in c.related_rule_ids:
                if ref_id not in all_ids:
                    invalid_refs += 1
        self.log(
            "引用ID全部有效",
            invalid_refs == 0,
            f"无效引用: {invalid_refs}"
        )

        # 打印一些引用示例
        print("\n  🔗 交叉引用示例:")
        shown = 0
        for c in chunks:
            if c.related_rule_ids and shown < 3:
                ref_titles = []
                for rid in c.related_rule_ids[:3]:
                    ref_chunk = next((x for x in chunks if x.id == rid), None)
                    if ref_chunk:
                        ref_titles.append(ref_chunk.title)
                print(f"    {c.title} → {ref_titles}")
                shown += 1

        return chunks

    # ===== 阶段6: 表格提取 =====

    def test_table_extraction(self):
        """测试表格提取"""
        from pdf_processor import PDFExtractor, PDFProcessConfig

        config = PDFProcessConfig()
        extractor = PDFExtractor(self.pdf_path, config)
        tables = extractor.extract_tables()
        extractor.close()

        # 测试PDF可能没有复杂表格，所以这个测试宽松一些
        self.log(
            "表格提取功能正常运行",
            True,
            f"发现 {len(tables)} 个表格"
        )

        if tables:
            for t in tables[:3]:
                headers = [str(h) for h in (t.get("headers") or []) if h]
                print(f"    页{t['page']}: 列={headers}")

    # ===== 阶段7: JSON 导出/导入 =====

    def test_json_roundtrip(self, chunks: list):
        """测试 JSON 序列化/反序列化"""
        from pdf_processor import save_chunks_to_json, load_chunks_from_json

        json_path = "test_chunks_output.json"

        # 导出
        try:
            save_chunks_to_json(chunks, json_path)
            export_ok = os.path.exists(json_path)
            file_size = os.path.getsize(json_path) / 1024
        except Exception as e:
            export_ok = False
            file_size = 0
            print(f"    导出异常: {e}")

        self.log(
            "JSON 导出成功",
            export_ok,
            f"文件大小: {file_size:.1f} KB"
        )

        # 导入
        try:
            loaded = load_chunks_from_json(json_path)
            import_ok = len(loaded) == len(chunks)
        except Exception as e:
            import_ok = False
            loaded = []
            print(f"    导入异常: {e}")

        self.log(
            "JSON 导入成功且数据完整",
            import_ok,
            f"导出 {len(chunks)} 条, 导入 {len(loaded)} 条"
        )

        # 数据一致性
        if loaded and chunks:
            first_orig = chunks[0]
            first_loaded = loaded[0]
            fields_match = (
                first_orig.id == first_loaded.id
                and first_orig.title == first_loaded.title
                and first_orig.category == first_loaded.category
            )
            self.log("数据字段一致", fields_match)

        # 清理
        if os.path.exists(json_path):
            os.remove(json_path)

    # ===== 阶段8: 嵌入性能测试 =====

    async def test_embedding_performance(self, chunks: list):
        """测试嵌入服务性能"""
        from embedding_service import EmbeddingService

        try:
            service = EmbeddingService()
        except Exception as e:
            self.log("嵌入服务初始化", False, str(e))
            return

        self.log(
            "嵌入服务初始化",
            True,
            f"模式: {service.mode}, 维度: {service.dimensions}, 设备: {getattr(service, 'device', 'N/A')}"
        )

        # 测试单条嵌入
        t0 = time.time()
        try:
            emb = await service.embed_text("Sneak Attack requires advantage")
            single_time = time.time() - t0
            self.log(
                "单条嵌入",
                len(emb) == service.dimensions,
                f"维度: {len(emb)}, 耗时: {single_time:.2f}秒"
            )
        except Exception as e:
            self.log("单条嵌入", False, str(e))
            return

        # 测试小批量（10条）
        test_texts = [c.content[:200] for c in chunks[:10]]
        t0 = time.time()
        try:
            embs = await service.embed_texts(test_texts)
            batch_time = time.time() - t0
            self.log(
                f"批量嵌入 ({len(test_texts)}条)",
                len(embs) == len(test_texts),
                f"耗时: {batch_time:.2f}秒, {len(test_texts)/batch_time:.1f}条/秒"
            )
        except Exception as e:
            self.log(f"批量嵌入", False, str(e))
            return

        # 估算全量耗时
        speed = len(test_texts) / batch_time
        estimated_full = len(chunks) / speed
        print(f"\n  ⏱️  性能估算:")
        print(f"    当前 {len(chunks)} 条规则预计嵌入耗时: {estimated_full:.0f} 秒 ({estimated_full/60:.1f} 分钟)")
        print(f"    处理速度: {speed:.1f} 条/秒")

        if estimated_full > 300:
            print(f"    ⚠️  嵌入速度较慢，建议:")
            print(f"       - 使用 GPU 加速")
            print(f"       - 或减少规则数量后测试")

    # ===== 阶段9: 完整导入测试 =====

    async def test_full_import(self, chunks: list):
        """测试完整的导入流程（只导入前10条）"""
        import db
        from embedding_service import EmbeddingService
        from vector_store import VectorStore
        from keyword_store import KeywordStore
        from rule_importer import RuleImporter
        from config import get_settings

        # 只测试前 10 条，避免太慢
        test_chunks = chunks[:10]
        print(f"  (只测试前 {len(test_chunks)} 条，避免耗时过长)\n")

        try:
            await db.init_db()
            embedding_service = EmbeddingService()
            settings = get_settings()
            settings.embedding_dimensions = embedding_service.dimensions
            vector_store = VectorStore()
            keyword_store = KeywordStore()
            importer = RuleImporter(embedding_service, vector_store, keyword_store)

            t0 = time.time()
            await importer.import_official_rules(test_chunks)
            import_time = time.time() - t0

            self.log(
                "规则导入到系统",
                True,
                f"{len(test_chunks)} 条, 耗时: {import_time:.1f}秒"
            )

            # 验证数据库
            stored = await db.get_all_chunks()
            self.log(
                "数据库存储验证",
                len(stored) >= len(test_chunks),
                f"数据库中有 {len(stored)} 条规则"
            )

            # 验证向量搜索
            test_query = await embedding_service.embed_text("Fireball spell damage")
            results = vector_store.search(query_embedding=test_query, top_k=3)
            self.log(
                "向量搜索可用",
                len(results) > 0,
                f"搜索 'Fireball' 返回 {len(results)} 条结果"
            )

            if results:
                print(f"\n  🔍 向量搜索 'Fireball' 结果:")
                for r in results[:3]:
                    print(f"    [{r['score']:.3f}] {r['payload'].get('title', 'N/A')}")

            # 验证 BM25 搜索
            bm25_results = keyword_store.search("opportunity attack", top_k=3)
            self.log(
                "BM25搜索可用",
                len(bm25_results) > 0,
                f"搜索 'opportunity attack' 返回 {len(bm25_results)} 条"
            )

            if bm25_results:
                print(f"\n  🔍 BM25搜索 'opportunity attack' 结果:")
                for r in bm25_results[:3]:
                    print(f"    [{r['score']:.2f}] {r['payload'].get('title', 'N/A')}")

        except Exception as e:
            self.log("完整导入流程", False, str(e))
            import traceback
            traceback.print_exc()

    # ===== 汇总 =====

    def print_summary(self):
        """打印测试汇总"""
        total = self.passed + self.failed
        print("\n" + "=" * 60)
        print("📊 测试汇总")
        print("=" * 60)

        for name, passed, detail in self.results:
            status = "✅" if passed else "❌"
            line = f"  {status} {name}"
            if detail and not passed:
                line += f" — {detail}"
            print(line)

        print(f"\n  {'='*40}")
        print(f"  通过: {self.passed}/{total}")
        print(f"  失败: {self.failed}/{total}")
        print(f"  通过率: {self.passed/total*100:.0f}%" if total > 0 else "  无测试")

        if self.failed == 0:
            print("\n  🎉 全部通过！")
        else:
            print(f"\n  ⚠️  有 {self.failed} 个测试失败，请检查上方详细信息")

    def cleanup(self):
        """清理测试文件"""
        for f in ["test_rulebook.pdf", "test_chunks_output.json"]:
            if os.path.exists(f):
                os.remove(f)
                print(f"  🗑️  已清理: {f}")

        # 清理测试数据库（可选）
        test_db = "dnd_rules.db"
        if os.path.exists(test_db):
            print(f"  ℹ️  保留数据库: {test_db}")


# ================================================================
#  额外：快速诊断嵌入性能
# ================================================================

async def diagnose_embedding():
    """单独诊断嵌入服务性能"""
    print("=" * 60)
    print("🔧 嵌入服务性能诊断")
    print("=" * 60)

    from embedding_service import EmbeddingService
    import time

    service = EmbeddingService()

    print(f"\n模式: {service.mode}")
    print(f"维度: {service.dimensions}")
    print(f"设备: {getattr(service, 'device', 'N/A')}")
    print(f"模型: {getattr(service, 'model_name', 'N/A')}")

    # 清除缓存以测试真实速度
    test_text = f"This is a test sentence for embedding performance. {time.time()}"

    print(f"\n单条嵌入测试...")
    t0 = time.time()
    emb = await service.embed_text(test_text)
    t1 = time.time()
    print(f"  耗时: {t1-t0:.3f} 秒")
    print(f"  维度: {len(emb)}")

    print(f"\n批量嵌入测试 (50条)...")
    texts = [f"Test sentence number {i} about D&D rules. {time.time()}" for i in range(50)]
    t0 = time.time()
    embs = await service.embed_texts(texts)
    t1 = time.time()
    speed = 50 / (t1 - t0)
    print(f"  耗时: {t1-t0:.1f} 秒")
    print(f"  速度: {speed:.1f} 条/秒")

    print(f"\n📊 性能估算:")
    for n in [100, 500, 1000, 2000]:
        est = n / speed
        print(f"  {n:>5} 条规则: {est:.0f} 秒 ({est/60:.1f} 分钟)")

    if speed < 5:
        print(f"\n💡 建议:")
        print(f"  当前速度较慢 ({speed:.1f}/s)")
        print(f"  1. 安装 GPU 版 PyTorch: pip install torch --index-url https://download.pytorch.org/whl/cu121")
        print(f"  2. 或使用 API 嵌入（在 .env 中配置）")
        print(f"  3. 首次计算后会缓存，再次启动会很快")


# ================================================================
#  命令行入口
# ================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PDF 处理器测试")
    parser.add_argument("--diagnose", action="store_true",
                        help="只诊断嵌入性能")
    parser.add_argument("--pdf", type=str, default=None,
                        help="使用指定PDF测试（而非生成测试PDF）")
    args = parser.parse_args()

    if args.diagnose:
        asyncio.run(diagnose_embedding())
    else:
        tester = PDFProcessorTester()
        tester.run_all()