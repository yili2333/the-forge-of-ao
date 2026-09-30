"""
怪物 Stat Block 解析器

支持两种来源格式：
  1. 主格式（怪物图鉴2025 / 多元宇宙的怪物 等）
     使用 <div class="stat-block"> + stat-block.css 样式
  2. DNDBeyond 格式（字幕组翻译）
     使用 <FONT color=#800000> + <P> 纯文本

GBK/GB2312 编码自动处理。
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from bs4 import BeautifulSoup, Tag

from monster.models import Monster, MonsterAction, MonsterAbilities


# ================================================================
#  工具函数
# ================================================================

def _read_htm(path: Path) -> str:
    """尝试 GBK / UTF-8 读取 HTM 文件"""
    for enc in ("gbk", "gb2312", "utf-8", "utf-8-sig"):
        try:
            return path.read_text(encoding=enc, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="gbk", errors="replace")


def _split_cn_en(text: str) -> tuple[str, str]:
    """
    拆分"中文名EnglishName"或"中文名 English Name"。
    规则：首个连续大写字母开头的英文词之前为中文名，之后为英文名。
    """
    text = text.strip()
    # 匹配：中文/标点 后面紧跟英文大写字母
    m = re.search(r'([A-Z][a-zA-Z\s\-\']+)$', text)
    if m:
        en = m.group(1).strip()
        cn = text[:m.start()].strip()
        return cn, en
    return text, ""


def _parse_cr(text: str) -> tuple[str, int, int]:
    """
    解析 CR 行，如 "3（XP700；PB+2）" 或 "21（XP33,000；巢穴41,000；PB+7）"
    返回 (cr_str, xp, pb)
    """
    cr_str = ""
    xp = 0
    pb = 0
    # CR 值
    m = re.match(r'(\d+/\d+|\d+)', text.strip())
    if m:
        cr_str = m.group(1)
    # XP
    xp_m = re.search(r'XP\s*([\d,，]+)', text)
    if xp_m:
        xp = int(xp_m.group(1).replace(",", "").replace("，", ""))
    # PB
    pb_m = re.search(r'PB\+?(-?\d+)', text)
    if pb_m:
        pb = int(pb_m.group(1))
    return cr_str, xp, pb


def _parse_action_entry(strong_tag: Tag) -> MonsterAction | None:
    """
    从 <strong>名称。</strong>描述<br> 结构中提取一个 MonsterAction。
    """
    raw_name = strong_tag.get_text(strip=True).rstrip("。.")
    if not raw_name:
        return None
    # 提取充能信息
    recharge = ""
    recharge_m = re.search(r'[（(]([充能\d/日天回合]+)[）)]', raw_name)
    if recharge_m:
        recharge = recharge_m.group(0)
        raw_name = raw_name[:recharge_m.start()].strip()

    cn, en = _split_cn_en(raw_name)

    # 描述：strong 后面的同级文本节点 + inline 标签，直到下一个 <br> 或 <strong>
    desc_parts = []
    node = strong_tag.next_sibling
    while node:
        if isinstance(node, Tag):
            if node.name in ("strong", "h6"):
                break
            if node.name == "br":
                # 遇到 br 且已有描述内容则结束
                if desc_parts:
                    break
            else:
                desc_parts.append(node.get_text())
        else:
            text = str(node)
            if text.strip():
                desc_parts.append(text)
        node = node.next_sibling

    description = "".join(desc_parts).strip()

    return MonsterAction(
        name=cn or raw_name,
        name_en=en,
        description=description,
        recharge=recharge,
    )


# ================================================================
#  主格式解析（stat-block div）
# ================================================================

# 能力名中文 → 字段名映射
_ABILITY_MAP = {
    "力量": "str", "敏捷": "dex", "体质": "con",
    "智力": "int_", "感知": "wis", "魅力": "cha",
}

# 信息表行标签映射
_INFO_LABELS = {
    "技能": "skills_raw",
    "抗性": "damage_resistances_raw",
    "易伤": "damage_vulnerabilities_raw",
    "免疫": "damage_immunities_raw",
    "感官": "senses_raw",
    "语言": "languages",
    "装备": "equipment",
    "CR":   "cr_raw",
    "挑战": "cr_raw",   # 部分文件用"挑战"
}

# h6 行动区块中文标题 → 字段名
_SECTION_MAP = {
    "特质": "traits",
    "动作": "actions",
    "附赠动作": "bonus_actions",
    "反应": "reactions",
    "传奇动作": "legendary_actions",
    "巢穴动作": "lair_actions",
    "神话动作": "mythic_actions",
}


def _parse_stat_block(div: Tag, source: str, source_file: str) -> Monster | None:
    """解析单个 <div class="stat-block"> 块"""

    # 1. 名称
    h5 = div.find("h5")
    if not h5:
        return None
    name_cn, name_en = _split_cn_en(h5.get_text(" ", strip=True))
    if not name_cn:
        return None

    monster = Monster(
        name_cn=name_cn,
        name_en=name_en,
        source=source,
        source_file=source_file,
    )

    # 2. 类型行
    sub = div.find("div", class_="sub-line")
    if sub:
        sub_text = sub.get_text(strip=True)
        # "大型龙类（邪恶）" 或 "中型亡灵，中立邪恶"
        parts = re.split(r'[，,]', sub_text, maxsplit=1)
        type_part = parts[0].strip()
        monster.alignment = parts[1].strip() if len(parts) > 1 else ""
        # 拆 size + creature_type
        for size in ("微型", "小型", "中型", "大型", "超大型", "巨型"):
            if type_part.startswith(size):
                monster.size = size
                rest = type_part[len(size):].strip()
                # 可能有子类型 "亡灵（精灵）"
                sub_m = re.match(r'([^（(]+)[（(]([^）)]+)[）)]', rest)
                if sub_m:
                    monster.creature_type = sub_m.group(1).strip()
                    monster.subtype = sub_m.group(2).strip()
                else:
                    monster.creature_type = rest
                break
        else:
            monster.creature_type = type_part

    # 3. 基础数值表（第一个普通 table）
    tables = div.find_all("table")
    if tables:
        first_table = tables[0]
        text = first_table.get_text(" ")
        # AC
        ac_m = re.search(r'AC\s+(\d+)\s*[（(]?([^）)]*)[）)]?', text)
        if ac_m:
            monster.ac = int(ac_m.group(1))
            monster.ac_note = ac_m.group(2).strip()
        # HP
        hp_m = re.search(r'HP\s+(\d+)[（(]([^）)]+)[）)]', text)
        if hp_m:
            monster.hp = int(hp_m.group(1))
            monster.hp_formula = hp_m.group(2).strip()
        elif re.search(r'HP\s+(\d+)', text):
            monster.hp = int(re.search(r'HP\s+(\d+)', text).group(1))
        # Speed
        speed_m = re.search(r'速度\s+(.+?)(?=\s{2,}|$)', text)
        if speed_m:
            monster.speed = speed_m.group(1).strip()
        # Initiative
        init_m = re.search(r'先攻\s+([+-]?\d+)', text)
        if init_m:
            monster.initiative_bonus = int(init_m.group(1))

    # 4. 属性表
    abilities_table = div.find("table", class_="stat-abilities")
    if abilities_table:
        cells = abilities_table.find_all("td")
        # 布局：每6格一行（name, score, mod, save），跳过空格单元格
        ability_cells = [
            c for c in cells
            if c.get("class") and any(
                cls in c.get("class", []) for cls in ("c1", "c2", "c3", "c4")
            )
        ]
        # 按 c1=name, c1=score, c2=mod, c2=save 顺序排列
        i = 0
        while i < len(ability_cells) - 3:
            name_cell = ability_cells[i]
            if "c1" in name_cell.get("class", []) or "c3" in name_cell.get("class", []):
                ability_name = name_cell.get_text(strip=True)
                field = _ABILITY_MAP.get(ability_name)
                if field and i + 1 < len(ability_cells):
                    score_cell = ability_cells[i + 1]
                    try:
                        score = int(score_cell.get_text(strip=True))
                        setattr(monster.abilities, field, score)
                        # 豁免（c2/c4 的第4格）
                        if i + 3 < len(ability_cells):
                            save_cell = ability_cells[i + 3]
                            save_text = save_cell.get_text(strip=True)
                            save_m = re.match(r'([+-]\d+)', save_text)
                            if save_m:
                                base_mod = (score - 10) // 2
                                save_val = int(save_m.group(1))
                                if save_val != base_mod:
                                    short = {
                                        "力量": "str", "敏捷": "dex", "体质": "con",
                                        "智力": "int", "感知": "wis", "魅力": "cha",
                                    }.get(ability_name, ability_name)
                                    monster.saving_throws[short] = save_val
                    except ValueError:
                        pass
                    i += 4
                    continue
            i += 1

    # 5. 信息表（第三个 table，技能/抗性/免疫/感官/语言/CR）
    info_data: dict[str, str] = {}
    for tbl in tables[1:]:
        if "stat-abilities" in (tbl.get("class") or []):
            continue
        for row in tbl.find_all("tr"):
            td = row.find("td")
            if not td:
                continue
            strong = td.find("strong")
            if not strong:
                continue
            label = strong.get_text(strip=True).rstrip("：: ")
            # 值在 strong 之后的文本
            value_parts = []
            for node in strong.next_siblings:
                value_parts.append(
                    node.get_text() if isinstance(node, Tag) else str(node)
                )
            value = "".join(value_parts).strip()
            info_data[label] = value

    # 技能
    skills_text = info_data.get("技能", "")
    if skills_text:
        for part in re.split(r'[，,、]', skills_text):
            m = re.match(r'\s*(.+?)\s*([+-]\d+)\s*$', part.strip())
            if m:
                monster.skills[m.group(1).strip()] = int(m.group(2))

    # 伤害抗性/免疫/易伤
    def _parse_damage_list(text: str) -> tuple[list[str], list[str]]:
        """拆分伤害类型和状态条件（用分号或特定词分隔）"""
        dmg, cond = [], []
        parts = re.split(r'[；;]', text)
        for p in parts:
            p = p.strip()
            if p:
                # 简单判断：中文短语 ≤4 字且无伤害关键词的大概是状态
                dmg.append(p)
        return dmg, cond

    for label, field_prefix in [
        ("抗性", "damage_resistances"),
        ("易伤", "damage_vulnerabilities"),
    ]:
        raw = info_data.get(label, "")
        if raw:
            items = [x.strip() for x in re.split(r'[，,、；;]', raw) if x.strip()]
            setattr(monster, field_prefix, items)

    # 免疫：可能含伤害和状态，用分号分隔
    imm_raw = info_data.get("免疫", "")
    if imm_raw:
        parts = re.split(r'[；;]', imm_raw)
        dmg_imm, cond_imm = [], []
        for p in parts:
            items = [x.strip() for x in re.split(r'[，,、]', p) if x.strip()]
            # 粗略判断：含已知状态关键词则归状态免疫
            state_keywords = {"魅惑", "力竭", "恐慌", "受擒", "麻痹", "石化",
                               "中毒", "倒地", "束缚", "失能", "昏迷", "目盲",
                               "耳聋", "看不见", "听不到"}
            for item in items:
                if any(kw in item for kw in state_keywords):
                    cond_imm.append(item)
                else:
                    dmg_imm.append(item)
        monster.damage_immunities = dmg_imm
        monster.condition_immunities = cond_imm

    # 感官
    senses_raw = info_data.get("感官", "")
    if senses_raw:
        monster.senses = senses_raw
        pp_m = re.search(r'被动察觉\s*(\d+)', senses_raw)
        if pp_m:
            monster.passive_perception = int(pp_m.group(1))

    # 语言
    monster.languages = info_data.get("语言", "")

    # 装备
    monster.equipment = info_data.get("装备", "")

    # CR
    cr_raw = info_data.get("CR", "") or info_data.get("挑战", "")
    if cr_raw:
        monster.cr, monster.xp, monster.proficiency_bonus = _parse_cr(cr_raw)

    # 6. 行动区块（h6 + 跟随的 p）
    # 注意：按关键字长度降序排列，避免"动作"误匹配"传奇动作"/"附赠动作"等长词
    section_map = {
        "附赠动作": "bonus_actions",
        "传奇动作": "legendary_actions",
        "巢穴动作": "lair_actions",
        "神话动作": "mythic_actions",
        "特质": "traits",
        "动作": "actions",
        "反应": "reactions",
    }
    for h6 in div.find_all("h6"):
        h6_text = h6.get_text(strip=True)
        field_name = None
        for key, field in section_map.items():
            if key in h6_text:
                field_name = field
                break
        if not field_name:
            continue

        p = h6.find_next_sibling("p")
        if not p:
            continue

        # 传奇动作前通常有说明文字（首个非 strong 文本）
        if field_name == "legendary_actions":
            desc_texts = []
            for node in p.children:
                if isinstance(node, Tag) and node.name == "strong":
                    break
                desc_texts.append(
                    node.get_text() if isinstance(node, Tag) else str(node)
                )
            monster.legendary_action_desc = "".join(desc_texts).strip()

        actions: list[MonsterAction] = []
        for strong in p.find_all("strong"):
            action = _parse_action_entry(strong)
            if action:
                action.action_type = field_name.rstrip("s")  # 去复数
                actions.append(action)

        setattr(monster, field_name, actions)

    # ---- 有效性校验：必须有 HP 或 CR，否则视为非怪物页面 ----
    if monster.hp == 0 and monster.cr == "":
        return None

    return monster


# ================================================================
#  DNDBeyond 格式解析（简化版）
# ================================================================

def _parse_dndbeyond_block(soup: BeautifulSoup, source: str, source_file: str) -> Monster | None:
    """
    解析 DNDBeyond / 多元宇宙格式的单文件。
    支持两种标签风格：
      A. 英文标签：AC: ... HP: ... CR: ...
      B. 中文标签：护甲等级：... 生命值：... 挑战等级：...（多元宇宙的怪物、巨人之荣耀 等）
    """
    body = soup.find("body")
    if not body:
        return None
    text = body.get_text("\n")

    # 名称：在含 size="5" 的 font 中，或退而求其次使用第一个 color=#800000 的 font
    font_large = soup.find("font", {"color": re.compile(r"800000", re.I), "size": re.compile(r"[45]")})
    font_any = soup.find("font", {"color": re.compile(r"800000", re.I)})
    font = font_large or font_any
    if not font:
        return None
    name_cn, name_en = _split_cn_en(font.get_text(" ", strip=True))
    if not name_cn:
        return None

    monster = Monster(name_cn=name_cn, name_en=name_en,
                      source=source, source_file=source_file)

    # ---- 类型/体型 ----
    type_m = re.search(r'(微型|小型|中型|大型|超大型|巨型)[^\n，,]*([，,].{0,20})?', text)
    if type_m:
        monster.size = type_m.group(1)

    # ---- AC（支持 "护甲等级：14"、"AC 15（天生护甲）"、"AC: 15" 等格式）----
    ac_m = re.search(r'(?:护甲等级|AC)[：:\s]+(\d+)', text)
    if ac_m:
        monster.ac = int(ac_m.group(1))
        ac_note_m = re.search(r'AC[^\d]*\d+\s*[（(]([^）)]+)[）)]', text)
        if ac_note_m:
            monster.ac_note = ac_note_m.group(1).strip()

    # ---- HP（支持 "生命值：337（...）"、"HP 337（...）"、"HP: 337（...）"）----
    hp_m = re.search(
        r'(?:生命值|HP)[：:\s]+(\d+)\s*[（(]([^）)]+)[）)]',
        text,
    )
    if hp_m:
        monster.hp = int(hp_m.group(1))
        monster.hp_formula = hp_m.group(2)
    else:
        hp_m2 = re.search(r'(?:生命值|HP)[：:\s]+(\d+)', text)
        if hp_m2:
            monster.hp = int(hp_m2.group(1))

    # ---- 速度（支持"速度40尺"、"速度：40尺"）----
    speed_m = re.search(r'速度[：:\s]*(.+?)(?:\n|$)', text)
    if speed_m:
        monster.speed = speed_m.group(1).strip()

    # ---- 属性值（中文标签：力量27（+8）敏捷12（+1）…）----
    _ability_cn_map = [
        ("力量", "str"), ("敏捷", "dex"), ("体质", "con"),
        ("智力", "int_"), ("感知", "wis"), ("魅力", "cha"),
    ]
    for cn_label, field in _ability_cn_map:
        m = re.search(rf'{cn_label}(\d+)', text)
        if m:
            setattr(monster.abilities, field, int(m.group(1)))

    # ---- CR（"挑战等级19（22,000XP）"、"挑战等级：20"、"CR: 5"）----
    cr_m = re.search(
        r'(?:挑战等级|战斗等级|CR)[：:\s]*(\d+/\d+|\d+)',
        text,
    )
    if cr_m:
        monster.cr = cr_m.group(1)
        # 提取 XP（紧跟 CR 的括号，如 （22,000XP））
        xp_m = re.search(r'[（(]([\d,，]+)\s*[xX][pP][）)]', text[cr_m.start():cr_m.start()+60])
        if xp_m:
            monster.xp = int(xp_m.group(1).replace(",", "").replace("，", ""))

    # ---- 感官 ----
    sense_m = re.search(r'感官[：:]\s*(.+?)(?:\n|$)', text)
    if sense_m:
        monster.senses = sense_m.group(1).strip()
        pp_m = re.search(r'被动察觉\s*(\d+)', monster.senses)
        if pp_m:
            monster.passive_perception = int(pp_m.group(1))

    # ---- 语言 ----
    lang_m = re.search(r'语言[：:]\s*(.+?)(?:\n|$)', text)
    if lang_m:
        monster.languages = lang_m.group(1).strip()

    # ---- 简单动作解析（<strong> 标签中的技能/动作条目）----
    actions: list = []
    from monster.models import MonsterAction
    for strong in body.find_all("strong"):
        raw_name = strong.get_text(strip=True).rstrip("。.")
        if not raw_name or len(raw_name) > 40:
            continue
        # 排除章节标题（"动作Actions", "传奇动作Legendary Actions"等）
        section_keywords = {"动作", "传奇动作", "附赠动作", "反应", "特质", "巢穴动作"}
        if any(kw in raw_name for kw in section_keywords) and len(raw_name) <= 15:
            continue
        cn, en = _split_cn_en(raw_name)
        if cn:
            # 提取充能
            recharge = ""
            r_m = re.search(r'[（(]充能\d[）)]', raw_name)
            if r_m:
                recharge = r_m.group(0)
            actions.append(MonsterAction(name=cn, name_en=en, description="", recharge=recharge))
    monster.actions = actions

    # 有效性校验
    if monster.hp == 0 and monster.cr == "":
        return None

    return monster


# ================================================================
#  公开接口
# ================================================================

def parse_file(path: Path, source: str = "MM 2024") -> list[Monster]:
    """
    解析单个 HTM 文件，返回其中所有怪物（一个文件可能有多个 stat block）。
    自动识别格式（主格式 vs DNDBeyond）。
    """
    html = _read_htm(path)
    soup = BeautifulSoup(html, "html.parser")
    source_file = str(path.name)

    # 优先尝试主格式
    stat_blocks = soup.find_all("div", class_="stat-block")
    if stat_blocks:
        monsters = []
        for div in stat_blocks:
            m = _parse_stat_block(div, source, source_file)
            if m:
                monsters.append(m)
        return monsters

    # 回退到 DNDBeyond 格式
    m = _parse_dndbeyond_block(soup, source, source_file)
    return [m] if m else []


def parse_directory(
    directory: Path,
    source: str = "MM 2024",
    progress_cb: Callable[[str], None] | None = None,
) -> tuple[list[Monster], list[str]]:
    """
    递归解析目录下所有 HTM 文件。
    返回 (monsters, errors)。
    """
    monsters: list[Monster] = []
    errors: list[str] = []

    htm_files = sorted(directory.rglob("*.htm")) + sorted(directory.rglob("*.html"))
    for path in htm_files:
        try:
            result = parse_file(path, source)
            monsters.extend(result)
            if progress_cb:
                progress_cb(f"  {path.name}: {len(result)} 个怪物")
        except Exception as e:
            errors.append(f"{path.name}: {e}")

    return monsters, errors
