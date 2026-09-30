"""
D&D 规则书 PDF 处理器
支持:
- 自动识别章节层级结构
- 法术块结构化提取
- 表格提取
- 智能分块（按语义而非固定长度）
- 中英文混合内容
- 交互式配置

使用方式:
    python pdf_processor.py path/to/rulebook.pdf
"""

import re
import os
import sys
import json
import argparse
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.markdown import Markdown

# 项目内部导入
sys.path.insert(0, str(Path(__file__).parent))
from models import RuleChunk, RuleCategory, RuleSource

console = Console()


# ================================================================
#  数据结构
# ================================================================

@dataclass
class PDFSection:
    """从 PDF 中提取的一个章节"""
    title: str
    level: int  # 标题层级 1=章, 2=节, 3=小节
    content: str
    page_start: int
    page_end: int
    parent_titles: list[str] = field(default_factory=list)  # 上级标题链
    children: list["PDFSection"] = field(default_factory=list)
    section_type: str = "text"  # text / spell / table / sidebar


@dataclass
class PDFProcessConfig:
    """PDF 处理配置"""
    # 来源信息
    source_name: str = "PHB 2024"
    source_enum: RuleSource = RuleSource.PHB_2024

    # 页码范围（跳过目录、封面等）
    page_start: int = 1
    page_end: int = -1  # -1 = 最后一页
    skip_pages: list[int] = field(default_factory=list)  # 跳过的页码

    # 标题检测
    title_font_size_min: float = 14.0  # 大于此字号视为标题
    h1_font_size_min: float = 20.0  # 章标题
    h2_font_size_min: float = 16.0  # 节标题
    title_patterns: list[str] = field(default_factory=lambda: [
        r"^chapter\s+\d+",  # Chapter 1, Chapter 2...
        r"^appendix\s+[a-z]",  # Appendix A...
        r"^part\s+\d+",  # Part 1...
    ])

    # 分块策略
    max_chunk_chars: int = 3000  # 单个chunk最大字符数
    min_chunk_chars: int = 100  # 太短的chunk合并到上一个

    # 法术检测
    spell_detection: bool = True
    spell_header_pattern: str = r"^(.+)\n(\d+(?:st|nd|rd|th)-level\s+\w+|cantrip)"

    # 类别自动识别关键词
    category_keywords: dict = field(default_factory=lambda: {
        "spell": ["casting time", "range", "components", "duration",
                  "施法时间", "射程", "成分", "持续时间"],
        "class_feature": ["class feature", "starting at", "beginning at",
                          "at 1st level", "职业特性"],
        "combat": ["attack roll", "damage roll", "hit points",
                   "opportunity attack", "攻击检定", "伤害"],
        "condition": ["condition", "a .+ creature", "状态"],
        "equipment": ["cost", "weight", "properties", "armor class",
                      "价格", "重量", "属性"],
        "feat": ["prerequisite", "feat", "专长", "先决条件"],
        "species_trait": ["species", "trait", "种族", "特征"],
    })


# ================================================================
#  PDF 文本提取
# ================================================================

class PDFExtractor:
    """从 PDF 提取结构化文本"""

    def __init__(self, pdf_path: str, config: PDFProcessConfig):
        self.pdf_path = pdf_path
        self.config = config
        self.doc = fitz.open(pdf_path)
        self.total_pages = len(self.doc)

    def extract_all_pages(self) -> list[dict]:
        """
        提取所有页面的文本块，保留字体大小、位置等信息
        """
        pages_data = []

        start = self.config.page_start - 1  # 0-indexed
        end = self.config.page_end if self.config.page_end > 0 else self.total_pages

        with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console
        ) as progress:
            task = progress.add_task(
                f"📖 提取PDF文本 (第{start + 1}-{end}页)...",
                total=end - start
            )

            for page_num in range(start, end):
                if (page_num + 1) in self.config.skip_pages:
                    progress.advance(task)
                    continue

                page = self.doc[page_num]
                blocks = self._extract_page_blocks(page, page_num + 1)
                pages_data.append({
                    "page_num": page_num + 1,
                    "blocks": blocks,
                })
                progress.advance(task)

        return pages_data

    def _extract_page_blocks(self, page: fitz.Page, page_num: int) -> list[dict]:
        """提取单页的文本块"""
        blocks = []

        # 获取文本块和字体信息
        text_dict = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        for block in text_dict.get("blocks", []):
            if block["type"] != 0:  # 跳过图片块
                continue

            block_text = ""
            block_fonts = []

            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    font_size = span.get("size", 12)
                    font_name = span.get("font", "")
                    is_bold = "bold" in font_name.lower() or "Bold" in font_name

                    line_text += text
                    block_fonts.append({
                        "size": font_size,
                        "bold": is_bold,
                        "font": font_name,
                        "text": text,
                    })

                block_text += line_text + "\n"

            block_text = block_text.strip()
            if not block_text:
                continue

            # 计算主要字体大小（出现最多的）
            if block_fonts:
                sizes = [f["size"] for f in block_fonts if f["text"].strip()]
                main_size = max(set(sizes), key=sizes.count) if sizes else 12
                any_bold = any(f["bold"] for f in block_fonts if f["text"].strip())
            else:
                main_size = 12
                any_bold = False

            blocks.append({
                "text": block_text,
                "font_size": main_size,
                "bold": any_bold,
                "bbox": block["bbox"],  # (x0, y0, x1, y1)
                "page": page_num,
                "fonts": block_fonts,
            })

        return blocks

    def extract_tables(self, page_numbers: list[int] | None = None) -> list[dict]:
        """用 pdfplumber 提取表格"""
        tables = []

        with pdfplumber.open(self.pdf_path) as pdf:
            pages = page_numbers or range(len(pdf.pages))

            for page_idx in pages:
                if page_idx >= len(pdf.pages):
                    continue
                page = pdf.pages[page_idx]
                page_tables = page.extract_tables()

                for table in page_tables:
                    if table and len(table) > 1:  # 至少有表头和一行数据
                        tables.append({
                            "page": page_idx + 1,
                            "headers": table[0],
                            "rows": table[1:],
                            "raw": table,
                        })

        return tables

    def close(self):
        self.doc.close()


# ================================================================
#  章节解析器
# ================================================================

class SectionParser:
    """将提取的文本块解析为层级章节结构"""

    def __init__(self, config: PDFProcessConfig):
        self.config = config

    def parse(self, pages_data: list[dict]) -> list[PDFSection]:
        """解析所有页面数据为章节列表"""
        sections: list[PDFSection] = []
        current_h1 = ""
        current_h2 = ""
        current_h3 = ""
        current_content_lines = []
        current_page_start = 1

        for page_data in pages_data:
            for block in page_data["blocks"]:
                text = block["text"].strip()
                if not text:
                    continue

                heading_level = self._detect_heading_level(block)

                if heading_level > 0:
                    # 保存之前的内容
                    if current_content_lines:
                        title = current_h3 or current_h2 or current_h1 or "Untitled"
                        parent_chain = [t for t in [current_h1, current_h2] if t and t != title]

                        sections.append(PDFSection(
                            title=title,
                            level=self._current_level(current_h1, current_h2, current_h3),
                            content="\n".join(current_content_lines).strip(),
                            page_start=current_page_start,
                            page_end=block["page"],
                            parent_titles=parent_chain,
                        ))
                        current_content_lines = []

                    # 更新标题
                    if heading_level == 1:
                        current_h1 = text
                        current_h2 = ""
                        current_h3 = ""
                    elif heading_level == 2:
                        current_h2 = text
                        current_h3 = ""
                    else:
                        current_h3 = text

                    current_page_start = block["page"]
                else:
                    current_content_lines.append(text)

        # 保存最后一个章节
        if current_content_lines:
            title = current_h3 or current_h2 or current_h1 or "Untitled"
            parent_chain = [t for t in [current_h1, current_h2] if t and t != title]
            sections.append(PDFSection(
                title=title,
                level=self._current_level(current_h1, current_h2, current_h3),
                content="\n".join(current_content_lines).strip(),
                page_start=current_page_start,
                page_end=pages_data[-1]["page_num"] if pages_data else 1,
                parent_titles=parent_chain,
            ))

        return sections

    def _detect_heading_level(self, block: dict) -> int:
        """
        检测文本块是否为标题及其层级
        返回: 0=不是标题, 1=H1, 2=H2, 3=H3
        """
        text = block["text"].strip()
        font_size = block["font_size"]
        is_bold = block["bold"]

        # 太长的不是标题
        if len(text) > 100:
            return 0

        # 纯数字或太短的不是标题
        if len(text) < 2:
            return 0

        # 按字号判断
        if font_size >= self.config.h1_font_size_min:
            return 1
        if font_size >= self.config.h2_font_size_min:
            return 2
        if font_size >= self.config.title_font_size_min and is_bold:
            return 3

        # 按模式匹配
        text_lower = text.lower().strip()
        for pattern in self.config.title_patterns:
            if re.match(pattern, text_lower):
                return 1

        # 全大写短文本通常是标题
        if text.isupper() and len(text) < 50 and len(text.split()) <= 6:
            return 2

        # 粗体且较短的可能是小标题
        if is_bold and len(text) < 60 and font_size >= 12:
            return 3

        return 0

    def _current_level(self, h1, h2, h3) -> int:
        if h3:
            return 3
        if h2:
            return 2
        return 1


# ================================================================
#  法术解析器
# ================================================================

class SpellParser:
    """专门解析法术块"""

    # 法术学派
    SCHOOLS = [
        "abjuration", "conjuration", "divination", "enchantment",
        "evocation", "illusion", "necromancy", "transmutation",
        "防护", "咒法", "预言", "附魔", "塑能", "幻术", "死灵", "变化"
    ]

    def try_parse_spell(self, section: PDFSection) -> RuleChunk | None:
        """尝试将一个章节解析为法术"""
        content = section.content
        title = section.title

        # 检测是否是法术
        spell_info = self._detect_spell_format(title, content)
        if not spell_info:
            return None

        return RuleChunk(
            id=f"pdf-spell-{self._make_id(title)}",
            title=title,
            content=f"{title}\n{content}",
            category=RuleCategory.SPELL,
            source=RuleSource.PHB_2024,
            page=section.page_start,
            parent_context=self._spell_context(spell_info),
            keywords=self._spell_keywords(title, content, spell_info),
            related_rule_ids=[],
        )

    def _detect_spell_format(self, title: str, content: str) -> dict | None:
        """检测内容是否符合法术格式"""
        content_lower = content.lower()

        # 必须包含这些关键字段中的至少3个
        spell_fields = [
            ("casting_time", [
                "casting time", "施法时间",
            ]),
            ("range", [
                "range:", "range：", "射程",
            ]),
            ("components", [
                "components:", "components：", "成分", "component",
            ]),
            ("duration", [
                "duration:", "duration：", "持续时间",
            ]),
        ]

        found = {}
        for field_name, patterns in spell_fields:
            for p in patterns:
                if p in content_lower:
                    found[field_name] = True
                    break

        if len(found) >= 3:
            # 尝试提取法术等级和学派
            level = self._extract_spell_level(content)
            school = self._extract_school(content)
            found["level"] = level
            found["school"] = school
            return found

        return None

    def _extract_spell_level(self, content: str) -> int:
        """提取法术等级"""
        content_lower = content.lower()

        if "cantrip" in content_lower or "戏法" in content_lower:
            return 0

        match = re.search(r"(\d+)(?:st|nd|rd|th)[\s-]*level", content_lower)
        if match:
            return int(match.group(1))

        match = re.search(r"(\d+)\s*(?:环|级)", content)
        if match:
            return int(match.group(1))

        return -1

    def _extract_school(self, content: str) -> str:
        content_lower = content.lower()
        for school in self.SCHOOLS:
            if school in content_lower:
                return school.capitalize()
        return "Unknown"

    def _spell_context(self, info: dict) -> str:
        level = info.get("level", -1)
        school = info.get("school", "Unknown")
        if level == 0:
            return f"Spells > {school} > Cantrip"
        elif level > 0:
            return f"Spells > {school} > Level {level}"
        return f"Spells > {school}"

    def _spell_keywords(self, title: str, content: str, info: dict) -> list[str]:
        keywords = [title.lower()]

        level = info.get("level", -1)
        if level == 0:
            keywords.append("cantrip")
            keywords.append("戏法")
        elif level > 0:
            keywords.append(f"level {level}")
            keywords.append(f"{level}环")

        school = info.get("school", "")
        if school:
            keywords.append(school.lower())

        if "concentration" in content.lower() or "集中" in content:
            keywords.append("concentration")
            keywords.append("集中")

        if "ritual" in content.lower() or "仪式" in content:
            keywords.append("ritual")
            keywords.append("仪式")

        return keywords

    def _make_id(self, title: str) -> str:
        return re.sub(r"[^a-z0-9]", "-", title.lower().strip()).strip("-")


# ================================================================
#  智能分块器
# ================================================================

class SmartChunker:
    """将章节智能切分为合适大小的规则块"""

    def __init__(self, config: PDFProcessConfig):
        self.config = config
        self.spell_parser = SpellParser()

    def chunk_sections(self, sections: list[PDFSection]) -> list[RuleChunk]:
        """将章节列表转换为规则块列表"""
        chunks = []

        for section in sections:
            # 先尝试解析为法术
            if self.config.spell_detection:
                spell_chunk = self.spell_parser.try_parse_spell(section)
                if spell_chunk:
                    chunks.append(spell_chunk)
                    continue

            # 检测类别
            category = self._detect_category(section)

            # 内容太长则拆分
            if len(section.content) > self.config.max_chunk_chars:
                sub_chunks = self._split_long_section(section, category)
                chunks.extend(sub_chunks)
            elif len(section.content) < self.config.min_chunk_chars:
                # 太短的跳过（或者可以选择合并）
                if len(section.content.strip()) > 20:
                    chunks.append(self._section_to_chunk(section, category))
            else:
                chunks.append(self._section_to_chunk(section, category))

        return chunks

    def _section_to_chunk(
            self,
            section: PDFSection,
            category: RuleCategory
    ) -> RuleChunk:
        """将章节转为 RuleChunk"""
        parent_context = " > ".join(section.parent_titles) if section.parent_titles else ""

        content = f"{section.title}\n\n{section.content}"

        return RuleChunk(
            id=f"pdf-{self._make_id(section.title)}-p{section.page_start}",
            title=section.title,
            content=content,
            category=category,
            source=self.config.source_enum,
            page=section.page_start,
            parent_context=parent_context,
            keywords=self._extract_keywords(section),
            related_rule_ids=[],
        )

    def _split_long_section(
            self,
            section: PDFSection,
            category: RuleCategory
    ) -> list[RuleChunk]:
        """将过长的章节按段落边界拆分"""
        chunks = []
        content = section.content

        # 按空行或换行分段
        paragraphs = re.split(r"\n\s*\n", content)

        current_text = ""
        chunk_index = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果加上这段会超长，先保存当前的
            if current_text and len(current_text) + len(para) > self.config.max_chunk_chars:
                chunk_index += 1
                title = f"{section.title} (Part {chunk_index})"

                chunks.append(RuleChunk(
                    id=f"pdf-{self._make_id(section.title)}-p{section.page_start}-{chunk_index}",
                    title=title,
                    content=f"{title}\n\n{current_text}",
                    category=category,
                    source=self.config.source_enum,
                    page=section.page_start,
                    parent_context=" > ".join(section.parent_titles),
                    keywords=self._extract_keywords(section),
                    related_rule_ids=[],
                ))
                current_text = para
            else:
                current_text += "\n\n" + para if current_text else para

        # 保存最后一段
        if current_text.strip():
            chunk_index += 1
            title = f"{section.title}" if chunk_index == 1 else f"{section.title} (Part {chunk_index})"
            chunks.append(RuleChunk(
                id=f"pdf-{self._make_id(section.title)}-p{section.page_start}-{chunk_index}",
                title=title,
                content=f"{title}\n\n{current_text}",
                category=category,
                source=self.config.source_enum,
                page=section.page_start,
                parent_context=" > ".join(section.parent_titles),
                keywords=self._extract_keywords(section),
                related_rule_ids=[],
            ))

        return chunks

    def _detect_category(self, section: PDFSection) -> RuleCategory:
        """基于内容自动识别规则类别"""
        text = (section.title + " " + section.content).lower()
        parent = " ".join(section.parent_titles).lower()

        # 先按父级标题判断
        parent_mapping = {
            "spell": RuleCategory.SPELL,
            "combat": RuleCategory.COMBAT,
            "condition": RuleCategory.CONDITION,
            "equipment": RuleCategory.EQUIPMENT,
            "weapon": RuleCategory.EQUIPMENT,
            "armor": RuleCategory.EQUIPMENT,
            "class": RuleCategory.CLASS_FEATURE,
            "feat": RuleCategory.FEAT,
            "species": RuleCategory.SPECIES_TRAIT,
            "race": RuleCategory.SPECIES_TRAIT,
            "magic item": RuleCategory.MAGIC_ITEM,
        }

        for keyword, cat in parent_mapping.items():
            if keyword in parent:
                return cat

        # 再按内容关键词判断
        for cat_name, keywords in self.config.category_keywords.items():
            match_count = sum(1 for kw in keywords if kw in text)
            if match_count >= 2:
                try:
                    return RuleCategory(cat_name)
                except ValueError:
                    pass

        return RuleCategory.GENERAL_RULE

    def _extract_keywords(self, section: PDFSection) -> list[str]:
        """从章节提取关键词"""
        keywords = [section.title.lower()]

        # 添加父标题
        for p in section.parent_titles:
            keywords.append(p.lower())

        # 提取 D&D 常见术语
        dnd_terms = [
            "advantage", "disadvantage", "proficiency", "saving throw",
            "attack roll", "damage", "hit points", "armor class",
            "spell slot", "cantrip", "concentration", "ritual",
            "action", "bonus action", "reaction", "movement",
            "优势", "劣势", "熟练", "豁免", "攻击", "伤害", "生命值",
        ]

        text_lower = section.content.lower()
        for term in dnd_terms:
            if term in text_lower:
                keywords.append(term)

        return list(set(keywords))

    def _make_id(self, title: str) -> str:
        cleaned = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "-", title.lower().strip())
        cleaned = re.sub(r"-+", "-", cleaned).strip("-")
        return cleaned[:60]


# ================================================================
#  表格处理器
# ================================================================

class TableProcessor:
    """处理 PDF 中的表格"""

    def table_to_chunk(
            self,
            table: dict,
            context_title: str,
            source: RuleSource
    ) -> RuleChunk | None:
        """将表格转为规则块"""
        headers = table.get("headers", [])
        rows = table.get("rows", [])

        if not headers or not rows:
            return None

        # 清理 None
        headers = [str(h or "").strip() for h in headers]

        # 构建 Markdown 格式表格
        lines = []
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

        for row in rows:
            cells = [str(c or "").strip() for c in row]
            # 补齐列数
            while len(cells) < len(headers):
                cells.append("")
            lines.append("| " + " | ".join(cells[:len(headers)]) + " |")

        content = f"{context_title}\n\n" + "\n".join(lines)

        return RuleChunk(
            id=f"pdf-table-{self._make_id(context_title)}-p{table['page']}",
            title=context_title,
            content=content,
            category=RuleCategory.GENERAL_RULE,
            source=source,
            page=table["page"],
            parent_context="Tables",
            keywords=[context_title.lower(), "table", "表格"],
            related_rule_ids=[],
        )

    def _make_id(self, title: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]", "-", title.lower().strip()).strip("-")
        return cleaned[:50]


# ================================================================
#  交互式配置
# ================================================================

class InteractiveConfigurator:
    """交互式引导用户配置 PDF 处理参数"""

    def configure(self, pdf_path: str, total_pages: int) -> PDFProcessConfig:
        """交互式配置"""
        config = PDFProcessConfig()

        console.print(Panel(
            f"📄 文件: {pdf_path}\n📖 总页数: {total_pages}",
            title="PDF 规则书处理器",
            border_style="blue"
        ))

        # 1. 来源名称
        console.print("\n[bold]1. 规则来源[/bold]")
        source_options = {
            "1": ("Player's Handbook 2024", RuleSource.PHB_2024),
            "2": ("Dungeon Master's Guide 2024", RuleSource.DMG_2024),
            "3": ("Monster Manual 2024", RuleSource.MM_2024),
            "4": ("Basic Rules / SRD", RuleSource.BASIC_RULES),
            "5": ("Homebrew / 第三方", RuleSource.HOMEBREW),
        }

        for k, (name, _) in source_options.items():
            console.print(f"  {k}. {name}")

        choice = Prompt.ask("选择来源", choices=list(source_options.keys()), default="1")
        config.source_name, config.source_enum = source_options[choice]

        # 2. 页码范围
        console.print("\n[bold]2. 页码范围[/bold]")
        config.page_start = IntPrompt.ask("起始页码", default=1)
        end = IntPrompt.ask(f"结束页码 (输入 0 = 最后一页即{total_pages})", default=0)
        config.page_end = end if end > 0 else total_pages

        skip = Prompt.ask(
            "需要跳过的页码 (逗号分隔, 如 '1,2,3', 留空=不跳过)",
            default=""
        )
        if skip.strip():
            config.skip_pages = [int(p.strip()) for p in skip.split(",") if p.strip().isdigit()]

        # 3. 标题检测
        console.print("\n[bold]3. 标题检测参数[/bold]")
        if Confirm.ask("是否调整标题检测的字号阈值？", default=False):
            config.h1_font_size_min = float(Prompt.ask("H1 最小字号", default="20"))
            config.h2_font_size_min = float(Prompt.ask("H2 最小字号", default="16"))
            config.title_font_size_min = float(Prompt.ask("H3 最小字号(需粗体)", default="14"))

        # 4. 分块大小
        console.print("\n[bold]4. 分块策略[/bold]")
        config.max_chunk_chars = IntPrompt.ask("单块最大字符数", default=3000)
        config.min_chunk_chars = IntPrompt.ask("单块最小字符数(更小的会被跳过)", default=100)

        # 5. 法术检测
        config.spell_detection = Confirm.ask("\n是否启用法术自动识别？", default=True)

        console.print(Panel(
            f"来源: {config.source_name}\n"
            f"页码: {config.page_start} - {config.page_end}\n"
            f"跳过: {config.skip_pages or '无'}\n"
            f"分块: {config.min_chunk_chars} - {config.max_chunk_chars} 字符\n"
            f"法术检测: {'✅' if config.spell_detection else '❌'}",
            title="✅ 配置确认",
            border_style="green"
        ))

        return config


# ================================================================
#  交叉引用构建器
# ================================================================

class CrossReferenceBuilder:
    """在所有 chunks 之间建立交叉引用"""

    # D&D 核心术语（出现在其他规则中时自动关联）
    CORE_TERMS = {
        "advantage": None, "disadvantage": None,
        "proficiency bonus": None, "proficiency": None,
        "armor class": None, "ac": None,
        "saving throw": None, "attack roll": None,
        "hit points": None, "hp": None,
        "spell slot": None, "concentration": None,
        "opportunity attack": None,
        "bonus action": None, "reaction": None,
        "incapacitated": None, "prone": None,
        "blinded": None, "charmed": None, "frightened": None,
        "grappled": None, "invisible": None, "paralyzed": None,
        "petrified": None, "poisoned": None, "restrained": None,
        "stunned": None, "unconscious": None, "exhaustion": None,
    }

    def build_references(self, chunks: list[RuleChunk]) -> list[RuleChunk]:
        """扫描所有 chunks，建立交叉引用"""
        # 1. 建立 title → id 的索引
        title_to_id = {}
        for chunk in chunks:
            title_lower = chunk.title.lower().strip()
            title_to_id[title_lower] = chunk.id

            # 同时索引简短版本
            # "Extra Attack (Fighter)" → "extra attack"
            simple = re.sub(r"\s*\(.*\)", "", title_lower).strip()
            if simple != title_lower:
                title_to_id[simple] = chunk.id

        # 2. 扫描每个 chunk 的内容，找引用
        for chunk in chunks:
            content_lower = chunk.content.lower()
            refs = set(chunk.related_rule_ids)

            for title, cid in title_to_id.items():
                if cid == chunk.id:
                    continue
                if len(title) < 3:
                    continue
                if title in content_lower:
                    refs.add(cid)

            chunk.related_rule_ids = list(refs)[:10]  # 最多10个引用

        console.print(f"   🔗 交叉引用: 共建立 {sum(len(c.related_rule_ids) for c in chunks)} 个链接")
        return chunks


# ================================================================
#  主流程
# ================================================================

class PDFRuleProcessor:
    """PDF 规则书处理主流程"""

    def __init__(self, pdf_path: str, interactive: bool = True):
        self.pdf_path = pdf_path
        self.interactive = interactive

    def process(self) -> list[RuleChunk]:
        """处理 PDF 并返回规则块列表"""

        # 1. 打开 PDF 获取基础信息
        doc = fitz.open(self.pdf_path)
        total_pages = len(doc)
        doc.close()

        # 2. 配置
        if self.interactive:
            configurator = InteractiveConfigurator()
            config = configurator.configure(self.pdf_path, total_pages)
        else:
            config = PDFProcessConfig()
            config.page_end = total_pages

        # 3. 提取文本
        console.print("\n[bold]📖 第1步: 提取 PDF 文本...[/bold]")
        extractor = PDFExtractor(self.pdf_path, config)
        pages_data = extractor.extract_all_pages()

        # 统计
        total_blocks = sum(len(p["blocks"]) for p in pages_data)
        console.print(f"   提取了 {len(pages_data)} 页, {total_blocks} 个文本块")

        # 4. 解析章节
        console.print("\n[bold]📋 第2步: 解析章节结构...[/bold]")
        parser = SectionParser(config)
        sections = parser.parse(pages_data)
        console.print(f"   识别了 {len(sections)} 个章节")

        # 显示章节预览
        if self.interactive and sections:
            self._preview_sections(sections)

        # 5. 提取表格
        console.print("\n[bold]📊 第3步: 提取表格...[/bold]")
        tables = extractor.extract_tables()
        console.print(f"   发现 {len(tables)} 个表格")
        extractor.close()

        # 6. 智能分块
        console.print("\n[bold]✂️  第4步: 智能分块...[/bold]")
        chunker = SmartChunker(config)
        chunks = chunker.chunk_sections(sections)

        # 添加表格 chunks
        table_processor = TableProcessor()
        for i, table in enumerate(tables):
            table_title = f"Table (Page {table['page']}, #{i + 1})"
            table_chunk = table_processor.table_to_chunk(table, table_title, config.source_enum)
            if table_chunk:
                chunks.append(table_chunk)

        console.print(f"   生成了 {len(chunks)} 个规则块")

        # 7. 建立交叉引用
        console.print("\n[bold]🔗 第5步: 建立交叉引用...[/bold]")
        ref_builder = CrossReferenceBuilder()
        chunks = ref_builder.build_references(chunks)

        # 8. 统计和预览
        self._show_stats(chunks)

        if self.interactive:
            self._preview_chunks(chunks)

        return chunks

    def _preview_sections(self, sections: list[PDFSection]):
        """预览识别到的章节"""
        table = Table(title="章节预览 (前20个)")
        table.add_column("层级", style="cyan", width=4)
        table.add_column("标题", style="green")
        table.add_column("页码", style="yellow", width=6)
        table.add_column("内容长度", style="magenta", width=8)
        table.add_column("父级", style="dim")

        for section in sections[:20]:
            indent = "  " * (section.level - 1)
            table.add_row(
                f"H{section.level}",
                f"{indent}{section.title[:50]}",
                str(section.page_start),
                str(len(section.content)),
                " > ".join(section.parent_titles)[:40] if section.parent_titles else "-"
            )

        if len(sections) > 20:
            table.add_row("...", f"...还有 {len(sections) - 20} 个章节", "", "", "")

        console.print(table)

    def _preview_chunks(self, chunks: list[RuleChunk]):
        """预览生成的规则块"""
        console.print("\n[bold]📝 规则块预览 (前10个):[/bold]")

        for chunk in chunks[:10]:
            preview = chunk.content[:150].replace("\n", " ")
            if len(chunk.content) > 150:
                preview += "..."

            cat_color = {
                "spell": "magenta", "combat": "red", "condition": "yellow",
                "class_feature": "blue", "equipment": "green",
            }.get(chunk.category.value, "white")

            console.print(f"\n  [{cat_color}][{chunk.category.value}][/{cat_color}] "
                          f"[bold]{chunk.title}[/bold] (p.{chunk.page})")
            console.print(f"  {preview}")
            console.print(f"  [dim]Keywords: {', '.join(chunk.keywords[:5])}[/dim]")

    def _show_stats(self, chunks: list[RuleChunk]):
        """显示统计信息"""
        table = Table(title="📊 规则块统计")
        table.add_column("类别", style="cyan")
        table.add_column("数量", style="green", justify="right")
        table.add_column("平均长度", style="yellow", justify="right")

        categories = {}
        for c in chunks:
            cat = c.category.value
            if cat not in categories:
                categories[cat] = {"count": 0, "total_len": 0}
            categories[cat]["count"] += 1
            categories[cat]["total_len"] += len(c.content)

        for cat, info in sorted(categories.items(), key=lambda x: -x[1]["count"]):
            avg_len = info["total_len"] // info["count"]
            table.add_row(cat, str(info["count"]), f"{avg_len} chars")

        table.add_row(
            "[bold]合计[/bold]",
            f"[bold]{len(chunks)}[/bold]",
            ""
        )

        console.print(table)


# ================================================================
#  导出和导入
# ================================================================

def save_chunks_to_json(chunks: list[RuleChunk], output_path: str):
    """保存规则块为 JSON 文件"""
    data = [chunk.model_dump() for chunk in chunks]
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    console.print(f"\n💾 已保存 {len(chunks)} 条规则到 [bold]{output_path}[/bold]")


def load_chunks_from_json(json_path: str) -> list[RuleChunk]:
    """从 JSON 文件加载规则块"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [RuleChunk(**item) for item in data]


async def import_chunks_to_system(chunks: list[RuleChunk]):
    """将规则块导入到系统中"""
    from embedding_service import EmbeddingService
    from vector_store import VectorStore
    from keyword_store import KeywordStore
    from rule_importer import RuleImporter
    from config import get_settings
    import db

    console.print("\n[bold]🚀 导入规则到系统...[/bold]")

    await db.init_db()

    embedding_service = EmbeddingService()
    settings = get_settings()
    settings.embedding_dimensions = embedding_service.dimensions

    vector_store = VectorStore()
    keyword_store = KeywordStore()
    importer = RuleImporter(embedding_service, vector_store, keyword_store)

    # 分批导入
    batch_size = 30
    with Progress(console=console) as progress:
        task = progress.add_task("导入中...", total=len(chunks))

        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            await importer.import_official_rules(batch)
            progress.advance(task, len(batch))

    console.print(f"✅ 成功导入 {len(chunks)} 条规则！")


# ================================================================
#  命令行入口
# ================================================================

def main():
    parser = argparse.ArgumentParser(
        description="D&D 规则书 PDF 处理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 交互模式（推荐首次使用）
  python pdf_processor.py rulebook.pdf

  # 处理并直接导入系统
  python pdf_processor.py rulebook.pdf --import

  # 只导出JSON不导入
  python pdf_processor.py rulebook.pdf --output rules.json

  # 非交互模式（自动参数）
  python pdf_processor.py rulebook.pdf --auto --pages 10-350

  # 导入已处理的JSON文件
  python pdf_processor.py --load rules.json --import
        """
    )

    parser.add_argument("pdf_path", nargs="?", help="PDF 文件路径")
    parser.add_argument("--output", "-o", help="输出 JSON 文件路径", default=None)
    parser.add_argument("--import", "-i", dest="do_import", action="store_true",
                        help="处理后直接导入系统")
    parser.add_argument("--auto", action="store_true", help="非交互模式")
    parser.add_argument("--pages", help="页码范围，如 '10-350'", default=None)
    parser.add_argument("--load", help="从已有 JSON 文件加载（跳过PDF处理）", default=None)
    parser.add_argument("--source", help="规则来源: phb2024/dmg2024/mm2024/basic/homebrew",
                        default=None)

    args = parser.parse_args()

    # 从 JSON 加载模式
    if args.load:
        console.print(f"📂 从 JSON 加载: {args.load}")
        chunks = load_chunks_from_json(args.load)
        console.print(f"   加载了 {len(chunks)} 条规则")

        if args.do_import:
            import asyncio
            asyncio.run(import_chunks_to_system(chunks))
        return

    # PDF 处理模式
    if not args.pdf_path:
        parser.print_help()
        return

    if not os.path.exists(args.pdf_path):
        console.print(f"[red]❌ 文件不存在: {args.pdf_path}[/red]")
        return

    # 处理 PDF
    processor = PDFRuleProcessor(
        pdf_path=args.pdf_path,
        interactive=not args.auto
    )

    chunks = processor.process()

    # 保存 JSON
    if args.output:
        output_path = args.output
    else:
        base_name = Path(args.pdf_path).stem
        # 统一存储到 src/data/imports/pdf/ 目录
        output_dir = Path(__file__).parent / "data" / "imports" / "pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{base_name}_rules.json"

    save_chunks_to_json(chunks, output_path)

    # 导入系统
    if args.do_import:
        import asyncio
        asyncio.run(import_chunks_to_system(chunks))
    else:
        console.print(f"\n💡 要导入系统，运行:")
        console.print(f"   python pdf_processor.py --load {output_path} --import")


if __name__ == "__main__":
    main()