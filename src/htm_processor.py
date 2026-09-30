"""
D&D 规则书 HTM/HTML 处理器

支持从 GitHub 开源项目提供的 HTML 格式规则书（PHB 2024、MM 2024 等）导入规则。

常见来源格式:
  - 单个大 HTML 文件（整本书在一个文件里，用 h1/h2/h3 划分章节）
  - 目录形式（每章/每物种/每法术一个 HTML 文件）

能力:
  - 自动按 heading 级别切分章节并维护父标题链
  - 检测法术块（Casting Time / Range / Components / Duration）
  - 检测怪物属性块（Armor Class / Hit Points / Speed / Challenge）
  - 表格转纯文本（保留列头和行）
  - 忽略 nav / aside / footer / script / style 等噪声节点
  - 可配置：最大/最小 chunk 大小、切分 heading 级别、跳过的 CSS class
  - CLI 工具（python htm_processor.py <path>）

使用方式:
    from htm_processor import HTMProcessor, HTMProcessConfig
    from models import RuleSource

    chunks = HTMProcessor.process_file(
        "path/to/phb2024.html",
        HTMProcessConfig(source_name="PHB 2024", source_enum=RuleSource.PHB_2024)
    )
    # chunks: list[RuleChunk]

    # 或处理目录
    chunks = HTMProcessor.process_directory("path/to/rules_dir/")
"""

from __future__ import annotations

import re
import sys
import json
import uuid
import hashlib
import argparse
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup, Tag, NavigableString

sys.path.insert(0, str(Path(__file__).parent))
from models import RuleChunk, RuleCategory, RuleSource


# ================================================================
#  数据结构
# ================================================================

@dataclass
class HTMSection:
    """从 HTML 中提取的一个语义节"""
    title: str
    level: int               # 标题级别 1=h1, 2=h2, 3=h3, 4=h4
    content: str             # 纯文本内容（表格已转换）
    parent_titles: list[str] = field(default_factory=list)
    section_type: str = "text"   # text | spell | monster | table | sidebar
    source_file: str = ""
    anchor: str = ""         # href anchor (id 属性)


@dataclass
class HTMProcessConfig:
    """HTM 处理配置"""
    # 来源信息
    source_name: str = "PHB 2024"
    source_enum: RuleSource = RuleSource.PHB_2024
    edition: str = "PHB 2024"

    # 切分配置：这些 heading 级别作为 chunk 边界
    # [1,2,3,4] 适用于大多数 D&D 规则书——法术文件用 h4 作每个法术的标题
    split_at_levels: list[int] = field(default_factory=lambda: [1, 2, 3, 4])

    # 分块大小
    max_chunk_chars: int = 2500
    min_chunk_chars: int = 80

    # 噪声过滤
    skip_tags: list[str] = field(default_factory=lambda: [
        "nav", "aside", "footer", "header", "script", "style",
        "noscript", "iframe", "button", "form",
    ])
    skip_classes: list[str] = field(default_factory=lambda: [
        "toc", "table-of-contents", "navigation", "breadcrumb",
        "sidebar-nav", "page-nav", "footnote",
    ])
    skip_ids: list[str] = field(default_factory=lambda: [
        "toc", "nav", "navigation", "sidebar",
    ])

    # 类别自动识别关键词（大小写不敏感）
    category_keywords: dict[str, list[str]] = field(default_factory=lambda: {
        "spell": [
            "casting time", "range:", "components:", "duration:",
            "spell attack", "saving throw",
            "施法时间", "施法距离", "成分", "持续时间",
        ],
        "monster": [
            "armor class", "hit points", "speed:", "challenge",
            "str ", "dex ", "con ", "int ", "wis ", "cha ",
            "damage immunities", "condition immunities",
            "护甲等级", "生命值", "速度", "挑战等级",
        ],
        "class_feature": [
            "at 1st level", "at 2nd level", "starting at", "beginning at",
            "class feature", "subclass feature",
            "职业特性", "子职业",
        ],
        "combat": [
            "attack roll", "damage roll", "hit points", "initiative",
            "opportunity attack", "grappled", "restrained",
            "攻击检定", "伤害", "主动权",
        ],
        "condition": [
            "a blinded creature", "a charmed creature", "a frightened creature",
            "while prone", "while grappled",
            "受到这个状态", "持有这个状态",
        ],
        "equipment": [
            "cost:", "weight:", "armor class (ac)", "damage:", "properties:",
            "价格", "重量", "伤害骰", "属性",
        ],
        "feat": [
            "prerequisite:", "4th level", "feat",
            "专长", "先决条件",
        ],
        "species_trait": [
            "creature type:", "size:", "speed:", "life span",
            "物种特性", "种族特性",
        ],
    })


# ================================================================
#  HTML 解析器
# ================================================================

class HTMExtractor:
    """
    从单个 HTML 文件提取章节列表。
    按 heading 标签切分，维护父标题链，处理表格，过滤噪声。
    """

    HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self, config: HTMProcessConfig):
        self.config = config

    def extract(self, html_content: str, source_file: str = "") -> list[HTMSection]:
        soup = BeautifulSoup(html_content, "html.parser")

        # 从 <title> 标签提取文档标题，作为"无 heading 时"的备用文档名
        title_tag = soup.find("title")
        doc_title = title_tag.get_text(strip=True) if title_tag else ""

        # 删除噪声节点
        self._strip_noise(soup)

        # 找到内容根节点（article > main > body）
        root = (
            soup.find("article")
            or soup.find("main")
            or soup.find("body")
            or soup
        )

        return self._extract_sections(root, source_file, doc_title=doc_title)

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        """删除导航、脚本、样式等噪声"""
        for tag in self.config.skip_tags:
            for el in soup.find_all(tag):
                el.decompose()

        for cls in self.config.skip_classes:
            for el in soup.find_all(class_=re.compile(cls, re.I)):
                el.decompose()

        for id_ in self.config.skip_ids:
            el = soup.find(id=re.compile(rf"^{re.escape(id_)}$", re.I))
            if el:
                el.decompose()

    def _extract_sections(
        self, root: Tag, source_file: str, doc_title: str = ""
    ) -> list[HTMSection]:
        """
        遍历 root 下的节点，按目标 heading 级别切分章节。
        非切分点的 heading（如 h5/h6）作为内容的一部分。

        doc_title: 从 <title> 标签提取的文档标题，用作无 heading 时的备用名。
        """
        cfg = self.config
        split_levels = set(cfg.split_at_levels)

        sections: list[HTMSection] = []

        # 标题栈：level → title
        title_stack: list[tuple[int, str]] = []  # (level, text)
        # 优先用 doc_title，其次用 source_file，最后兜底 "Document"
        initial_title = doc_title or source_file or "Document"
        current_title: str = initial_title
        current_level: int = 0
        current_anchor: str = ""
        content_parts: list[str] = []

        def flush_section():
            nonlocal current_title, current_level, current_anchor, content_parts
            # 段落间用双换行，使 _split_long 能按段落边界切分
            text = "\n\n".join(p.strip() for p in content_parts if p.strip())
            if text or current_level > 0:
                parents = [t for _, t in title_stack
                           if t != current_title]
                sections.append(HTMSection(
                    title=current_title,
                    level=current_level,
                    content=text,
                    parent_titles=parents,
                    source_file=source_file,
                    anchor=current_anchor,
                ))
            content_parts = []
            current_anchor = ""

        def heading_level(tag: Tag) -> int | None:
            name = tag.name.lower() if tag.name else ""
            if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                return int(name[1])
            return None

        def tag_text(el: Tag) -> str:
            return el.get_text(separator=" ", strip=True)

        def process_table(table_tag: Tag) -> str:
            rows = []
            headers = []
            # 表头
            for th in table_tag.find_all("th"):
                headers.append(th.get_text(strip=True))
            if headers:
                rows.append(" | ".join(headers))
                rows.append("-" * (len(rows[0]) + 4))
            # 数据行
            for tr in table_tag.find_all("tr"):
                cells = [td.get_text(strip=True) for td in tr.find_all("td")]
                if cells:
                    rows.append(" | ".join(cells))
            return "\n".join(rows)

        def walk(node: Tag) -> None:
            nonlocal current_title, current_level, current_anchor, content_parts

            if not hasattr(node, "children"):
                return

            for child in list(node.children):
                if isinstance(child, NavigableString):
                    text = str(child).strip()
                    if text:
                        content_parts.append(text)
                    continue

                if not hasattr(child, "name") or not child.name:
                    continue

                tag_name = child.name.lower()
                hlevel = heading_level(child)

                if hlevel is not None and hlevel in split_levels:
                    # 保存当前积累的内容
                    flush_section()

                    # 维护标题栈
                    title_stack_copy = [
                        (lvl, ttl) for lvl, ttl in title_stack
                        if lvl < hlevel
                    ]
                    title_stack.clear()
                    title_stack.extend(title_stack_copy)

                    new_title = tag_text(child)
                    title_stack.append((hlevel, new_title))
                    current_title = new_title
                    current_level = hlevel
                    current_anchor = child.get("id", "")

                elif tag_name == "table":
                    content_parts.append(process_table(child))

                elif tag_name in ("ul", "ol"):
                    items = []
                    for li in child.find_all("li", recursive=False):
                        items.append(f"• {tag_text(li)}")
                    if items:
                        content_parts.append("\n".join(items))

                elif tag_name in ("p", "div", "section", "article"):
                    # p/div 直接取文本，section/article 递归
                    if tag_name in ("section", "article"):
                        walk(child)
                    else:
                        text = tag_text(child)
                        if text:
                            content_parts.append(text)

                elif tag_name in ("blockquote", "pre", "code"):
                    text = child.get_text(strip=True)
                    if text:
                        content_parts.append(f"[{tag_name.upper()}] {text}")

                elif hlevel is not None:
                    # heading 不在切分级别内 → 当内容子标题处理
                    text = tag_text(child)
                    if text:
                        content_parts.append(f"\n### {text}")
                else:
                    # 其余块级标签递归
                    walk(child)

        walk(root)
        flush_section()

        # 过滤掉纯空白的节
        return [s for s in sections if s.title.strip() or s.content.strip()]


# ================================================================
#  分类检测
# ================================================================

def detect_category(title: str, content: str, cfg: HTMProcessConfig) -> RuleCategory:
    """
    根据标题和内容关键词自动判断 RuleCategory。
    顺序很重要：spell > monster > class_feature > combat > condition > equipment > feat > species_trait > general
    """
    combined = (title + "\n" + content).lower()

    # (keyword_group, category, min_matches)
    # min_matches > 1 防止单个通用词误判（如 "armor class" 同时出现在装备和怪物里）
    kw_map: list[tuple[str, RuleCategory, int]] = [
        ("spell",          RuleCategory.SPELL,         2),  # 需要施法时间+其他至少2项
        ("monster",        RuleCategory.GENERAL_RULE,  3),  # 需要AC+HP+Speed+CR里至少3项
        ("class_feature",  RuleCategory.CLASS_FEATURE, 1),
        ("combat",         RuleCategory.COMBAT,        1),
        ("condition",      RuleCategory.CONDITION,     1),
        ("equipment",      RuleCategory.EQUIPMENT,     1),
        ("feat",           RuleCategory.FEAT,          1),
        ("species_trait",  RuleCategory.SPECIES_TRAIT, 1),
    ]

    for key, cat, min_matches in kw_map:
        keywords = cfg.category_keywords.get(key, [])
        matched = sum(1 for kw in keywords if kw.lower() in combined)
        if matched >= min_matches:
            return cat

    return RuleCategory.GENERAL_RULE


def detect_section_type(section: HTMSection) -> str:
    """
    精细判断 section 类型。
    spell / monster / table / sidebar / text
    """
    combined = (section.title + "\n" + section.content).lower()

    spell_signals = ["casting time", "components:", "duration:", "施法时间"]
    monster_signals = ["armor class", "hit points", "speed:", "challenge", "护甲等级"]
    table_signals = [" | "]

    if sum(1 for s in spell_signals if s in combined) >= 2:
        return "spell"
    if sum(1 for s in monster_signals if s in combined) >= 3:
        return "monster"
    if section.content.count(" | ") > 3:
        return "table"
    return "text"


# ================================================================
#  关键词提取
# ================================================================

_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "to", "is", "it",
    "for", "on", "at", "by", "as", "be", "with", "this", "that",
    "can", "you", "your", "its", "are", "has", "have", "from",
}


def extract_keywords(title: str, content: str, max_kw: int = 12) -> list[str]:
    """
    从标题和内容中提取关键词。
    策略：标题词全保留，内容取出现频率最高的非停用词。
    """
    keywords: list[str] = []

    # 标题词（过滤太短的）
    title_words = re.findall(r"[A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff']*", title)
    for w in title_words:
        if len(w) >= 3 and w.lower() not in _STOPWORDS:
            keywords.append(w)

    # 内容词频
    content_words = re.findall(r"[A-Za-z\u4e00-\u9fff]{3,}", content)
    freq: dict[str, int] = {}
    for w in content_words:
        lw = w.lower()
        if lw not in _STOPWORDS and len(lw) >= 3:
            freq[lw] = freq.get(lw, 0) + 1

    top = sorted(freq.items(), key=lambda x: -x[1])[:max_kw]
    for w, _ in top:
        if w not in [k.lower() for k in keywords]:
            keywords.append(w)

    # 去重，保留原大小写
    seen: set[str] = set()
    result: list[str] = []
    for kw in keywords[:max_kw]:
        if kw.lower() not in seen:
            seen.add(kw.lower())
            result.append(kw)

    return result


# ================================================================
#  分块器
# ================================================================

class HTMChunker:
    """
    把 HTMSection 列表转换为 RuleChunk 列表。
    主要工作：
    1. 太短的 section 合并到上一个（同级 parent 时）
    2. 太长的 section 在段落边界分裂
    3. 填充 RuleChunk 各字段
    """

    def __init__(self, config: HTMProcessConfig):
        self.config = config

    def chunk(self, sections: list[HTMSection]) -> list[RuleChunk]:
        merged = self._merge_short(sections)
        chunks: list[RuleChunk] = []
        for sec in merged:
            if not sec.content.strip():
                continue  # skip title-only sections with no content
            parts = self._split_long(sec)
            for part in parts:
                chunks.append(self._to_chunk(part))
        return chunks

    def _merge_short(self, sections: list[HTMSection]) -> list[HTMSection]:
        """把内容过短（< min_chunk_chars）的 section 合并到上一个 section"""
        min_c = self.config.min_chunk_chars
        result: list[HTMSection] = []

        for sec in sections:
            if (result
                    and len(sec.content) < min_c
                    and result[-1].level <= sec.level):
                # 合并：追加到上一个 section 的内容
                prev = result[-1]
                combined_content = (
                    prev.content.rstrip()
                    + ("\n\n" if prev.content else "")
                    + (f"**{sec.title}**\n" if sec.title != prev.title else "")
                    + sec.content
                )
                result[-1] = HTMSection(
                    title=prev.title,
                    level=prev.level,
                    content=combined_content,
                    parent_titles=prev.parent_titles,
                    section_type=prev.section_type,
                    source_file=prev.source_file,
                    anchor=prev.anchor,
                )
            else:
                result.append(sec)

        return result

    def _split_long(self, sec: HTMSection) -> list[HTMSection]:
        """
        把内容过长的 section 在段落边界处分裂。
        如果单个段落仍然超长，再在句子边界处分裂。
        """
        max_c = self.config.max_chunk_chars
        if len(sec.content) <= max_c:
            return [sec]

        # 第一级：段落分裂
        paragraphs = re.split(r"\n{2,}", sec.content)

        # 如果内容没有双换行（如单段超长文本），也按单换行尝试
        if len(paragraphs) == 1 and len(sec.content) > max_c:
            paragraphs = re.split(r"\n", sec.content)

        # 对每个段落，若还超长则在句子边界分裂（中英文标点均支持）
        fine_paras: list[str] = []
        for para in paragraphs:
            if len(para) <= max_c:
                fine_paras.append(para)
            else:
                # 中英文句子边界：. ! ? 。！？ 后跟空格或下一字
                sentences = re.split(r"(?<=[.!?。！？])\s*", para)
                buf = ""
                for sent in sentences:
                    if buf and len(buf) + len(sent) + 1 > max_c:
                        fine_paras.append(buf.strip())
                        buf = sent
                    else:
                        buf = (buf + sent) if buf else sent
                if buf:
                    fine_paras.append(buf.strip())

        # 最终兜底：如果仍有超长（无任何分句点），强制按字符数硬截
        hard_capped: list[str] = []
        for para in fine_paras:
            if len(para) <= max_c:
                hard_capped.append(para)
            else:
                for i in range(0, len(para), max_c):
                    part = para[i: i + max_c].strip()
                    if part:
                        hard_capped.append(part)
        fine_paras = hard_capped

        parts: list[HTMSection] = []
        current_paras: list[str] = []
        current_len = 0
        chunk_idx = 0

        def _make_section(paras: list[str], idx: int) -> HTMSection:
            suffix = f" (续 {idx})" if idx > 0 else ""
            return HTMSection(
                title=sec.title + suffix,
                level=sec.level,
                content="\n\n".join(paras),
                parent_titles=sec.parent_titles,
                section_type=sec.section_type,
                source_file=sec.source_file,
                anchor=sec.anchor,
            )

        for para in fine_paras:
            if current_paras and current_len + len(para) > max_c:
                parts.append(_make_section(current_paras, chunk_idx))
                current_paras = [para]
                current_len = len(para)
                chunk_idx += 1
            else:
                current_paras.append(para)
                current_len += len(para)

        if current_paras:
            parts.append(_make_section(current_paras, chunk_idx))

        return parts

    def _to_chunk(self, sec: HTMSection) -> RuleChunk:
        cfg = self.config
        category = detect_category(sec.title, sec.content, cfg)
        keywords = extract_keywords(sec.title, sec.content)
        section_type = detect_section_type(sec)

        content_hash = hashlib.md5(
            (sec.title + sec.content).encode("utf-8")
        ).hexdigest()[:16]

        parent_ctx = " > ".join(sec.parent_titles) if sec.parent_titles else ""

        return RuleChunk(
            id=f"htm-{uuid.uuid4().hex[:10]}",
            title=sec.title,
            content=sec.content,
            category=category,
            source=cfg.source_enum,
            parent_context=parent_ctx,
            keywords=keywords,
            edition=cfg.edition,
            status="active",
            content_hash=content_hash,
            canonical_title=sec.title.strip().lower(),
        )


# ================================================================
#  对外主接口
# ================================================================

class HTMProcessor:
    """
    对外主接口。调用方只需要用这个类。
    """

    @staticmethod
    def _read_html(path: Path) -> str:
        """
        自动检测编码后读取 HTML 文件。
        优先顺序：
          1. BeautifulSoup 从 <meta charset> / HTTP-Equiv 里检测
          2. 文件头注释里的 <!-- coding: xxx -->
          3. 回退 gbk（适用于本项目的中文规则书）
          4. 最终回退 utf-8(errors=replace)
        """
        raw = path.read_bytes()

        # 先尝试从文件头 200 字节中找 coding 注释（优先于 meta 检测）
        head = raw[:200]
        coding_match = re.search(rb"coding[:\s]+([A-Za-z0-9_-]+)", head)
        if coding_match:
            detected = coding_match.group(1).decode("ascii", errors="replace").lower()
            try:
                return raw.decode(detected, errors="replace")
            except LookupError:
                pass

        # 让 BeautifulSoup 尝试检测 meta charset
        try:
            sniff = BeautifulSoup(raw[:2048], "html.parser")
            meta = sniff.find("meta", attrs={"charset": True})
            if not meta:
                meta = sniff.find("meta", attrs={"http-equiv": re.compile("content-type", re.I)})
            if meta:
                charset_raw = meta.get("charset") or meta.get("content", "")
                charset_match = re.search(r"charset=([A-Za-z0-9_-]+)", str(charset_raw), re.I)
                if charset_match:
                    enc = charset_match.group(1).lower()
                    try:
                        return raw.decode(enc, errors="replace")
                    except LookupError:
                        pass
        except Exception:
            pass

        # 回退 gbk（中文规则书通常是 gbk/gb2312）
        try:
            return raw.decode("gbk", errors="replace")
        except Exception:
            return raw.decode("utf-8", errors="replace")

    @staticmethod
    def process_file(
        path: str | Path,
        config: HTMProcessConfig | None = None,
    ) -> list[RuleChunk]:
        """处理单个 HTML/HTM 文件"""
        config = config or HTMProcessConfig()
        path = Path(path)

        html_content = HTMProcessor._read_html(path)
        extractor = HTMExtractor(config)
        sections = extractor.extract(html_content, source_file=path.name)

        chunker = HTMChunker(config)
        return chunker.chunk(sections)

    @staticmethod
    def process_directory(
        directory: str | Path,
        config: HTMProcessConfig | None = None,
        glob_pattern: str = "**/*.htm*",
        max_files: int = 0,
    ) -> tuple[list[RuleChunk], list[str]]:
        """
        处理目录下的所有 HTM/HTML 文件。
        返回 (所有chunks列表, 出错文件列表)。
        """
        config = config or HTMProcessConfig()
        directory = Path(directory)

        files = sorted(directory.glob(glob_pattern))
        if not files:
            # 宽松匹配
            files = sorted(directory.glob("*.htm")) + sorted(directory.glob("*.html"))

        if max_files > 0:
            files = files[:max_files]

        all_chunks: list[RuleChunk] = []
        errors: list[str] = []

        for f in files:
            try:
                chunks = HTMProcessor.process_file(f, config)
                all_chunks.extend(chunks)
            except Exception as e:
                errors.append(f"{f.name}: {e}")

        return all_chunks, errors

    @staticmethod
    def process_auto(
        path: str | Path,
        config: HTMProcessConfig | None = None,
    ) -> tuple[list[RuleChunk], list[str]]:
        """
        自动检测 path 是文件还是目录并处理。
        返回 (chunks, errors)。
        """
        path = Path(path)
        if path.is_dir():
            return HTMProcessor.process_directory(path, config)
        else:
            return HTMProcessor.process_file(path, config), []


# ================================================================
#  CLI（与 pdf_processor.py 风格保持一致）
# ================================================================

def _build_config_interactive(
    source_name: str,
    edition: str,
    source_enum: RuleSource,
    split_at_levels: list[int],
    max_chunk_chars: int,
) -> HTMProcessConfig:
    return HTMProcessConfig(
        source_name=source_name,
        source_enum=source_enum,
        edition=edition,
        split_at_levels=split_at_levels,
        max_chunk_chars=max_chunk_chars,
    )


def _print_preview(chunks: list[RuleChunk]) -> None:
    print(f"\n{'='*60}")
    print(f"  解析结果预览 (共 {len(chunks)} 个 chunk)")
    print(f"{'='*60}")

    category_count: dict[str, int] = {}
    for c in chunks:
        category_count[c.category.value] = category_count.get(c.category.value, 0) + 1

    print("\n  按类别统计:")
    for cat, cnt in sorted(category_count.items(), key=lambda x: -x[1]):
        print(f"    {cat:25s}  {cnt}")

    print(f"\n  示例 chunk (前 3 个):")
    for i, chunk in enumerate(chunks[:3]):
        print(f"\n  [{i+1}] 标题: {chunk.title}")
        print(f"       类别: {chunk.category.value}")
        print(f"       内容: {chunk.content[:120].replace(chr(10), ' ')}...")
        print(f"       关键词: {', '.join(chunk.keywords[:6])}")


def _source_enum_from_str(s: str) -> RuleSource:
    mapping = {
        "phb2024": RuleSource.PHB_2024,
        "phb 2024": RuleSource.PHB_2024,
        "dmg2024": RuleSource.DMG_2024,
        "dmg 2024": RuleSource.DMG_2024,
        "mm2024": RuleSource.MM_2024,
        "mm 2024": RuleSource.MM_2024,
        "basic2024": RuleSource.BASIC_RULES,
        "basic rules 2024": RuleSource.BASIC_RULES,
        "srd2014": RuleSource.SRD_2014,
        "srd 5.1 (2014)": RuleSource.SRD_2014,
        "phb2014": RuleSource.PHB_2014,
        "phb 2014": RuleSource.PHB_2014,
    }
    return mapping.get(s.strip().lower(), RuleSource.PHB_2024)


def main() -> None:
    """CLI 入口"""
    # 中文输出支持
    try:
        if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(
        description="D&D 规则书 HTM/HTML 导入工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 解析单个文件并预览（不导入）
  python htm_processor.py phb2024.html

  # 解析目录
  python htm_processor.py ./rules_html/ --source "PHB 2024" --edition "PHB 2024"

  # 解析并输出 JSON（供调试）
  python htm_processor.py rules.html --output chunks.json

  # 直接导入（需要服务在运行）
  python htm_processor.py rules.html --import-url http://localhost:8000
        """,
    )
    parser.add_argument("path", help="HTML 文件或目录路径")
    parser.add_argument("--source", default="PHB 2024", help="来源名称 (default: PHB 2024)")
    parser.add_argument("--edition", default="PHB 2024", help="规则版本 (default: PHB 2024)")
    parser.add_argument(
        "--split-levels", default="1,2,3",
        help="以逗号分隔的标题切分级别 (default: 1,2,3)"
    )
    parser.add_argument("--max-chars", type=int, default=2500, help="最大 chunk 字符数")
    parser.add_argument("--output", default="", help="输出 JSON 文件路径 (可选)")
    parser.add_argument(
        "--import-url", default="",
        help="服务器 URL，若提供则直接向服务器 API 导入",
    )
    parser.add_argument("--no-preview", action="store_true", help="跳过预览")
    parser.add_argument("--yes", action="store_true", help="跳过确认直接处理")

    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"❌ 路径不存在: {path}", file=sys.stderr)
        sys.exit(1)

    split_levels = [int(x) for x in args.split_levels.split(",")]
    source_enum = _source_enum_from_str(args.source)

    config = _build_config_interactive(
        source_name=args.source,
        edition=args.edition,
        source_enum=source_enum,
        split_at_levels=split_levels,
        max_chunk_chars=args.max_chars,
    )

    print(f"\n📖 来源: {args.source}  |  版本: {args.edition}")
    print(f"📂 路径: {path}")
    print(f"🔧 切分级别: h{'/h'.join(str(l) for l in split_levels)}  "
          f"|  最大 chunk: {args.max_chars} 字符")

    if not args.yes:
        try:
            ans = input("\n开始处理？(y/n): ").strip().lower()
            if ans != "y":
                print("已取消")
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            print("\n已取消")
            sys.exit(0)

    print("\n⏳ 处理中...")
    chunks, errors = HTMProcessor.process_auto(path, config)

    if errors:
        print(f"\n⚠️  {len(errors)} 个文件出错:")
        for e in errors[:5]:
            print(f"   {e}")

    if not args.no_preview:
        _print_preview(chunks)

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        # 从输入路径推断输出文件名
        if path.is_file():
            base_name = path.stem
        else:
            base_name = path.name
        # 统一存储到 src/data/imports/htm/ 目录
        output_dir = Path(__file__).parent / "data" / "imports" / "htm"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{base_name}_rules.json"

    data = [c.model_dump() for c in chunks]
    output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已输出 {len(chunks)} 个 chunk → {output_path}")

    if args.import_url:
        _import_to_server(chunks, args.import_url)
    else:
        print(f"\n✅ 共解析 {len(chunks)} 个 chunk")
        print("   使用 --import-url http://localhost:8000 可直接导入到服务器")
        print("   使用 --output chunks.json 可保存为 JSON 文件")


def _import_to_server(chunks: list[RuleChunk], server_url: str) -> None:
    """将 chunks 通过 API 导入到运行中的服务器"""
    import urllib.request
    import urllib.error

    url = f"{server_url.rstrip('/')}/api/import/rules/htm"
    payload = json.dumps({
        "chunks": [c.model_dump() for c in chunks],
        "check_conflicts": True,
    }).encode("utf-8")

    print(f"\n📤 导入到 {url} ...")
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            print(f"✅ 导入成功: {result.get('chunks_created', '?')} 条规则")
            if result.get("message"):
                print(f"   {result['message']}")
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP 错误 {e.code}: {e.read().decode()}", file=sys.stderr)
    except Exception as e:
        print(f"❌ 导入失败: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
