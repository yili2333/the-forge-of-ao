"""
HTM 规则书离线导入脚本

在不启动服务器的情况下，直接将 HTM 格式规则书批量解析并写入数据库。
与 import_monsters.py 用途相同，区别在于写入的是 rule_chunks 表。

用法：
    cd src
    python import_htm_books.py                      # 导入默认三本规则书
    python import_htm_books.py --books PHB DMG       # 只导入指定规则书
    python import_htm_books.py --dry-run             # 只解析不写入

依赖：
    DND5e_chm-main/ 目录需与项目根目录同级，或通过 DND5E_CHM_DIR 环境变量指定
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from htm_processor import HTMProcessor, HTMProcessConfig
from models import RuleSource
import db
from embedding_service import EmbeddingService
from vector_store import VectorStore
from keyword_store import KeywordStore
from rule_importer import RuleImporter
from config import get_settings


_DEFAULT_CHM_DIR = Path(r"D:\dnd-rules-ai\DND5e_chm-main")


def _get_chm_dir() -> Path:
    """优先读 .env / 环境变量 DND5E_CHM_DIR，否则用硬编码默认值。"""
    import os
    # pydantic-settings 已经把 .env 加载进 os.environ
    # 但脚本独立运行时可能还没加载，手动读一次
    env = os.environ.get("DND5E_CHM_DIR")
    if not env:
        # 尝试从 .env 文件读取
        from config import get_settings
        _ = get_settings()   # 触发 .env 加载
        env = os.environ.get("DND5E_CHM_DIR")
    return Path(env) if env else _DEFAULT_CHM_DIR


# 所有可导入的规则书配置
BOOK_CONFIGS: dict[str, dict] = {
    "PHB": {
        "subdir": "玩家手册2024",
        "source": RuleSource.PHB_2024,
        "edition": "PHB 2024",
        "source_name": "玩家手册 2024",
    },
    "DMG": {
        "subdir": "城主指南2024",
        "source": RuleSource.DMG_2024,
        "edition": "DMG 2024",
        "source_name": "城主指南 2024",
    },
    "MM": {
        "subdir": "怪物图鉴2025",
        "source": RuleSource.MM_2024,
        "edition": "MM 2025",
        "source_name": "怪物图鉴 2025",
    },
}

DEFAULT_BOOKS = ["PHB", "DMG", "MM"]


async def import_books(books: list[str], dry_run: bool = False) -> None:
    settings = get_settings()
    await db.init_db()

    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    keyword_store = KeywordStore()
    importer = RuleImporter(embedding_service, vector_store, keyword_store)

    existing = await db.get_all_chunks()
    keyword_store.build_index(existing)
    print(f"\n[DB] 导入前：{len(existing)} 条规则")

    chm_dir = _get_chm_dir()
    if not chm_dir.exists():
        print(f"[错误] CHM 目录不存在：{chm_dir}", file=sys.stderr)
        print(f"  请设置环境变量 DND5E_CHM_DIR 指向 DND5e_chm-main 目录", file=sys.stderr)
        sys.exit(1)

    grand_total = 0
    grand_start = time.time()

    for key in books:
        cfg_dict = BOOK_CONFIGS.get(key.upper())
        if not cfg_dict:
            print(f"[跳过] 未知规则书标识: {key}（可用: {', '.join(BOOK_CONFIGS)}）")
            continue

        book_path = chm_dir / cfg_dict["subdir"]
        if not book_path.exists():
            print(f"[跳过] 目录不存在：{book_path}")
            continue

        print(f"\n{'='*60}")
        print(f"[导入] {cfg_dict['source_name']}  ({cfg_dict['edition']})")
        print(f"   路径: {book_path}")

        cfg = HTMProcessConfig(
            source_name=cfg_dict["source_name"],
            source_enum=cfg_dict["source"],
            edition=cfg_dict["edition"],
            split_at_levels=[1, 2, 3, 4],
            max_chunk_chars=2500,
            min_chunk_chars=60,
        )
        t0 = time.time()
        chunks, errors = HTMProcessor.process_directory(book_path, cfg)
        print(f"   解析完成: {len(chunks)} 条, {len(errors)} 错误, {time.time()-t0:.1f}s")

        for e in errors[:3]:
            print(f"   [错误] {e}")

        if not chunks:
            print("   [跳过] 无内容")
            continue

        if dry_run:
            print(f"   [DRY RUN] 不写入数据库")
            grand_total += len(chunks)
            continue

        t0 = time.time()
        conflicts = await importer.import_official_rules(chunks, check_conflicts=True)
        print(f"   写入完成: {time.time()-t0:.1f}s，冲突: {len(conflicts)}")
        grand_total += len(chunks)

    total_time = time.time() - grand_start
    if not dry_run:
        final_count = len(await db.get_all_chunks())
        print(f"\n{'='*60}")
        print(f"[完成] 新增 {grand_total} 条规则，数据库总计 {final_count} 条，耗时 {total_time:.1f}s")
    else:
        print(f"\n[DRY RUN 完成] 共解析 {grand_total} 条，未写入数据库")


def main() -> None:
    parser = argparse.ArgumentParser(description="HTM 规则书离线导入脚本")
    parser.add_argument(
        "--books", nargs="*", default=DEFAULT_BOOKS,
        help=f"要导入的规则书（默认全部）：{', '.join(BOOK_CONFIGS)}",
    )
    parser.add_argument("--dry-run", action="store_true", help="只解析不写入数据库")
    parser.add_argument(
        "--chm-dir", default=None,
        help=f"CHM 根目录（默认：{_DEFAULT_CHM_DIR}）",
    )
    args = parser.parse_args()

    if args.chm_dir:
        import os
        os.environ["DND5E_CHM_DIR"] = args.chm_dir

    asyncio.run(import_books(args.books, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
