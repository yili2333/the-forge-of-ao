"""
统一导入路由

/api/import/rules/upload           — 直接上传 HTM/HTML/PDF 文件导入（新环境无需服务器文件）
/api/import/rules/htm              — 从 HTM/HTML 格式规则书导入官方/Homebrew 规则
/api/import/rules/pdf              — 从 PDF 格式规则书导入规则
/api/import/rules/custom           — 导入 DM 自定义 Homebrew 规则（JSON）
/api/import/rules/browse           — 浏览服务器目录（目录选择器用）
/api/import/rules/scan             — 扫描服务器文件夹并自动导入
/api/import/monsters               — 从 HTM 目录批量导入怪物数据
/api/import/map-bg/{cid}/{mid}     — 上传遭遇战地图底图
/api/import/region-map-bg/{cid}/{mid} — 上传区域地图底图
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile

from maps.config import MAPS_DIR, image_path_to_url
from models import (
    HTMImportRequest, HTMImportResponse,
    PDFImportRequest, PDFImportResponse,
    ImportRuleRequest, ImportRuleResponse,
    RuleSource,
    BrowseEntry, BrowseResult,
    ScanImportRequest, ScanImportResponse, ScanBookResult,
    UploadImportResponse,
)
from htm_processor import HTMProcessor, HTMProcessConfig
from monster.models import MonsterImportRequest, MonsterImportResponse
from monster.storage import save_monsters
from monster.stat_block_parser import parse_directory, parse_file

if TYPE_CHECKING:
    from rule_importer import RuleImporter

router = APIRouter(prefix="/api/import", tags=["import"])

# Set at startup via set_dependencies()
_importer: RuleImporter | None = None

MAP_UPLOAD_DIR = MAPS_DIR


def set_dependencies(importer: "RuleImporter") -> None:
    global _importer
    _importer = importer


def _require_dm(x_role: str | None) -> None:
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="此操作需要 DM 权限")


# ============================================================
#  HTM 规则书导入
# ============================================================

@router.post("/rules/htm", response_model=HTMImportResponse)
async def import_htm_rules(request: HTMImportRequest):
    """
    从 HTML/HTM 格式的规则书导入规则。

    **方式一：CLI 预解析后提交**（先在本地跑 `python htm_processor.py` 验证效果）
    ```json
    { "chunks": [ {...} ], "check_conflicts": true }
    ```

    **方式二：服务器端解析本地路径**
    ```json
    { "path": "D:/rules/phb2024.html", "source_name": "PHB 2024",
      "edition": "PHB 2024", "source_key": "PHB_2024" }
    ```
    """
    assert _importer is not None, "importer not initialized"

    try:
        if request.chunks:
            chunks = request.chunks
            files_processed = 0
            errors: list[str] = []

        elif request.path:
            path = Path(request.path)
            if not path.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"路径不存在或服务器无权访问: {request.path}",
                )
            try:
                source_enum = RuleSource(request.source_key)
            except ValueError:
                source_enum = next(
                    (s for s in RuleSource if s.value.lower() == request.source_key.lower()),
                    RuleSource.PHB_2024,
                )
            config = HTMProcessConfig(
                source_name=request.source_name,
                source_enum=source_enum,
                edition=request.edition,
                split_at_levels=request.split_at_levels,
                max_chunk_chars=request.max_chunk_chars,
            )
            chunks, errors = HTMProcessor.process_auto(path, config)
            files_processed = 1 if path.is_file() else len(list(path.glob("**/*.htm*")))

        else:
            raise HTTPException(
                status_code=422,
                detail="必须提供 'path'（服务器端解析）或 'chunks'（CLI 预解析）之一",
            )

        if not chunks:
            return HTMImportResponse(
                success=True,
                files_processed=files_processed if request.path else 0,
                chunks_created=0,
                errors=errors if request.path else [],
                message="未解析到任何 chunk，请检查 HTML 文件内容或调整切分配置",
            )

        conflicts = await _importer.import_official_rules(
            chunks,
            check_conflicts=request.check_conflicts,
        )

        return HTMImportResponse(
            success=True,
            files_processed=files_processed if request.path else 0,
            chunks_created=len(chunks),
            conflicts_found=len(conflicts),
            errors=errors if request.path else [],
            message=(
                f"成功导入 {len(chunks)} 条规则"
                + (f"（{len(conflicts)} 个冲突已处理）" if conflicts else "")
                + (f"，{len(errors)} 个文件出错" if (request.path and errors) else "")
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ HTM 导入错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
#  PDF 规则书导入
# ============================================================

@router.post("/rules/pdf", response_model=PDFImportResponse)
async def import_pdf_rules(request: PDFImportRequest):
    """
    从 PDF 格式的规则书导入规则。

    **方式一：CLI 预解析后提交**（先在本地跑 `python pdf_processor.py` 验证效果）
    ```json
    { "chunks": [ {...} ], "check_conflicts": true }
    ```

    **方式二：服务器端解析本地路径**（需要安装 PyMuPDF + pdfplumber）
    ```json
    { "path": "D:/rules/phb2024.pdf", "source_name": "PHB 2024",
      "source_key": "PHB_2024", "page_start": 1, "page_end": -1 }
    ```
    """
    assert _importer is not None, "importer not initialized"

    try:
        if request.chunks:
            chunks = request.chunks

        elif request.path:
            path = Path(request.path)
            if not path.exists() or not path.is_file():
                raise HTTPException(
                    status_code=400,
                    detail=f"路径不存在或不是文件: {request.path}",
                )
            if path.suffix.lower() != ".pdf":
                raise HTTPException(status_code=400, detail="仅支持 .pdf 格式文件")

            try:
                from pdf_processor import PDFRuleProcessor, PDFProcessConfig
            except ImportError as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"PDF 处理依赖未安装 (需要 PyMuPDF + pdfplumber): {e}",
                )

            try:
                source_enum = RuleSource(request.source_key)
            except ValueError:
                source_enum = next(
                    (s for s in RuleSource if s.value.lower() == request.source_key.lower()),
                    RuleSource.PHB_2024,
                )

            chunks = _parse_pdf(path, request, source_enum)

        else:
            raise HTTPException(
                status_code=422,
                detail="必须提供 'path'（服务器端解析）或 'chunks'（CLI 预解析）之一",
            )

        if not chunks:
            return PDFImportResponse(
                success=True,
                chunks_created=0,
                message="未解析到任何规则块，请检查 PDF 内容或调整配置",
            )

        conflicts = await _importer.import_official_rules(
            chunks,
            check_conflicts=request.check_conflicts,
        )

        return PDFImportResponse(
            success=True,
            chunks_created=len(chunks),
            conflicts_found=len(conflicts),
            message=(
                f"成功导入 {len(chunks)} 条规则"
                + (f"（{len(conflicts)} 个冲突已处理）" if conflicts else "")
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ PDF 导入错误: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_pdf(path: Path, request: PDFImportRequest, source_enum: RuleSource) -> list:
    from pdf_processor import (
        PDFProcessConfig, PDFExtractor, SectionParser,
        SmartChunker, TableProcessor, CrossReferenceBuilder,
    )
    import fitz as _fitz

    doc = _fitz.open(str(path))
    total_pages = len(doc)
    doc.close()

    cfg = PDFProcessConfig(
        source_name=request.source_name,
        source_enum=source_enum,
        page_start=request.page_start,
        page_end=request.page_end if request.page_end != -1 else total_pages,
        max_chunk_chars=request.max_chunk_chars,
    )
    extractor = PDFExtractor(str(path), cfg)
    pages_data = extractor.extract_all_pages()
    parser = SectionParser(cfg)
    sections = parser.parse(pages_data)
    tables = extractor.extract_tables()
    extractor.close()

    chunker = SmartChunker(cfg)
    result_chunks = chunker.chunk_sections(sections)
    tp = TableProcessor()
    for i, tbl in enumerate(tables):
        tc = tp.table_to_chunk(tbl, f"Table (Page {tbl['page']}, #{i+1})", cfg.source_enum)
        if tc:
            result_chunks.append(tc)

    return CrossReferenceBuilder().build_references(result_chunks)


# ============================================================
#  地图底图上传
# ============================================================

@router.post("/map-bg/{campaign_id}/{map_id}")
async def upload_map_bg(
    campaign_id: str,
    map_id: str,
    file: UploadFile = File(...),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 上传遭遇战地图底图图片"""
    _require_dm(x_role)

    from maps.storage import get_encounter_map, save_encounter_map
    from maps.models import EncounterMap

    m = await get_encounter_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="遭遇战地图不存在")

    MAP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"encounter_{map_id}_{file.filename}"
    dest = MAP_UPLOAD_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    m.image_url = image_path_to_url(str(dest))
    return await save_encounter_map(m)


@router.post("/region-map-bg/{campaign_id}/{map_id}")
async def upload_region_map_bg(
    campaign_id: str,
    map_id: str,
    file: UploadFile = File(...),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """DM: 上传区域地图底图图片"""
    _require_dm(x_role)

    from maps.storage import get_region_map, save_region_map

    m = await get_region_map(map_id)
    if m is None or m.campaign_id != campaign_id:
        raise HTTPException(status_code=404, detail="区域地图不存在")

    MAP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"region_{map_id}_{file.filename}"
    dest = MAP_UPLOAD_DIR / filename
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    m.image_url = image_path_to_url(str(dest))
    return await save_region_map(m)


# ============================================================
#  怪物手册导入
# ============================================================

@router.post("/monsters", response_model=MonsterImportResponse)
async def import_monsters(request: MonsterImportRequest):
    """
    从 HTM 文件或目录批量导入怪物。

    示例：
    ```json
    {
      "path": "D:/dnd-rules-ai/DND5e_chm-main/怪物图鉴2025",
      "source": "MM 2024",
      "overwrite": false
    }
    ```
    """
    path = Path(request.path)
    if not path.exists():
        raise HTTPException(status_code=400, detail=f"路径不存在: {request.path}")

    errors: list[str] = []
    monsters = []

    try:
        if path.is_file():
            monsters = parse_file(path, source=request.source)
        else:
            monsters, errors = parse_directory(path, source=request.source)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {e}")

    if not monsters:
        return MonsterImportResponse(
            success=True, imported=0, skipped=0, errors=errors,
            message="未解析到任何怪物，请检查文件格式或路径",
        )

    try:
        inserted, skipped = await save_monsters(monsters, overwrite=request.overwrite)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入数据库失败: {e}")

    return MonsterImportResponse(
        success=True,
        imported=inserted,
        skipped=skipped,
        errors=errors,
        message=(
            f"成功导入 {inserted} 个怪物"
            + (f"，跳过 {skipped} 个（已存在）" if skipped else "")
            + (f"，{len(errors)} 个文件出错" if errors else "")
        ),
    )


# ============================================================
#  DM 自定义 Homebrew 规则导入
# ============================================================

@router.post("/rules/custom", response_model=ImportRuleResponse)
async def import_custom_rules(request: ImportRuleRequest):
    """
    导入 DM 自定义 Homebrew 规则到指定战役。

    示例：
    ```json
    {
      "campaign_id": "my-campaign-001",
      "rules": [
        {
          "title": "强化偷袭",
          "content": "偷袭每轮可触发两次，第二次伤害骰减半。",
          "category": "class_feature",
          "keywords": ["sneak attack", "rogue", "homebrew"],
          "overrides_official": "Sneak Attack"
        }
      ]
    }
    ```
    """
    assert _importer is not None, "importer not initialized"
    try:
        return await _importer.import_custom_rules(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
#  文件直传导入（新环境 / 无服务器文件访问时使用）
# ============================================================

_ALLOWED_SUFFIXES = {".htm", ".html", ".pdf"}
# 临时上传目录：data/uploads/rules（随服务器，不纳入 git）
_UPLOAD_TEMP_DIR = Path(__file__).resolve().parent / "data" / "uploads" / "rules"


@router.post("/rules/upload", response_model=UploadImportResponse)
async def upload_and_import(
    file: UploadFile = File(..., description="HTM / HTML / PDF 规则书文件"),
    source_key: str = Query(default="auto", description="来源标识，auto=按文件名自动识别"),
    source_name: str = Query(default="", description="自定义书名，留空时由文件名推断"),
    check_conflicts: bool = Query(default=True),
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    直接上传 HTM / HTML / PDF 规则书文件并导入。

    **适用场景**：新环境部署、服务器上没有预置规则资源目录时，
    前端（Unity / 浏览器）可直接从本地磁盘选取文件上传。

    - `source_key=auto`（默认）：根据文件名自动识别官方书目，无法识别则归入 Homebrew
    - 支持同时上传多个文件（多次调用本接口）
    - 文件处理完成后临时副本自动删除，不占用服务器空间

    **C# 示例（UnityWebRequest）：**
    ```csharp
    var form = new WWWForm();
    form.AddBinaryData("file", fileBytes, fileName, "application/octet-stream");
    var req = UnityWebRequest.Post(
        $"http://host:8000/api/import/rules/upload?source_key=auto",
        form);
    req.SetRequestHeader("X-Role", "dm");
    ```
    """
    _require_dm(x_role)
    assert _importer is not None, "importer not initialized"

    # ── 校验文件类型 ──
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 {suffix!r}，仅接受 .htm / .html / .pdf",
        )

    # ── 确定来源 ──
    stem = Path(filename).stem
    if source_key == "auto":
        detected_src, detected_name = _detect_source(stem)
    else:
        try:
            detected_src = RuleSource(source_key)
            detected_name = source_name or source_key
        except ValueError:
            detected_src = RuleSource.HOMEBREW
            detected_name = source_name or stem

    if source_name:
        detected_name = source_name

    # ── 落盘到临时目录 ──
    _UPLOAD_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = _UPLOAD_TEMP_DIR / filename
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # ── 解析 ──
        errors: list[str] = []
        chunks = []

        if suffix in (".htm", ".html"):
            config = HTMProcessConfig(
                source_name=detected_name,
                source_enum=detected_src,
                edition=detected_name,
                split_at_levels=[1, 2, 3, 4],
                max_chunk_chars=2500,
                min_chunk_chars=60,
            )
            chunks, errors = HTMProcessor.process_auto(tmp_path, config)

        elif suffix == ".pdf":
            try:
                from pdf_processor import PDFRuleProcessor, PDFProcessConfig  # noqa: F401

                class _FakeReq:
                    source_name = detected_name
                    source_key = detected_src.value
                    page_start = 1
                    page_end = -1
                    max_chunk_chars = 2500

                chunks = _parse_pdf(tmp_path, _FakeReq(), detected_src)
            except ImportError:
                raise HTTPException(
                    status_code=500,
                    detail="PDF 解析依赖未安装（需要 PyMuPDF + pdfplumber）",
                )

        if not chunks:
            return UploadImportResponse(
                success=True,
                filename=filename,
                detected_source=detected_src.value,
                detected_name=detected_name,
                chunks_created=0,
                errors=errors,
                message="文件解析成功但未提取到任何规则块，请检查文件内容或格式",
            )

        # ── 写入数据库 ──
        conflicts = await _importer.import_official_rules(
            chunks, check_conflicts=check_conflicts
        )

        return UploadImportResponse(
            success=True,
            filename=filename,
            detected_source=detected_src.value,
            detected_name=detected_name,
            chunks_created=len(chunks),
            conflicts_found=len(conflicts),
            errors=errors,
            message=(
                f"成功导入《{detected_name}》：{len(chunks)} 条规则"
                + (f"，{len(conflicts)} 个冲突已处理" if conflicts else "")
                + (f"，{len(errors)} 个解析错误" if errors else "")
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败：{e}")
    finally:
        # 无论成功失败，都清理临时文件
        if tmp_path.exists():
            tmp_path.unlink()


# ============================================================
#  目录浏览（前端导航用）
# ============================================================

# 目录名关键词 → (RuleSource, 展示名)
_SOURCE_PATTERNS: list[tuple[list[str], RuleSource, str]] = [
    (["玩家手册", "phb", "player", "players handbook"],   RuleSource.PHB_2024,    "玩家手册 2024"),
    (["城主指南", "dmg", "dungeon master", "dungeon masters guide"], RuleSource.DMG_2024, "城主指南 2024"),
    (["怪物图鉴", "mm", "monster manual", "monster"],     RuleSource.MM_2024,     "怪物图鉴 2025"),
    (["基础规则", "basic rules", "basic rule"],            RuleSource.BASIC_RULES, "基础规则 2024"),
    (["srd"],                                              RuleSource.SRD_2014,    "SRD 5.1 (2014)"),
    (["phb 2014", "phb2014", "玩家手册2014"],              RuleSource.PHB_2014,    "玩家手册 2014"),
]


def _detect_source(dir_name: str) -> tuple[RuleSource, str]:
    """根据目录名自动匹配 RuleSource，无法匹配时返回 HOMEBREW。"""
    lower = dir_name.lower()
    for keywords, source, display in _SOURCE_PATTERNS:
        if any(kw in lower for kw in keywords):
            return source, display
    return RuleSource.HOMEBREW, dir_name  # 原目录名作为书名


def _count_rule_files(path: Path) -> tuple[int, int]:
    """返回 (htm_count, pdf_count)，只统计直属文件（不递归）。"""
    htm = sum(1 for f in path.iterdir() if f.is_file() and f.suffix.lower() in (".htm", ".html"))
    pdf = sum(1 for f in path.iterdir() if f.is_file() and f.suffix.lower() == ".pdf")
    return htm, pdf


@router.get("/rules/browse", response_model=BrowseResult)
async def browse_directory(
    path: str = Query(default="", description="要浏览的目录绝对路径，为空时返回项目根目录"),
):
    """
    浏览服务器文件系统目录，供前端实现目录选择器。

    返回当前目录下的子目录列表和直属 HTM/PDF 文件数，
    以便前端逐级导航，最终选定要扫描的规则书根目录。

    示例：
    ```
    GET /api/import/rules/browse?path=D:/dnd-rules-ai/DND5e_chm-main
    ```
    """
    from config import get_settings

    if not path:
        # 默认返回 DND5E_CHM_DIR，若未设置则返回项目根目录
        settings = get_settings()
        path = settings.dnd5e_chm_dir or str(Path(__file__).resolve().parent.parent)

    current = Path(path)
    if not current.exists() or not current.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不存在或不是目录：{path}")

    entries: list[BrowseEntry] = []
    total_htm = total_pdf = 0

    try:
        for item in sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                try:
                    htm_c, pdf_c = _count_rule_files(item)
                except PermissionError:
                    htm_c = pdf_c = 0
                entries.append(BrowseEntry(
                    name=item.name,
                    path=str(item),
                    is_dir=True,
                    htm_count=htm_c,
                    pdf_count=pdf_c,
                ))
            elif item.suffix.lower() in (".htm", ".html"):
                total_htm += 1
                entries.append(BrowseEntry(name=item.name, path=str(item), is_dir=False))
            elif item.suffix.lower() == ".pdf":
                total_pdf += 1
                entries.append(BrowseEntry(name=item.name, path=str(item), is_dir=False))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权访问目录：{e}")

    parent = str(current.parent) if current.parent != current else None

    return BrowseResult(
        current_path=str(current),
        parent_path=parent,
        entries=entries,
        total_htm=total_htm,
        total_pdf=total_pdf,
    )


# ============================================================
#  文件夹扫描自动导入
# ============================================================

@router.post("/rules/scan", response_model=ScanImportResponse)
async def scan_and_import(request: ScanImportRequest):
    """
    扫描指定文件夹，自动识别其中的规则书子目录并批量导入。

    **自动检测逻辑**：
    - 根据子目录名关键词匹配官方书目（玩家手册/PHB、城主指南/DMG、怪物图鉴/MM 等）
    - 无法匹配的子目录归入 HOMEBREW 来源
    - 同时处理 .htm/.html 和 .pdf 文件

    **dry_run=true**：只扫描预览匹配结果，不写入数据库。

    示例请求：
    ```json
    {
      "root_path": "D:/dnd-rules-ai/DND5e_chm-main",
      "check_conflicts": true,
      "dry_run": false
    }
    ```
    """
    assert _importer is not None, "importer not initialized"

    root = Path(request.root_path)
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不存在或不是目录：{request.root_path}")

    # ── 收集需要处理的目标（子目录 + 根目录下直属 htm/pdf 文件）──
    targets: list[tuple[Path, bool]] = []  # (path, is_dir)
    try:
        for item in sorted(root.iterdir(), key=lambda p: p.name.lower()):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                targets.append((item, True))
            elif item.suffix.lower() in (".htm", ".html", ".pdf"):
                targets.append((item, False))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"无权访问目录：{e}")

    if not targets:
        raise HTTPException(status_code=400, detail="目录下未发现任何子目录或 HTM/PDF 文件")

    results: list[ScanBookResult] = []
    total_chunks = total_conflicts = books_imported = 0

    for target_path, is_dir in targets:
        dir_name = target_path.name

        # ── 确定来源 ──
        if request.source_override:
            try:
                src = RuleSource(request.source_override)
                display_name = request.source_override
            except ValueError:
                src = RuleSource.HOMEBREW
                display_name = dir_name
        else:
            src, display_name = _detect_source(dir_name)

        # ── 统计文件数 ──
        if is_dir:
            try:
                htm_c, pdf_c = _count_rule_files(target_path)
            except PermissionError:
                htm_c = pdf_c = 0
            files_found = htm_c + pdf_c
        else:
            files_found = 1
            htm_c = 1 if target_path.suffix.lower() in (".htm", ".html") else 0
            pdf_c = 1 if target_path.suffix.lower() == ".pdf" else 0

        if files_found == 0:
            results.append(ScanBookResult(
                subdir=dir_name,
                full_path=str(target_path),
                detected_source=src.value,
                detected_name=display_name,
                skipped=True,
                skip_reason="目录内无 HTM/HTML/PDF 文件",
            ))
            continue

        # ── dry_run：只记录，不导入 ──
        if request.dry_run:
            results.append(ScanBookResult(
                subdir=dir_name,
                full_path=str(target_path),
                detected_source=src.value,
                detected_name=display_name,
                files_found=files_found,
                skipped=True,
                skip_reason="dry_run 模式，未实际写入",
            ))
            continue

        # ── 正式导入 ──
        book_result = ScanBookResult(
            subdir=dir_name,
            full_path=str(target_path),
            detected_source=src.value,
            detected_name=display_name,
            files_found=files_found,
        )

        try:
            # HTM/HTML 处理
            if htm_c > 0:
                config = HTMProcessConfig(
                    source_name=display_name,
                    source_enum=src,
                    edition=display_name,
                    split_at_levels=[1, 2, 3, 4],
                    max_chunk_chars=request.max_chunk_chars,
                    min_chunk_chars=60,
                )
                chunks, errors = HTMProcessor.process_auto(target_path, config)
                book_result.errors.extend(errors)

                if chunks:
                    conflicts = await _importer.import_official_rules(
                        chunks,
                        check_conflicts=request.check_conflicts,
                    )
                    book_result.chunks_created += len(chunks)
                    book_result.conflicts_found += len(conflicts)

            # PDF 处理（依赖可选）
            if pdf_c > 0:
                try:
                    from pdf_processor import PDFRuleProcessor, PDFProcessConfig  # noqa: F401
                    pdf_files = [target_path] if target_path.is_file() else list(target_path.glob("*.pdf"))
                    for pdf_file in pdf_files:
                        try:
                            pdf_req_mock = type("R", (), {
                                "source_name": display_name,
                                "source_key": src.value,
                                "page_start": 1,
                                "page_end": -1,
                                "max_chunk_chars": request.max_chunk_chars,
                            })()
                            pdf_chunks = _parse_pdf(pdf_file, pdf_req_mock, src)
                            if pdf_chunks:
                                conflicts = await _importer.import_official_rules(
                                    pdf_chunks,
                                    check_conflicts=request.check_conflicts,
                                )
                                book_result.chunks_created += len(pdf_chunks)
                                book_result.conflicts_found += len(conflicts)
                        except Exception as pdf_err:
                            book_result.errors.append(f"{pdf_file.name}: {pdf_err}")
                except ImportError:
                    book_result.errors.append("PDF 解析依赖未安装（PyMuPDF + pdfplumber），已跳过 PDF 文件")

        except Exception as e:
            book_result.errors.append(str(e))

        total_chunks += book_result.chunks_created
        total_conflicts += book_result.conflicts_found
        if book_result.chunks_created > 0:
            books_imported += 1

        results.append(book_result)

    skipped = sum(1 for r in results if r.skipped)
    processed = len(results) - skipped

    return ScanImportResponse(
        success=True,
        root_path=str(root),
        books_found=len(results),
        books_imported=books_imported,
        total_chunks=total_chunks,
        total_conflicts=total_conflicts,
        dry_run=request.dry_run,
        results=results,
        message=(
            f"扫描完成：发现 {len(results)} 个目标"
            + (f"，导入 {books_imported} 本，共 {total_chunks} 条规则" if not request.dry_run else "（dry_run，未写入）")
            + (f"，跳过 {skipped} 个" if skipped else "")
            + (f"，{total_conflicts} 个冲突已处理" if total_conflicts else "")
        ),
    )
