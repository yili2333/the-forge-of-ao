"""
模型打包脚本 — 将 Hugging Face 模型导出到项目内的 models/ 目录

用法:
    python pack_model.py                # 打包默认模型 (bge-small-zh-v1.5)
    python pack_model.py BAAI/bge-m3    # 打包指定模型

打包后项目可离线运行，无需联网下载模型。
分发时将 models/ 目录一并发送即可。
"""

import sys
import shutil
from pathlib import Path

# 修复 Windows 控制台中文输出乱码（cp936 → utf-8）
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_MODELS_DIR = _PROJECT_ROOT / "models"

DEFAULT_MODEL = "BAAI/bge-small-zh-v1.5"


def pack_model(model_name: str):
    """下载模型并保存到项目内 models/ 目录"""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("错误: 请先安装 sentence-transformers")
        print("  pip install sentence-transformers")
        sys.exit(1)

    # 目标路径: models/BAAI--bge-small-zh-v1.5
    safe_name = model_name.replace("/", "--")
    target_dir = _LOCAL_MODELS_DIR / safe_name

    if target_dir.exists():
        print(f"模型已存在: {target_dir}")
        answer = input("是否重新下载覆盖? (y/N): ").strip().lower()
        if answer != "y":
            print("已取消")
            return
        shutil.rmtree(target_dir)

    print(f"正在下载模型: {model_name} ...")
    model = SentenceTransformer(model_name)

    print(f"正在保存到: {target_dir} ...")
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(target_dir))

    # 计算目录大小
    total_size = sum(f.stat().st_size for f in target_dir.rglob("*") if f.is_file())
    size_mb = total_size / 1024 / 1024

    print(f"打包完成! 模型大小: {size_mb:.1f}MB")
    print(f"路径: {target_dir}")
    print()
    print("提示: models/ 目录已在 .gitignore 中排除。")
    print("分发时请将 models/ 目录随项目一并打包。")


if __name__ == "__main__":
    model_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    pack_model(model_name)
