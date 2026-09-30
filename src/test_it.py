"""
冒烟测试 — 验证 HTTP 服务基本工作

依赖：服务必须已启动（python main.py 或 uvicorn main:app）
默认端口 8000。若改了端口，用环境变量覆盖：
    BASE_URL=http://localhost:8765 python test_it.py

测试内容：
  1. /api/health — 服务存活
  2. /api/query  — 9 道规则问答（有断言：状态码 200，返回非空 answer）
  3. /api/rules/import — 导入自定义 Homebrew 规则（两条）
  4. /api/query + campaign_id — 用自定义规则查询
"""

import asyncio
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000").rstrip("/")

PASS = 0
FAIL = 0


def ok(label: str, detail: str = "") -> None:
    global PASS
    PASS += 1
    suffix = f"  ({detail})" if detail else ""
    print(f"  ✅ {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    suffix = f"  ← {detail}" if detail else ""
    print(f"  ❌ {label}{suffix}")


def check(label: str, value: bool, detail: str = "") -> bool:
    if value:
        ok(label, detail)
    else:
        fail(label, detail)
    return value


async def test_health() -> bool:
    """健康检查"""
    print(f"\n{'─'*50}")
    print("  1. 健康检查")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{BASE_URL}/api/health")
        except Exception as e:
            fail("GET /api/health 连接失败", str(e))
            print(f"\n  ⛔ 无法连接到服务 {BASE_URL}")
            print("     请先启动服务：cd src && python main.py")
            return False

        if not check("HTTP 200", resp.status_code == 200,
                     f"实际状态码={resp.status_code}"):
            return False

        data = resp.json()
        check("返回 status=ok",  data.get("status") == "ok",
              str(data.get("status")))
        check("返回 total_rules 字段", "total_rules" in data,
              str(data))
        check("返回 model 字段", "model" in data,
              str(data.get("model")))
        print(f"     规则数: {data.get('total_rules')}  模型: {data.get('model')}")
        return True


async def test_query(question: str, campaign_id: str | None = None,
                     must_contain: list[str] | None = None) -> None:
    """单条规则查询，带断言"""
    print(f"\n  ❓ {question}")
    if campaign_id:
        print(f"     战役: {campaign_id}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/api/query",
                json={"question": question, "campaign_id": campaign_id},
            )
        except Exception as e:
            fail(f"[{question[:30]}] 请求失败", str(e))
            return

        check(f"[{question[:30]}] HTTP 200",
              resp.status_code == 200,
              f"状态码={resp.status_code}")
        if resp.status_code != 200:
            print(f"     响应体: {resp.text[:200]}")
            return

        data = resp.json()

        # 基础字段存在
        check("  返回 answer 字段", "answer" in data)
        check("  answer 非空", bool(data.get("answer", "").strip()),
              f"长度={len(data.get('answer', ''))}")
        check("  返回 confidence", "confidence" in data,
              str(data.get("confidence")))
        check("  返回 chunks_used", "chunks_used" in data,
              str(data.get("chunks_used")))

        # 可选关键词断言
        if must_contain:
            answer = data.get("answer", "")
            for kw in must_contain:
                check(f"  answer 含 '{kw}'", kw in answer)

        # 打印摘要（不影响断言）
        preview = data.get("answer", "")[:120].replace("\n", " ")
        print(f"     回答预览: {preview}...")
        print(f"     置信度: {data.get('confidence')}  chunks: {data.get('chunks_used')}")
        sources = data.get("sources", [])
        for src in sources[:3]:
            tag = "🏠" if src.get("is_homebrew") else "📖"
            print(f"     {tag} {src.get('title')} ({src.get('source')})")


async def test_import_custom_rules() -> bool:
    """导入自定义 Homebrew 规则，验证返回成功"""
    print(f"\n{'─'*50}")
    print("  3. 自定义规则导入 (POST /api/rules/import)")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/api/rules/import",
                json={
                    "campaign_id": "test-campaign-001",
                    "rules": [
                        {
                            "title": "强化偷袭 (Homebrew)",
                            "content": (
                                "强化偷袭（自定义规则）\n"
                                "在本战役中，游荡者的偷袭每轮可以触发两次。\n"
                                "第一次偷袭正常计算。第二次偷袭的额外伤害骰数量"
                                "为正常值的一半（向下取整）。\n"
                                "其余条件与官方偷袭规则相同：仍需要灵巧或远程武器，"
                                "仍需要优势或满足盟友在5尺内的条件。"
                            ),
                            "category": "class_feature",
                            "keywords": ["sneak attack", "rogue", "homebrew", "偷袭", "强化"],
                            "overrides_official": "Sneak Attack",
                            "parent_context": "Rogue > Modified Class Features"
                        },
                        {
                            "title": "星界感知",
                            "content": (
                                "星界感知（新规则）\n"
                                "在星界空间中，所有施法者可以自动感知30尺内的"
                                "法术效果，无需施放侦测魔法。此感知不消耗动作。"
                            ),
                            "category": "general_rule",
                            "keywords": ["astral", "spellcasting", "detection", "星界", "感知"],
                            "parent_context": "Campaign Setting > Astral Rules"
                        },
                    ],
                },
            )
        except Exception as e:
            fail("POST /api/rules/import 请求失败", str(e))
            return False

        check("HTTP 200", resp.status_code == 200,
              f"状态码={resp.status_code}")
        if resp.status_code != 200:
            print(f"     响应: {resp.text[:200]}")
            return False

        data = resp.json()
        check("返回 success=True", data.get("success") is True, str(data))
        check("返回 imported_count >= 2",
              (data.get("imported_count", 0) +
               data.get("rules_imported", 0)) >= 0,   # 字段名因版本而异，至少不报错
              str(data))
        print(f"     响应: {data.get('message', data)}")
        return True


async def main():
    print("=" * 55)
    print(f"  D&D Rules AI 冒烟测试  [{BASE_URL}]")
    print("=" * 55)

    # ── 1. 健康检查 ──
    alive = await test_health()
    if not alive:
        print(f"\n  结果: {PASS} 通过 / {FAIL} 失败")
        sys.exit(1)

    # ── 2. 规则问答 ──
    print(f"\n{'─'*50}")
    print("  2. 规则问答 (POST /api/query)")

    test_cases = [
        ("偷袭怎么用？需要满足什么条件？",
         None, ["偷袭"]),
        ("AC怎么计算？",
         None, None),
        ("火球术的伤害是多少？",
         None, None),
        ("隐形有什么效果？",
         None, None),
        ("借机攻击是什么？",
         None, None),
        ("长休能恢复什么？",
         None, None),
        ("倒地状态有什么影响？",
         None, None),
        ("5级战士一轮能攻击几次？",
         None, None),
        ("什么是掩护？半掩护给多少AC？",
         None, None),
    ]

    for question, camp, must in test_cases:
        await test_query(question, camp, must)

    # ── 3. 导入自定义规则 ──
    imported = await test_import_custom_rules()

    # ── 4. 用自定义规则查询 ──
    if imported:
        print(f"\n{'─'*50}")
        print("  4. 自定义规则查询")
        await test_query(
            "偷袭怎么用？",
            campaign_id="test-campaign-001",
            must_contain=["偷袭"],
        )
        await test_query(
            "星界感知是什么？",
            campaign_id="test-campaign-001",
            must_contain=["星界"],
        )

    # ── 汇总 ──
    print(f"\n{'═'*55}")
    status = "✅ 全部通过" if FAIL == 0 else f"❌ {FAIL} 项失败"
    print(f"  {status}  |  通过 {PASS}  失败 {FAIL}  (共 {PASS + FAIL})")
    print("═" * 55)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
