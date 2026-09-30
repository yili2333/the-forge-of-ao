#!/usr/bin/env python3
"""
模型下载脚本
使用 hf-mirror.com 镜像站下载三个本地模型到 models/ 目录：

  1. Qwen2.5-7B-Instruct-Q4_K_M.gguf  — LLM 推理模型（约 4.5GB）
  2. BAAI/bge-m3                        — 嵌入大模型，GPU≥4GB 时使用（约 2.3GB）
  3. BAAI/bge-small-zh-v1.5            — 嵌入小模型，CPU/低显存时使用（约 93MB）

用法：
  python download_models.py            # 下载全部
  python download_models.py --llm      # 只下载 LLM
  python download_models.py --emb      # 只下载两个嵌入模型
  python download_models.py --small    # 只下载小嵌入模型（CPU 环境）
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

# ── 镜像站配置 ────────────────────────────────────────────────
MIRROR = "https://hf-mirror.com"
os.environ["HF_ENDPOINT"] = MIRROR       # huggingface_hub 读取此环境变量
os.environ["HUGGINGFACE_HUB_VERBOSITY"] = "info"

# ── 路径配置 ──────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
MODELS_DIR  = _SCRIPT_DIR / "models"
MODELS_DIR.mkdir(exist_ok=True)

# ── 目标文件/目录定义 ─────────────────────────────────────────
LLM_REPO      = "Qwen/Qwen2.5-7B-Instruct-GGUF"
LLM_FILENAME  = "qwen2.5-7b-instruct-q4_k_m.gguf"   # 仓库内的原始文件名
LLM_SAVE_AS   = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"   # 本项目 config 期望的文件名

EMB_LARGE_REPO = "BAAI/bge-m3"
EMB_LARGE_DIR  = "BAAI--bge-m3"          # embedding_service.py 按此规则查找

EMB_SMALL_REPO = "BAAI/bge-small-zh-v1.5"
EMB_SMALL_DIR  = "BAAI--bge-small-zh-v1.5"


# ═════════════════════════════════════════════════════════════
#  下载函数
# ═════════════════════════════════════════════════════════════

def _check_huggingface_hub():
    try:
        import huggingface_hub
        return True
    except ImportError:
        print("❌ 缺少依赖：huggingface_hub")
        print("   请先执行：pip install huggingface_hub")
        return False


def download_llm():
    """下载 Qwen2.5-7B-Instruct Q4_K_M GGUF 文件。"""
    save_path = MODELS_DIR / LLM_SAVE_AS

    if save_path.exists():
        size_gb = save_path.stat().st_size / 1024 ** 3
        print(f"✅ LLM 已存在，跳过：{save_path.name}（{size_gb:.1f} GB）")
        return True

    print(f"\n{'─'*60}")
    print(f"📥 下载 LLM：{LLM_REPO} → {LLM_FILENAME}")
    print(f"   镜像站：{MIRROR}")
    print(f"   目标路径：{save_path}")
    print(f"   预计大小：约 4.5 GB，请耐心等待...")
    print(f"{'─'*60}")

    if not _check_huggingface_hub():
        return False

    from huggingface_hub import hf_hub_download

    try:
        # hf_hub_download 会下载到 HF 缓存目录，拿到实际路径后再复制过来
        cached_path = hf_hub_download(
            repo_id=LLM_REPO,
            filename=LLM_FILENAME,
            repo_type="model",
        )
        print(f"\n   复制到项目目录：{save_path}")
        shutil.copy2(cached_path, save_path)
        size_gb = save_path.stat().st_size / 1024 ** 3
        print(f"✅ LLM 下载完成：{save_path.name}（{size_gb:.1f} GB）")
        return True

    except Exception as e:
        print(f"\n❌ LLM 下载失败：{e}")
        print("   建议手动下载：")
        print(f"   {MIRROR}/{LLM_REPO}/resolve/main/{LLM_FILENAME}")
        print(f"   保存为：{save_path}")
        return False


def download_embedding(repo_id: str, save_dir_name: str, label: str, size_hint: str):
    """下载 sentence-transformers 嵌入模型（完整目录）。"""
    save_path = MODELS_DIR / save_dir_name

    if save_path.exists() and any(save_path.iterdir()):
        print(f"✅ {label} 已存在，跳过：{save_path.name}")
        return True

    print(f"\n{'─'*60}")
    print(f"📥 下载嵌入模型：{repo_id}")
    print(f"   镜像站：{MIRROR}")
    print(f"   目标路径：{save_path}")
    print(f"   预计大小：{size_hint}，请耐心等待...")
    print(f"{'─'*60}")

    if not _check_huggingface_hub():
        return False

    from huggingface_hub import snapshot_download

    try:
        # snapshot_download 下载整个仓库到缓存，返回缓存路径
        cached_path = snapshot_download(
            repo_id=repo_id,
            repo_type="model",
            ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*",
                              "rust_model*", "coreml*", "onnx*"],
        )
        # 将缓存目录复制到项目 models/ 下
        if save_path.exists():
            shutil.rmtree(save_path)
        shutil.copytree(cached_path, save_path)
        print(f"✅ {label} 下载完成：{save_path.name}")
        return True

    except Exception as e:
        print(f"\n❌ {label} 下载失败：{e}")
        print("   建议使用 git-lfs 手动克隆：")
        print(f"   git clone {MIRROR}/{repo_id}  models/{save_dir_name}")
        return False


# ═════════════════════════════════════════════════════════════
#  主入口
# ═════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="下载 D&D Rules AI 本地模型")
    parser.add_argument("--llm",   action="store_true", help="只下载 LLM（Qwen2.5-7B GGUF）")
    parser.add_argument("--emb",   action="store_true", help="只下载两个嵌入模型")
    parser.add_argument("--small", action="store_true", help="只下载小嵌入模型 bge-small-zh-v1.5")
    args = parser.parse_args()

    # 无参数 = 全部下载
    download_all = not (args.llm or args.emb or args.small)

    print("=" * 60)
    print("  D&D Rules AI — 模型下载脚本")
    print(f"  镜像站：{MIRROR}")
    print(f"  模型目录：{MODELS_DIR}")
    print("=" * 60)

    results = {}

    if download_all or args.llm:
        results["LLM (Qwen2.5-7B-Q4_K_M)"] = download_llm()

    if download_all or args.emb:
        results["嵌入大模型 (bge-m3)"] = download_embedding(
            EMB_LARGE_REPO, EMB_LARGE_DIR, "bge-m3", "约 2.3 GB"
        )
        results["嵌入小模型 (bge-small-zh)"] = download_embedding(
            EMB_SMALL_REPO, EMB_SMALL_DIR, "bge-small-zh-v1.5", "约 93 MB"
        )
    elif args.small:
        results["嵌入小模型 (bge-small-zh)"] = download_embedding(
            EMB_SMALL_REPO, EMB_SMALL_DIR, "bge-small-zh-v1.5", "约 93 MB"
        )

    # ── 汇总 ──────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("  下载结果汇总")
    print(f"{'═'*60}")
    all_ok = True
    for name, ok in results.items():
        status = "✅ 成功" if ok else "❌ 失败"
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    if all_ok:
        print(f"\n🎉 全部完成！现在可以启动服务：")
        print(f"   cd src && uvicorn main:app --reload")
    else:
        print(f"\n⚠️  部分模型下载失败，请参考上方错误信息手动处理。")
        print(f"   手动下载后放置路径：{MODELS_DIR}")

    print()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
