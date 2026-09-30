"""
D&D 术语标准化：中文/缩写/俗称 → 标准英文术语
这是提升检索准确率的关键组件
"""

import re


class DnDTermMapper:
    def __init__(self):
        # 中文 → 英文
        self.zh_to_en = {
            # 核心机制
            "护甲等级": "Armor Class",
            "生命值": "Hit Points",
            "先攻": "Initiative",
            "豁免检定": "Saving Throw",
            "豁免": "Saving Throw",
            "属性检定": "Ability Check",
            "技能检定": "Skill Check",
            "难度等级": "Difficulty Class",
            "熟练加值": "Proficiency Bonus",
            "优势": "Advantage",
            "劣势": "Disadvantage",

            # 战斗
            "借机攻击": "Opportunity Attack",
            "偷袭": "Sneak Attack",
            "攻击检定": "Attack Roll",
            "伤害检定": "Damage Roll",
            "近战攻击": "Melee Attack",
            "远程攻击": "Ranged Attack",
            "额外攻击": "Extra Attack",
            "双持": "Two-Weapon Fighting",
            "双武器战斗": "Two-Weapon Fighting",
            "擒抱": "Grapple",
            "推撞": "Shove",
            "掩护": "Cover",
            "半掩护": "Half Cover",
            "全掩护": "Total Cover",

            # 动作类型
            "动作": "Action",
            "附赠动作": "Bonus Action",
            "反应": "Reaction",
            "移动": "Movement",
            "冲刺": "Dash",
            "撤离": "Disengage",
            "闪避": "Dodge",
            "帮助": "Help",
            "隐藏": "Hide",
            "搜索": "Search",
            "准备": "Ready",

            # 状态
            "目盲": "Blinded",
            "魅惑": "Charmed",
            "耳聋": "Deafened",
            "恐惧": "Frightened",
            "擒抱中": "Grappled",
            "失能": "Incapacitated",
            "隐形": "Invisible",
            "麻痹": "Paralyzed",
            "石化": "Petrified",
            "中毒": "Poisoned",
            "倒地": "Prone",
            "束缚": "Restrained",
            "震慑": "Stunned",
            "昏迷": "Unconscious",
            "力竭": "Exhaustion",

            # 职业
            "野蛮人": "Barbarian",
            "吟游诗人": "Bard",
            "牧师": "Cleric",
            "德鲁伊": "Druid",
            "战士": "Fighter",
            "武僧": "Monk",
            "圣武士": "Paladin",
            "游侠": "Ranger",
            "游荡者": "Rogue",
            "术士": "Sorcerer",
            "邪术师": "Warlock",
            "法师": "Wizard",

            # 施法
            "集中": "Concentration",
            "仪式施法": "Ritual Casting",
            "法术位": "Spell Slot",
            "戏法": "Cantrip",
            "施法": "Spellcasting",

            # 休息
            "长休": "Long Rest",
            "大休": "Long Rest",
            "短休": "Short Rest",
            "小休": "Short Rest",

            # 法术（常见）
            "火球术": "Fireball",
            "火球": "Fireball",
            "魔法飞弹": "Magic Missile",
            "治疗术": "Cure Wounds",
            "治疗创伤": "Cure Wounds",
            "法师之手": "Mage Hand",
            "法师手": "Mage Hand",
            "防护法阵": "Magic Circle",
            "护盾术": "Shield",
            "识破隐形": "See Invisibility",
            "传送术": "Teleport",
            "复活术": "Resurrection",
            "祝福术": "Bless",
            "侦测魔法": "Detect Magic",
        }

        # 缩写 → 全称
        self.abbreviations = {
            "AC": "Armor Class",
            "HP": "Hit Points",
            "DC": "Difficulty Class",
            "OA": "Opportunity Attack",
            "AoO": "Opportunity Attack",
            "BA": "Bonus Action",
            "ST": "Saving Throw",
            "PB": "Proficiency Bonus",
            "ASI": "Ability Score Improvement",
            "STR": "Strength",
            "DEX": "Dexterity",
            "CON": "Constitution",
            "INT": "Intelligence",
            "WIS": "Wisdom",
            "CHA": "Charisma",
            "DM": "Dungeon Master",
            "PC": "Player Character",
            "NPC": "Non-Player Character",
            "PHB": "Player's Handbook",
            "DMG": "Dungeon Master's Guide",
            "MM": "Monster Manual",
        }

        # 构建反向索引供快速查找
        self._all_terms: dict[str, str] = {}
        self._all_terms.update(self.zh_to_en)
        self._all_terms.update(self.abbreviations)
        # 小写版本
        self._lower_map = {k.lower(): v for k, v in self._all_terms.items()}

    def normalize_query(self, query: str) -> str:
        """
        将查询中的中文/缩写术语替换为标准英文
        同时保留原始中文以便向量搜索
        """
        result = query
        found_terms = []

        # 先替换完整的中文术语（长的优先）
        sorted_terms = sorted(self.zh_to_en.keys(), key=len, reverse=True)
        for zh_term in sorted_terms:
            if zh_term in result:
                en_term = self.zh_to_en[zh_term]
                found_terms.append(en_term)
                # 不替换，而是追加（保留中文便于向量匹配）

        # 替换缩写（全大写的）
        for abbr, full in self.abbreviations.items():
            pattern = r'\b' + re.escape(abbr) + r'\b'
            if re.search(pattern, result):
                found_terms.append(full)

        # 追加标准术语到查询末尾
        if found_terms:
            result = result + " | " + " ".join(set(found_terms))

        return result

    def extract_terms(self, query: str) -> list[str]:
        """提取查询中出现的所有 D&D 术语（标准英文形式）"""
        terms = []
        query_lower = query.lower()

        for key, value in self._lower_map.items():
            if key in query_lower:
                terms.append(value)

        return list(set(terms))

    def get_search_keywords(self, query: str) -> list[str]:
        """获取用于关键词搜索的术语列表"""
        terms = self.extract_terms(query)
        # 同时加入原始中文词
        for zh, en in self.zh_to_en.items():
            if zh in query:
                terms.append(zh)
                terms.append(en)
        return list(set(terms))