from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

class RuleStatus(str, Enum):
    """规则状态"""
    ACTIVE = "active"               # 当前生效
    SUPERSEDED = "superseded"       # 被新版本取代
    DEPRECATED = "deprecated"       # 已废弃
    DRAFT = "draft"                 # 草稿（未生效）


class ConflictType(str, Enum):
    """冲突类型"""
    VERSION_UPDATE = "version_update"      # 新版本更新了旧版本
    DUPLICATE = "duplicate"                # 重复录入
    CONTRADICTION = "contradiction"        # 内容矛盾
    HOMEBREW_OVERRIDE = "homebrew_override" # 自定义覆盖官方


# ========== 规则分类枚举 ==========

class RuleSource(str, Enum):
    PHB_2024 = "PHB 2024"
    DMG_2024 = "DMG 2024"
    MM_2024 = "MM 2024"
    BASIC_RULES = "Basic Rules 2024"
    SRD_2014 = "SRD 5.1 (2014)"
    PHB_2014 = "PHB 2014"
    ERRATA = "Errata"
    HOMEBREW = "Homebrew"


class RuleCategory(str, Enum):
    COMBAT = "combat"
    SPELL = "spell"
    CLASS_FEATURE = "class_feature"
    SPECIES_TRAIT = "species_trait"
    FEAT = "feat"
    CONDITION = "condition"
    EQUIPMENT = "equipment"
    SKILL = "skill"
    GENERAL_RULE = "general_rule"
    MAGIC_ITEM = "magic_item"
    ADVENTURING = "adventuring"


# ========== 核心规则块 ==========

class RuleChunk(BaseModel):
    id: str
    title: str
    content: str
    category: RuleCategory
    source: RuleSource
    page: int | None = None

    # D&D 特有
    parent_context: str = ""
    related_rule_ids: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    level_requirement: int | None = None

    # 多租户
    campaign_id: str | None = None
    priority: int = 0

    # ===== 版本管理字段 =====
    edition: str = "PHB 2024"          # 规则版本
    status: str = "active"              # active / superseded / deprecated
    superseded_by: str | None = None    # 被哪条规则取代（rule id）
    supersedes: str | None = None       # 取代了哪条规则（rule id）
    errata_note: str | None = None      # 勘误说明
    canonical_title: str = ""           # 标准化标题（用于匹配同名规则）
    content_hash: str = ""              # 内容哈希（用于检测重复）

    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # 运行时附加
    score: float = 0.0
    is_overridden: bool = False


# ========== 冲突记录 ==========

class RuleConflict(BaseModel):
    """记录检测到的规则冲突"""
    id: str
    conflict_type: ConflictType
    rule_a_id: str
    rule_a_title: str
    rule_a_source: str
    rule_b_id: str
    rule_b_title: str
    rule_b_source: str
    description: str               # 冲突描述
    resolution: str = ""           # 解决方案
    auto_resolved: bool = False    # 是否已自动解决
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


# ========== API 请求/响应 ==========

class QueryRequest(BaseModel):
    question: str
    campaign_id: str | None = None
    conversation_history: list[dict] = Field(default_factory=list)
    prefer_edition: str | None = None    # 新增：偏好版本 "2024" / "2014"


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceRef]
    confidence: float
    chunks_used: int
    has_version_diff: bool = False       # 新增：是否涉及版本差异
    version_note: str = ""               # 新增：版本差异说明


class SourceRef(BaseModel):
    title: str
    source: str
    category: str
    is_homebrew: bool = False
    edition: str = ""                    # 新增
    status: str = "active"               # 新增


class ImportRuleRequest(BaseModel):
    campaign_id: str
    rules: list[ImportRuleItem]


class ImportRuleItem(BaseModel):
    title: str
    content: str
    category: RuleCategory = RuleCategory.GENERAL_RULE
    keywords: list[str] = Field(default_factory=list)
    overrides_official: str | None = None
    parent_context: str = ""
    edition: str = "Homebrew"


class ImportRuleResponse(BaseModel):
    success: bool
    chunks_created: int
    message: str
    conflicts_found: list[RuleConflict] = Field(default_factory=list)  # 新增


# ========== HTM 导入 ==========

class HTMImportRequest(BaseModel):
    """
    HTM 规则书导入请求。
    可以提交本地路径（服务器端处理），也可直接提交预解析好的 chunks（CLI 导入时用）。
    """
    # --- 路径模式 ---
    path: str = ""                    # 本地文件或目录路径（服务器端处理）

    # --- 直接 chunks 模式 ---
    chunks: list[RuleChunk] = Field(default_factory=list)  # CLI 预解析后直接提交

    # --- 配置 ---
    source_name: str = "PHB 2024"
    edition: str = "PHB 2024"
    source_key: str = "PHB_2024"      # RuleSource 的 value 字符串
    check_conflicts: bool = True
    split_at_levels: list[int] = Field(default_factory=lambda: [1, 2, 3])
    max_chunk_chars: int = 2500


class HTMImportResponse(BaseModel):
    success: bool
    files_processed: int = 0
    chunks_created: int
    conflicts_found: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str


# ========== PDF 导入 ==========

class PDFImportRequest(BaseModel):
    """
    PDF 规则书导入请求。
    两种模式：
    1. path 模式：服务器端直接解析本地 PDF 文件
    2. chunks 模式：客户端用 pdf_processor.py CLI 预解析后直接提交 chunks
    """
    # --- 路径模式（服务器端处理）---
    path: str = ""

    # --- 直接 chunks 模式（CLI 预解析）---
    chunks: list[RuleChunk] = Field(default_factory=list)

    # --- 配置（路径模式时有效）---
    source_name: str = "PHB 2024"
    source_key: str = "PHB_2024"      # RuleSource 的 value 字符串
    check_conflicts: bool = True
    page_start: int = 1
    page_end: int = -1
    max_chunk_chars: int = 3000


class PDFImportResponse(BaseModel):
    success: bool
    chunks_created: int
    conflicts_found: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str


# ========== 文件上传导入 ==========

class UploadImportResponse(BaseModel):
    """POST /api/import/rules/upload 返回值"""
    success: bool
    filename: str
    detected_source: str
    detected_name: str
    chunks_created: int
    conflicts_found: int = 0
    errors: list[str] = Field(default_factory=list)
    message: str


# ========== 文件夹扫描导入 ==========

class BrowseEntry(BaseModel):
    """单个目录条目（用于前端目录导航）"""
    name: str           # 目录/文件名
    path: str           # 完整绝对路径
    is_dir: bool
    htm_count: int = 0  # 目录内 .htm/.html 文件数（仅 is_dir=True 时有效）
    pdf_count: int = 0  # 目录内 .pdf 文件数


class BrowseResult(BaseModel):
    """GET /api/import/rules/browse 返回值"""
    current_path: str
    parent_path: str | None       # None 表示已到根目录
    entries: list[BrowseEntry]
    total_htm: int = 0            # 当前目录下直属 .htm/.html 文件总数
    total_pdf: int = 0            # 当前目录下直属 .pdf 文件总数


class ScanBookResult(BaseModel):
    """scan 端口中，每本检测到的规则书的处理结果"""
    subdir: str                   # 相对于 root_path 的子目录名（或文件名）
    full_path: str
    detected_source: str          # 自动检测到的 RuleSource.value
    detected_name: str            # 用于展示的书名
    files_found: int = 0
    chunks_created: int = 0
    conflicts_found: int = 0
    errors: list[str] = Field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class ScanImportRequest(BaseModel):
    """
    文件夹扫描导入请求。

    服务器扫描 root_path 下的每个子目录，
    根据目录名自动匹配 RuleSource；无法匹配的归入 HOMEBREW。

    dry_run=True 时只扫描，不写入数据库，用于预览效果。
    """
    root_path: str                        # 要扫描的根目录（服务器端路径）
    check_conflicts: bool = True
    dry_run: bool = False                 # True = 仅扫描预览，不写入数据库
    max_chunk_chars: int = 2500
    source_override: str = ""             # 非空时强制所有子目录使用同一来源


class ScanImportResponse(BaseModel):
    """POST /api/import/rules/scan 返回值"""
    success: bool
    root_path: str
    books_found: int
    books_imported: int
    total_chunks: int
    total_conflicts: int
    dry_run: bool = False
    results: list[ScanBookResult]
    message: str