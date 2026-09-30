"""
批量导入怪物数据脚本

从 D&D 5e CHM 源文件中解析怪物数据，导入到 monsters 表。

用法：
  python import_monsters.py [--dry-run] [--overwrite] [--sources SOURCE...]

支持的来源目录（相对于 DND5E_CHM_DIR 或绝对路径）：
  - 怪物图鉴2025      → source="MM 2024"
  - 怪物图鉴          → source="MM 2014"
  - 多元宇宙的怪物    → source="MMotM"
  - 魔邓肯的众敌卷册  → source="Mordenkainens"
  - 塔莎的万事坩埚    → source="Tashas"
  - DNDBeyond/怪物纲要1 → source="MMotM Extra"
  - 万象无常书        → source="Deck of Many Things"
  - 范·里希腾的鸦阁魔域指南 → source="VRGtR"
  - 瓦罗怪物指南      → source="Volo"
  - 珊娜萨的万事指南  → source="Xanathars"

配置:
  DND5E_CHM_DIR 环境变量 或 .env 中设置，默认 D:\\dnd-rules-ai\\DND5e_chm-main
"""
from __future__ import annotations

import argparse
import asyncio
import io
import os
import sys
from pathlib import Path

# ── Windows 控制台 UTF-8 输出（避免 emoji 崩溃）────────────────────────────
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 确保 src/ 在 import path 中 ─────────────────────────────────────────────
_SRC = Path(__file__).parent
sys.path.insert(0, str(_SRC))

from monster.stat_block_parser import parse_directory
from monster.storage import init_monster_db, save_monsters, count_monsters

# ── 来源目录配置 ─────────────────────────────────────────────────────────────

_DEFAULT_CHM_DIR = Path(r"D:\dnd-rules-ai\DND5e_chm-main")

# 格式: (子目录名或相对路径, source标签, 优先级)
# 优先级高的先处理；相同名称时高优先级来源会被保留（INSERT OR REPLACE）
_SOURCE_CONFIG: list[tuple[str, str, int]] = [
    ("怪物图鉴2025",                  "MM 2024",            100),
    ("怪物图鉴",                      "MM 2014",             80),
    ("多元宇宙的怪物",                "MMotM",               70),
    ("魔邓肯的众敌卷册",              "Mordenkainens",        60),
    ("塔莎的万事坩埚",                "Tashas",              50),
    ("DNDBeyond/怪物纲要1",           "MMotM Extra",         40),
    ("DNDBeyond/怪物纲要2",           "MMotM Extra",         40),
    ("DNDBeyond/怪物纲要3",           "MMotM Extra",         40),
    ("DNDBeyond/怪物纲要4",           "MMotM Extra",         40),
    ("DNDBeyond/邪物卷册1",           "MMotM Extra",         40),
    ("DNDBeyond/错位怪物1",           "MMotM Extra",         40),
    ("万象无常书",                    "Deck of Many Things", 30),
    ("范·里希腾的鸦阁魔域指南",       "VRGtR",               30),
    ("瓦罗怪物指南",                  "Volo",                30),
    ("巨人之荣耀",                    "Giants",              25),
    ("布布的星界怪兽展",              "Boo's Astral",        25),
    ("星界冒险者指南",                "Spelljammer",         25),
    ("荒洲探险家指南",                "Wildmount",           25),
    ("珊娜萨的万事指南",              "Xanathars",           20),
    ("塞洛斯之神话奥德赛",            "Theros",              20),
    ("拉尼卡公会长指南",              "Ravnica",             20),
    ("艾伯伦：从终末战争中崛起",      "Eberron",             20),
    ("剑湾冒险者指南",                "SCAG",                20),
    ("印记城与外域",                  "Sigil",               20),
    ("莫提的位面游记",                "Planescape",          15),
    ("龙枪：龙后之影",                "Dragonlance",         15),
    ("费资本的巨龙宝库",              "Fizban",              15),
    ("DNDBeyond/地图-葬仪社",         "Adventure",           10),
    ("DNDBeyond/侠盗荣耀",            "Adventure",           10),
]


def _get_chm_dir() -> Path:
    """优先读 .env / 环境变量 DND5E_CHM_DIR，否则用硬编码默认值。"""
    env = os.environ.get("DND5E_CHM_DIR")
    if not env:
        from config import get_settings
        _ = get_settings()   # 触发 .env 加载
        env = os.environ.get("DND5E_CHM_DIR")
    return Path(env) if env else _DEFAULT_CHM_DIR


async def main() -> None:
    parser = argparse.ArgumentParser(description="批量导入 D&D 怪物数据")
    parser.add_argument("--dry-run", action="store_true", help="只解析不写入数据库")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已有同名怪物（默认：跳过已有）")
    parser.add_argument("--sources", nargs="*",
                        help="只处理指定来源标签，如 'MM 2024' 'MMotM'")
    parser.add_argument("--chm-dir", default=None,
                        help=f"CHM 根目录（默认：{_DEFAULT_CHM_DIR}）")
    args = parser.parse_args()

    chm_dir = Path(args.chm_dir) if args.chm_dir else _get_chm_dir()
    if not chm_dir.exists():
        print(f"[错误] CHM 目录不存在：{chm_dir}", file=sys.stderr)
        sys.exit(1)

    overwrite = args.overwrite
    dry_run = args.dry_run

    # 初始化数据库
    if not dry_run:
        await init_monster_db()
        before = await count_monsters()
        print(f"[DB] 导入前：{before} 只怪物")

    # 过滤来源
    configs = _SOURCE_CONFIG
    if args.sources:
        wanted = set(args.sources)
        configs = [(d, s, p) for d, s, p in configs if s in wanted]

    all_monsters = []
    all_errors = []
    seen_names: set[str] = set()

    # 按优先级排序（高→低）
    configs = sorted(configs, key=lambda x: -x[2])

    total_skipped_dup = 0
    for subdir, source_label, priority in configs:
        target = chm_dir / subdir
        if not target.exists():
            print(f"  [跳过] 目录不存在：{target}")
            continue

        print(f"\n📂 解析 {target.name}（{source_label}）...")

        def cb(msg: str) -> None:
            print(f"  {msg}")

        monsters, errors = parse_directory(target, source=source_label, progress_cb=cb)
        all_errors.extend(errors)

        # 去重：同一名称只保留最高优先级（先出现的）
        new_monsters = []
        for m in monsters:
            key = m.name_cn.strip()
            if key in seen_names:
                total_skipped_dup += 1
                continue
            seen_names.add(key)
            new_monsters.append(m)

        print(f"  ✅ 解析 {len(monsters)} 只，新增（去重后）{len(new_monsters)} 只")
        all_monsters.extend(new_monsters)

    print(f"\n{'='*60}")
    print(f"总计解析：{len(all_monsters) + total_skipped_dup} 只")
    print(f"跨来源去重后：{len(all_monsters)} 只（去重 {total_skipped_dup} 只重复）")
    if all_errors:
        print(f"解析错误：{len(all_errors)} 个")
        for e in all_errors[:10]:
            print(f"  [错误] {e}")
        if len(all_errors) > 10:
            print(f"  ... 及 {len(all_errors)-10} 个更多")

    if dry_run:
        print("\n[DRY RUN] 未写入数据库。以下是前20条预览：")
        for m in all_monsters[:20]:
            print(f"  {m.name_cn:15s} {m.name_en:25s} CR={m.cr:5s} HP={m.hp:4d} AC={m.ac:3d} "
                  f"[{m.source}]")
        return

    # 写入数据库
    print(f"\n💾 写入数据库（overwrite={overwrite}）...")
    inserted, skipped = await save_monsters(all_monsters, overwrite=overwrite)

    after = await count_monsters()
    print(f"\n✅ 写入完成：新增/更新 {inserted} 只，跳过已有 {skipped} 只")
    print(f"[DB] 导入后：{after} 只怪物（+{after - before}）")


if __name__ == "__main__":
    asyncio.run(main())
