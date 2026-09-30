from contextlib import asynccontextmanager
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import (
    QueryRequest, QueryResponse,
    RuleSource,
)
from config import get_settings
import db
from embedding_service import EmbeddingService
from vector_store import VectorStore
from keyword_store import KeywordStore
from retriever import HybridRetriever
from generator import RuleAnswerGenerator, get_active_mode, set_runtime_mode, probe_local_llm
from rule_importer import RuleImporter
from character.api import router as character_router
from character.storage import init_character_db, get_character, save_character
from character.rule_bridge import build_enriched_question, extract_rule_topics
from monster.api import router as monster_router
from monster.storage import init_monster_db, count_monsters
from campaign.api import router as campaign_router
from campaign.storage import init_campaign_db
from session.storage import init_session_db
from session.api import router as session_router
from maps.api import router as maps_router, editor_router as dungeon_editor_router
from maps.storage import init_map_db
import import_router
from character.api import set_rest_broadcast_hook, set_dm_approval_hooks, set_xp_broadcast_hook
from ws_manager import ConnectionManager
from ws_models import (
    WSMessage, WSMsgType,
    MemberInfo, ChatData, RollRequestData, RollResultData,
    InitiativeUpdateData, SceneUpdateData, CharacterUpdateData,
    RuleQueryData, RuleResultData,
    NpcChatData, NpcResponseData,
    RestCompleteData,
    CreatureMoveData, CreatureHpData, FogUpdateData, PoiRevealData, MapUpdateData,
    TurnAdvanceData, CombatStartData, CombatEndData,
    DeathSaveData, ConditionUpdateData,
    DmApprovalRequestData, DmApprovalResultData, LootGrantData,
    XpGainData,
    ReactionUsedData, CastConcentrationSpellData, OpportunityAttackData,
    CreatureActionData, LegendaryActionData,
    AttackData, AttackResultData,
    SavingThrowData, SavingThrowResultData,
    AoeAttackData, AoeAttackResultData,
    RollInitiativeData, InitiativeEntry,
)
from dice import parse_and_roll, DiceError

# ========== 全局服务实例 ==========
settings = get_settings()
embedding_service = EmbeddingService()

# 用实际维度覆盖配置（本地模型和API模型维度不同）
settings.embedding_dimensions = embedding_service.dimensions

vector_store = VectorStore()          # 这里会用到 embedding_dimensions
keyword_store = KeywordStore()
retriever = HybridRetriever(vector_store, keyword_store, embedding_service)
generator = RuleAnswerGenerator()
importer = RuleImporter(embedding_service, vector_store, keyword_store)
manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化"""
    print("🎲 D&D Rules AI 启动中...")

    # 初始化数据库
    await db.init_db()
    await init_character_db()
    await init_monster_db()
    await init_campaign_db()
    await init_session_db()
    await init_map_db()

    # 检查怪物库，给出提示
    monster_count = await count_monsters()
    if monster_count == 0:
        print("⚠️  怪物库为空！首次部署请运行：")
        print("      python import_monsters.py")
        print("   或设置环境变量 DND5E_CHM_DIR 指向 CHM 资源目录后重新运行")
    else:
        print(f"🐉 怪物库：{monster_count} 只")

    existing = await db.get_all_chunks()
    if not existing:
        print("⚠️  规则库为空，请通过 POST /api/import/rules/htm 导入规则书")
    else:
        print(f"📚 规则库：{len(existing)} 条，重建索引...")
        # 重建内存索引
        embeddings = await embedding_service.embed_texts([
            _chunk_embed_text(c) for c in existing
        ])
        vector_store.upsert_chunks(existing, embeddings)
        keyword_store.build_index(existing)

    # 注入导入路由依赖
    import_router.set_dependencies(importer)

    # auto 模式：启动时探测本地 LLM
    if settings.llm_mode == "auto":
        avail, model, models = await probe_local_llm()
        if avail:
            print(f"🤖 本地 LLM 可达，auto 模式启用本地推理: {model}")
        else:
            print(f"🌐 本地 LLM 不可达，auto 模式回退到 API ({settings.llm_model})")

    # 注入休息广播 Hook（避免 character/api.py 循环导入 main）
    set_rest_broadcast_hook(_broadcast_rest_complete)
    # 注入 DM 审批广播 Hook
    set_dm_approval_hooks(_broadcast_dm_approval_request, _broadcast_dm_approval_result)
    # 注入 XP 增加广播 Hook
    set_xp_broadcast_hook(_broadcast_xp_gain)

    print("✅ D&D Rules AI 就绪！")
    yield
    print("👋 D&D Rules AI 关闭")


def _chunk_embed_text(chunk):
    parts = [f"Title: {chunk.title}", f"Category: {chunk.category.value}"]
    if chunk.parent_context:
        parts.append(f"Context: {chunk.parent_context}")
    parts.append(f"Content: {chunk.content}")
    if chunk.keywords:
        parts.append(f"Keywords: {', '.join(chunk.keywords)}")
    return "\n".join(parts)


# ========== FastAPI App ==========
app = FastAPI(
    title="D&D 5e Rules AI",
    description="D&D 5e 2024 规则查询 AI 系统",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 地图图片静态文件服务
from maps.config import MAPS_DIR as _MAPS_DIR
_MAPS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static/maps", StaticFiles(directory=str(_MAPS_DIR)), name="maps")

# 注册子路由
app.include_router(character_router)
app.include_router(monster_router)
app.include_router(campaign_router)
app.include_router(session_router)
app.include_router(maps_router)
app.include_router(dungeon_editor_router)
app.include_router(import_router.router)


# ========== API 端点 ==========

@app.post("/api/query", response_model=QueryResponse)
async def query_rules(request: QueryRequest):
    """
    查询D&D规则

    示例:
    - "偷袭怎么用？"
    - "AC怎么计算？"
    - "火球术的伤害是多少？"
    - "隐形状态有什么效果？"
    """
    try:
        # 1. 检索相关规则
        chunks = await retriever.retrieve(
            query=request.question,
            campaign_id=request.campaign_id,
        )

        if not chunks:
            return QueryResponse(
                answer="抱歉，没有找到与您问题相关的规则。请尝试换一种方式提问，或检查术语是否正确。",
                sources=[],
                confidence=0.1,
                chunks_used=0
            )

        # 2. 生成回答
        response = await generator.generate(
            question=request.question,
            chunks=chunks,
            conversation_history=request.conversation_history,
        )

        return response

    except Exception as e:
        print(f"❌ Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/character/{character_id}/ask")
async def ask_with_character_context(character_id: str, request: QueryRequest):
    """
    带角色上下文的规则提问。
    会把角色的职业/属性/状态/装备等注入到检索与生成中，
    让 AI 知道"这个问题是谁在问"。

    示例请求体:
        { "question": "我能不能偷袭?" }
    """
    sheet = await get_character(character_id)
    if sheet is None:
        raise HTTPException(status_code=404, detail=f"角色 {character_id} 不存在")

    try:
        # 1. 构建带上下文的增强问题
        enriched = build_enriched_question(request.question, sheet)

        # 2. 检索: 用原问题找规则 + 用角色主题补充
        topics = extract_rule_topics(sheet)
        topic_query = " ".join(topics[:5]) if topics else ""
        combined_query = f"{request.question} {topic_query}".strip()

        chunks = await retriever.retrieve(
            query=combined_query,
            campaign_id=request.campaign_id or sheet.campaign_id,
        )

        if not chunks:
            return QueryResponse(
                answer="抱歉，没有找到与你问题相关的规则。你可以换种说法或给出更多上下文。",
                sources=[],
                confidence=0.1,
                chunks_used=0,
            )

        # 3. 用增强后的问题生成回答
        response = await generator.generate(
            question=enriched,
            chunks=chunks,
            conversation_history=request.conversation_history,
        )
        return response

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error in character ask: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/rules/campaign/{campaign_id}")
async def delete_campaign_rules(campaign_id: str):
    """删除指定战役的所有自定义规则"""
    try:
        await importer.delete_campaign_rules(campaign_id)
        return {"success": True, "message": f"已删除战役 {campaign_id} 的所有自定义规则"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
#  规则库管理（DM 清理 / 维护）
# ============================================================

@app.get("/api/rules")
async def list_rules(
    source: str | None = None,
    status: str | None = None,
    category: str | None = None,
    keyword: str | None = None,
    campaign_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """
    分页列出规则库内容，支持按来源/状态/分类/关键词过滤。

    常用场景：
    - 查看已导入了哪些来源：不填任何过滤，按 source 字段统计
    - 查找某本书所有规则：`?source=PHB 2024`
    - 查找已被禁用的规则：`?status=deprecated`
    - 搜索关键词：`?keyword=偷袭`

    可用 source 值：PHB 2024 / DMG 2024 / MM 2024 / Basic Rules 2024 /
                    SRD 5.1 (2014) / PHB 2014 / Errata / Homebrew
    可用 status 值：active / deprecated / superseded
    """
    chunks, total = await db.list_chunks_paginated(
        source=source,
        status=status,
        category=category,
        keyword=keyword,
        campaign_id=campaign_id,
        limit=min(limit, 200),
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "chunks": [
            {
                "id": c.id,
                "title": c.title,
                "source": c.source.value,
                "category": c.category.value,
                "status": c.status,
                "edition": c.edition,
                "page": c.page,
                "content_preview": c.content[:120] + "…" if len(c.content) > 120 else c.content,
            }
            for c in chunks
        ],
    }


@app.delete("/api/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    删除单条规则（永久删除，不可恢复）。

    建议先用 PATCH /api/rules/{id}/status 禁用，确认无影响再删除。
    删除后内存索引会自动更新。
    """
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="需要 DM 权限")

    chunk = await db.get_chunk_by_id(rule_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"规则不存在：{rule_id}")

    ok = await db.delete_chunk_by_id(rule_id)
    if ok:
        # 从内存索引中移除
        vector_store.delete_chunk(rule_id)
        keyword_store.remove_chunk(rule_id)

    return {
        "success": ok,
        "deleted_id": rule_id,
        "title": chunk.title,
        "message": f"已删除规则：{chunk.title}（{chunk.source.value}）",
    }


@app.delete("/api/rules/source/{source_name}")
async def delete_rules_by_source(
    source_name: str,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    删除某个来源的全部规则（批量永久删除）。

    示例：
    - DELETE /api/rules/source/PHB%202014   → 删除所有 2014 玩家手册规则
    - DELETE /api/rules/source/Homebrew     → 清空所有 Homebrew 规则

    **注意**：此操作不可撤销，建议先用 GET /api/rules?source=xxx 确认范围。
    """
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="需要 DM 权限")

    # 校验来源是否合法
    valid_sources = {s.value for s in RuleSource}
    if source_name not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"未知来源 {source_name!r}，可用值：{', '.join(sorted(valid_sources))}",
        )

    deleted = await db.delete_chunks_by_source(source_name)

    if deleted > 0:
        # 重建内存索引（批量删除后增量更新代价高，直接重建）
        remaining = await db.get_all_chunks()
        keyword_store.build_index(remaining)
        embeddings = await embedding_service.embed_texts([
            f"Title: {c.title}\nContent: {c.content}" for c in remaining
        ])
        vector_store.upsert_chunks(remaining, embeddings)

    return {
        "success": True,
        "source": source_name,
        "deleted_count": deleted,
        "message": f"已删除来源《{source_name}》的 {deleted} 条规则"
                   + ("，内存索引已重建" if deleted > 0 else "（该来源无规则）"),
    }


@app.patch("/api/rules/{rule_id}/status")
async def update_rule_status(
    rule_id: str,
    body: dict,
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    禁用或恢复单条规则（不删除，只修改 status 字段）。

    推荐用法：
    - 禁用：`{"status": "deprecated"}`  → 规则仍在库中但不会被检索到
    - 恢复：`{"status": "active"}`

    与删除的区别：禁用后规则数据保留，随时可以恢复；删除不可撤销。
    """
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="需要 DM 权限")

    new_status = body.get("status", "")
    if new_status not in ("active", "deprecated", "superseded"):
        raise HTTPException(
            status_code=400,
            detail="status 必须是 active / deprecated / superseded",
        )

    chunk = await db.get_chunk_by_id(rule_id)
    if chunk is None:
        raise HTTPException(status_code=404, detail=f"规则不存在：{rule_id}")

    ok = await db.update_chunk_status(rule_id, new_status)

    # deprecated 时从内存索引撤出，active 时重新加入
    if ok:
        if new_status == "deprecated":
            vector_store.delete_chunk(rule_id)
            keyword_store.remove_chunk(rule_id)
        elif new_status == "active":
            embedding = await embedding_service.embed_text(
                f"Title: {chunk.title}\nContent: {chunk.content}"
            )
            vector_store.upsert_chunks([chunk], [embedding])
            keyword_store.add_chunk(chunk)

    action = "禁用" if new_status == "deprecated" else "恢复"
    return {
        "success": ok,
        "rule_id": rule_id,
        "title": chunk.title,
        "old_status": chunk.status,
        "new_status": new_status,
        "message": f"已{action}规则：{chunk.title}（{chunk.source.value}）",
    }


@app.get("/api/settings/llm")
async def get_llm_settings():
    """
    查询当前 LLM 配置和状态。

    返回字段：
    - active_mode: 当前生效模式（"api" 或 "local"）
    - config_mode: .env 中配置的默认模式
    - api_model: API 模式使用的模型名
    - api_base_url: API 模式的服务地址
    - local_url: 本地 LLM 服务地址
    - local_model: 当前本地模型名（空表示未探测）
    - local_available: 本地服务是否可达（null 表示未探测过）
    - local_models: 本地可用模型列表（空表示未探测或不可达）
    """
    from generator import _local_available, _local_model
    return {
        "active_mode": get_active_mode(),
        "config_mode": settings.llm_mode,
        "api_model": settings.llm_model,
        "api_base_url": settings.openai_base_url,
        "local_url": settings.local_llm_url,
        "local_model": _local_model,
        "local_available": _local_available,
        "local_models": [],   # 需要调用 probe 才会填充
    }


@app.post("/api/settings/llm/probe")
async def probe_llm():
    """
    探测本地 LLM 服务是否可达，并返回可用模型列表。
    建议在切换到 local 模式前先调用此接口确认服务在线。
    """
    available, model, models = await probe_local_llm()
    return {
        "available": available,
        "local_url": settings.local_llm_url,
        "selected_model": model,
        "all_models": models,
        "message": (
            f"本地 LLM 可达，找到 {len(models)} 个模型，当前选用: {model}"
            if available
            else f"本地 LLM 不可达，请确认 Ollama/LM Studio 已启动 ({settings.local_llm_url})"
        ),
    }


@app.post("/api/settings/llm/switch")
async def switch_llm_mode(
    mode: str,
    model: str = "",
    x_role: str | None = Header(None, alias="X-Role"),
):
    """
    切换 LLM 模式，无需重启服务。DM 专用。

    - mode="api"   → 切换到 API 模式（DeepSeek / OpenAI 等）
    - mode="local" → 切换到本地 LLM（Ollama / LM Studio）
    - model        → 可选，指定本地模型名；为空则保持当前探测到的模型

    切换到 local 前建议先调用 POST /api/settings/llm/probe 确认服务在线。
    """
    if x_role != "dm":
        raise HTTPException(status_code=403, detail="切换 LLM 模式需要 DM 权限")
    if mode not in ("api", "local"):
        raise HTTPException(status_code=422, detail="mode 必须是 'api' 或 'local'")

    if mode == "local":
        available, detected_model, models = await probe_local_llm()
        if not available:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"本地 LLM 服务不可达 ({settings.local_llm_url})。"
                    "请先启动 Ollama 或 LM Studio，再切换到 local 模式。"
                ),
            )
        chosen = model or detected_model
        set_runtime_mode("local", chosen)
        return {
            "active_mode": "local",
            "model": chosen,
            "all_models": models,
            "message": f"已切换到本地 LLM，使用模型: {chosen}",
        }
    else:
        set_runtime_mode("api")
        return {
            "active_mode": "api",
            "model": settings.llm_model,
            "message": f"已切换到 API 模式，使用模型: {settings.llm_model}",
        }


@app.get("/api/health")
async def health_check():
    chunks = await db.get_all_chunks()
    return {
        "status": "ok",
        "total_rules": len(chunks),
        "model": settings.llm_model,
    }


# 冲突规则处理端点

@app.get("/api/conflicts")
async def list_conflicts(campaign_id: str | None = None):
    """查看所有检测到的规则冲突"""
    # 从数据库获取所有规则，找出有冲突标记的
    chunks = await db.get_all_chunks(campaign_id)

    superseded = [c for c in chunks if c.status == "superseded"]
    overridden = [c for c in chunks if c.is_overridden]
    with_notes = [c for c in chunks if c.errata_note]

    return {
        "total_rules": len(chunks),
        "active_rules": len([c for c in chunks if c.status == "active"]),
        "superseded_rules": len(superseded),
        "overridden_rules": len(overridden),
        "rules_with_notes": len(with_notes),
        "superseded_details": [
            {
                "id": c.id,
                "title": c.title,
                "source": c.source.value,
                "superseded_by": c.superseded_by,
                "note": c.errata_note,
            }
            for c in superseded[:20]
        ],
        "overridden_details": [
            {
                "id": c.id,
                "title": c.title,
                "source": c.source.value,
                "note": c.errata_note,
            }
            for c in overridden[:20]
        ],
    }


@app.post("/api/rules/errata")
async def add_errata(
    title: str,
    content: str,
    note: str = "Official errata update"
):
    """添加勘误更新"""
    conflicts = await importer.import_errata(
        rule_title=title,
        new_content=content,
        errata_note=note,
    )
    return {
        "success": True,
        "conflicts_resolved": len(conflicts),
        "conflicts": [c.model_dump() for c in conflicts],
    }


@app.post("/api/rules/set-edition-preference")
async def set_edition_preference(prefer: str = "2024"):
    """
    设置全局版本偏好
    prefer: "2024" 或 "2014"
    """
    # 这会影响检索时的排序
    return {"message": f"版本偏好已设置为: {prefer}", "prefer": prefer}


# ========== WebSocket 联机 ==========

async def _ws_error(ws: WebSocket, detail: str, in_reply_to: str = "") -> None:
    """向客户端发送 ERROR 消息。"""
    msg = WSMessage(
        type=WSMsgType.ERROR,
        sender="server",
        data={"detail": detail, "in_reply_to": in_reply_to},
    )
    await manager.send_personal(ws, msg)


async def _broadcast_rest_complete(
    campaign_id: str | None,
    character_id: str,
    owner_id: str,
    rest_type: str,
    result,
) -> None:
    """
    休息完成后通过 WS 广播 REST_COMPLETE，通知房间内其他玩家。
    若角色无 campaign_id 则不广播。
    """
    if not campaign_id:
        return
    data = RestCompleteData(
        character_id=character_id,
        owner_id=owner_id,
        rest_type=rest_type,
        hp_gained=result.hp_gained,
        resources_recovered=result.resources_recovered,
        effects_expired=result.effects_expired,
    )
    await manager.broadcast(
        campaign_id,
        WSMessage(type=WSMsgType.REST_COMPLETE, sender="server", data=data.model_dump()),
    )


async def _broadcast_dm_approval_request(campaign_id: str, sheet) -> None:
    """
    非标准角色创建后，通知房间内所有 DM 进行审批。
    若 DM 不在线，消息静默丢弃（下次 DM 连线时可通过 pending_approval API 查询）。
    """
    data = DmApprovalRequestData(
        character_id=sheet.id,
        character_name=sheet.name,
        owner_id=sheet.owner_id,
        owner_display=sheet.owner_display,
        campaign_id=campaign_id,
    )
    msg = WSMessage(type=WSMsgType.DM_APPROVAL_REQUEST, sender="server", data=data.model_dump())
    for dm_ws in manager.get_dm_sockets(campaign_id):
        await manager.send_personal(dm_ws, msg)


async def _broadcast_dm_approval_result(
    campaign_id: str,
    sheet,
    approved: bool,
    note: str = "",
) -> None:
    """审批结果通知角色拥有者。"""
    data = DmApprovalResultData(
        character_id=sheet.id,
        character_name=sheet.name,
        approved=approved,
        dm_note=note,
    )
    msg = WSMessage(type=WSMsgType.DM_APPROVAL_RESULT, sender="server", data=data.model_dump())
    await manager.send_to_member(campaign_id, sheet.owner_id, msg)


async def _broadcast_xp_gain(
    campaign_id: str,
    owner_id: str,
    character_name: str,
    character_id: str,
    xp_result,
    note: str = "",
) -> None:
    """
    XP 增加广播。
    向战役房间内的所有成员发送 xp_gain 消息。
    若 leveled_up=True，客户端应展示升级提示（实际升级需玩家调用 /level-up）。
    """
    data = XpGainData(
        character_id=character_id,
        character_name=character_name,
        owner_id=owner_id,
        xp_gained=xp_result.xp_gained,
        xp_before=xp_result.xp_before,
        xp_after=xp_result.xp_after,
        level_before=xp_result.level_before,
        level_after=xp_result.level_after,
        leveled_up=xp_result.leveled_up,
        xp_to_next=xp_result.xp_to_next,
        note=note,
    )
    await manager.broadcast(
        campaign_id,
        WSMessage(type=WSMsgType.XP_GAIN, sender="server", data=data.model_dump()),
    )


async def _handle_message(
    ws: WebSocket,
    campaign_id: str,
    msg: WSMessage,
    member: MemberInfo,
) -> None:
    """
    分发入站 WebSocket 消息到对应处理器。
    所有异常均在内部捕获并转为 ERROR 消息，保持连接存活。
    """
    sender = member.owner_id

    # ---- PING ----
    if msg.type == WSMsgType.PING:
        await manager.send_personal(
            ws, WSMessage(type=WSMsgType.PONG, sender="server", data={})
        )
        return

    # ---- CHAT ----
    if msg.type == WSMsgType.CHAT:
        try:
            chat = ChatData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CHAT 格式错误: {e}", msg.msg_id)
            return

        out = WSMessage(type=WSMsgType.CHAT, sender=sender, data=chat.model_dump())
        if chat.whisper_to:
            sent = await manager.send_to_member(campaign_id, chat.whisper_to, out)
            if not sent:
                await _ws_error(ws, f"悄悄话目标不在线: {chat.whisper_to}", msg.msg_id)
            else:
                await manager.send_personal(ws, out)  # 回显给发送者
        else:
            await manager.broadcast(campaign_id, out)
        return

    # ---- ROLL ----
    if msg.type == WSMsgType.ROLL:
        try:
            req = RollRequestData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"ROLL 格式错误: {e}", msg.msg_id)
            return

        try:
            result = parse_and_roll(req.expression)
        except DiceError as e:
            await _ws_error(ws, str(e), msg.msg_id)
            return

        is_d20_single = len(result.kept) == 1 and "d20" in result.expression
        roll_result = RollResultData(
            expression=result.expression,
            total=result.total,
            rolls=result.rolls,
            kept=result.kept,
            modifier=result.modifier,
            breakdown=result.breakdown,
            reason=req.reason,
            roller=sender,
            secret=req.secret,
            natural_20=is_d20_single and result.kept[0] == 20,
            natural_1=is_d20_single and result.kept[0] == 1,
        )
        out = WSMessage(
            type=WSMsgType.ROLL_RESULT, sender=sender, data=roll_result.model_dump()
        )
        if req.secret:
            await manager.send_personal(ws, out)
            if not manager.is_dm(ws, campaign_id):
                for dm_ws in manager.get_dm_sockets(campaign_id):
                    await manager.send_personal(dm_ws, out)
        else:
            await manager.broadcast(campaign_id, out)
        return

    # ---- INITIATIVE_UPDATE（仅 DM）----
    if msg.type == WSMsgType.INITIATIVE_UPDATE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "先攻更新需要 DM 权限", msg.msg_id)
            return
        try:
            data = InitiativeUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"INITIATIVE_UPDATE 格式错误: {e}", msg.msg_id)
            return
        manager.update_initiative(campaign_id, data)
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.INITIATIVE_UPDATE, sender=sender, data=data.model_dump()),
        )
        return

    # ---- SCENE_UPDATE（仅 DM）----
    if msg.type == WSMsgType.SCENE_UPDATE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "场景更新需要 DM 权限", msg.msg_id)
            return
        try:
            data = SceneUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"SCENE_UPDATE 格式错误: {e}", msg.msg_id)
            return
        manager.update_scene(campaign_id, data)
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.SCENE_UPDATE, sender=sender, data=data.model_dump()),
        )
        return

    # ---- CHARACTER_UPDATE ----
    if msg.type == WSMsgType.CHARACTER_UPDATE:
        try:
            upd = CharacterUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CHARACTER_UPDATE 格式错误: {e}", msg.msg_id)
            return

        sheet = await get_character(upd.character_id)
        if sheet is None:
            await _ws_error(ws, f"角色不存在: {upd.character_id}", msg.msg_id)
            return
        if sheet.owner_id != sender and not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "无权修改该角色", msg.msg_id)
            return

        try:
            from character.models import CharacterSheet as CS
            if upd.full_sync:
                sheet = CS.model_validate(upd.changed_fields)
            else:
                patched = sheet.model_dump()
                patched.update(upd.changed_fields)
                sheet = CS.model_validate(patched)
        except Exception as e:
            await _ws_error(ws, f"角色数据校验失败: {e}", msg.msg_id)
            return

        sheet = await save_character(sheet)
        out_data = upd.model_dump()
        if upd.full_sync:
            out_data["sheet"] = sheet.model_dump()

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.CHARACTER_UPDATE, sender=sender, data=out_data),
            exclude=ws,
        )
        return

    # ---- RULE_QUERY（单播回复）----
    if msg.type == WSMsgType.RULE_QUERY:
        try:
            qdata = RuleQueryData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"RULE_QUERY 格式错误: {e}", msg.msg_id)
            return

        try:
            chunks = await retriever.retrieve(
                query=qdata.question,
                campaign_id=qdata.campaign_id or campaign_id,
                top_k=qdata.top_k,
            )
            resp = await generator.generate(
                question=qdata.question,
                chunks=chunks,
            )
        except Exception as e:
            await _ws_error(ws, f"规则查询失败: {e}", msg.msg_id)
            return

        result = RuleResultData(
            question=qdata.question,
            answer=resp.answer,
            sources=[s.model_dump() for s in resp.sources],
            confidence=resp.confidence,
            chunks_used=resp.chunks_used,
        )
        await manager.send_personal(
            ws,
            WSMessage(type=WSMsgType.RULE_RESULT, sender="server", data=result.model_dump()),
        )
        return

    # ---- NPC_CHAT（玩家发起 NPC 对话）----
    # 流程：玩家消息广播全员 → RAG 生成建议文本 → 仅发给 DM → DM 修改确认后发 NPC_RESPONSE
    if msg.type == WSMsgType.NPC_CHAT:
        try:
            ndata = NpcChatData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"NPC_CHAT 格式错误: {e}", msg.msg_id)
            return

        # 1. 把玩家的发言广播给全员（让所有人看到对话发生）
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.NPC_CHAT, sender=sender, data=ndata.model_dump()),
        )

        # 2. RAG 生成 NPC 回复建议
        try:
            query = f"{ndata.npc_name}: {ndata.message}"
            cid = ndata.campaign_id or campaign_id
            chunks = await retriever.retrieve(query=query, campaign_id=cid, top_k=ndata.top_k)
            resp = await generator.generate(
                question=f"玩家对 {ndata.npc_name} 说：{ndata.message}",
                chunks=chunks,
            )
        except Exception as e:
            await _ws_error(ws, f"NPC 回复生成失败: {e}", msg.msg_id)
            return

        # 3. 生成建议只发给 DM，附带 is_suggestion 标记，DM 可修改后再确认
        suggestion = NpcResponseData(
            npc_name=ndata.npc_name,
            response=resp.answer,
            sources=[s.model_dump() for s in resp.sources],
            confidence=resp.confidence,
            triggered_by=sender,
            is_suggestion=True,
        )
        suggestion_msg = WSMessage(
            type=WSMsgType.NPC_RESPONSE,
            sender="server",
            data=suggestion.model_dump(),
        )
        for dm_ws in manager.get_dm_sockets(campaign_id):
            await manager.send_personal(dm_ws, suggestion_msg)
        return

    # ---- NPC_RESPONSE（DM 确认/修改后的 NPC 发言，广播给全员）----
    if msg.type == WSMsgType.NPC_RESPONSE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "NPC 回复需要 DM 权限", msg.msg_id)
            return
        try:
            nresp = NpcResponseData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"NPC_RESPONSE 格式错误: {e}", msg.msg_id)
            return

        # 强制清除 is_suggestion 标记，再广播给全员
        nresp.is_suggestion = False
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.NPC_RESPONSE, sender=sender, data=nresp.model_dump()),
        )
        return

    # ================================================================
    #  Phase D3 — 地图 + 休息 WS 处理（含 DM 专属过滤）
    # ================================================================

    # ---- CREATURE_MOVE（DM 移动棋盘生物）----
    if msg.type == WSMsgType.CREATURE_MOVE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "生物移动需要 DM 权限", msg.msg_id)
            return
        try:
            mv = CreatureMoveData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CREATURE_MOVE 格式错误: {e}", msg.msg_id)
            return

        # 更新 DB（先记录旧坐标用于机会攻击检测）
        old_x: int | None = None
        old_y: int | None = None
        emap_for_oa = None
        try:
            from maps.storage import get_encounter_map, save_encounter_map
            emap = await get_encounter_map(mv.encounter_map_id)
            if emap:
                target = next((c for c in emap.creatures if c.instance_id == mv.instance_id), None)
                if target:
                    old_x, old_y = target.x, target.y
                    target.x, target.y = mv.x, mv.y
                    await save_encounter_map(emap)
                    emap_for_oa = emap
        except Exception as e:
            await _ws_error(ws, f"棋盘更新失败: {e}", msg.msg_id)
            return

        # 更新 RoomState 缓存（保证重连 SYNC 能下发最新位置）
        manager.update_creature_position(
            campaign_id, mv.instance_id, mv.x, mv.y, actor_id=sender
        )

        # 广播给所有人（隐藏生物的移动也广播；前端负责不渲染隐藏生物）
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.CREATURE_MOVE, sender=sender, data=mv.model_dump()),
        )

        # ---- 机会攻击检测（仅战斗中，且有旧坐标时）----
        state_oa = manager.get_room_state(campaign_id)
        if state_oa.initiative and old_x is not None and emap_for_oa:
            try:
                from character.opportunity_attack import provokes_opportunity_attack
                mover = next(
                    (c for c in emap_for_oa.creatures if c.instance_id == mv.instance_id), None
                )
                if mover:
                    provoked = provokes_opportunity_attack(
                        mover, old_x, old_y, mv.x, mv.y, emap_for_oa.creatures
                    )
                    for attacker in provoked:
                        oa_data = OpportunityAttackData(
                            encounter_map_id=mv.encounter_map_id,
                            attacker_instance_id=attacker.instance_id,
                            attacker_name=attacker.name,
                            mover_instance_id=mv.instance_id,
                            mover_name=mover.name,
                            attacker_is_player=attacker.is_player,
                        )
                        await manager.broadcast(
                            campaign_id,
                            WSMessage(type=WSMsgType.OPPORTUNITY_ATTACK, sender="server",
                                      data=oa_data.model_dump()),
                        )
            except Exception:
                pass
        return

    # ---- CREATURE_HP（DM 更新生物 HP）----
    if msg.type == WSMsgType.CREATURE_HP:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "HP 修改需要 DM 权限", msg.msg_id)
            return
        try:
            hp_data = CreatureHpData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CREATURE_HP 格式错误: {e}", msg.msg_id)
            return

        # 更新 DB（遭遇地图生物 HP）
        creature_char_id: str = ""   # 若该生物对应一个 PC，记录其 character_id
        try:
            from maps.storage import get_encounter_map, save_encounter_map
            emap = await get_encounter_map(hp_data.encounter_map_id)
            if emap:
                target = next((c for c in emap.creatures if c.instance_id == hp_data.instance_id), None)
                if target:
                    target.hp_current = max(0, hp_data.hp_current)
                    await save_encounter_map(emap)
                    if target.character_id:
                        creature_char_id = target.character_id
                    # 更新 RoomState 缓存（重连 SYNC 能下发最新 HP）
                    manager.update_creature_hp_in_room(
                        campaign_id, hp_data.instance_id, max(0, hp_data.hp_current)
                    )
        except Exception:
            pass   # HP 更新失败不中断广播

        # ---- HP=0 自动处理 ----
        # 若目标是玩家角色且 HP 降至 0：
        #   1. 自动施加 UNCONSCIOUS 状态
        #   2. 打断集中法术
        #   3. 广播 CONDITION_UPDATE 通知所有人
        if hp_data.hp_current <= 0 and creature_char_id:
            import asyncio as _asyncio
            async def _handle_drop_to_zero(char_id: str):
                try:
                    from character.models import Condition as _Cond
                    from character.effects_engine import _break_concentration
                    ch = await get_character(char_id)
                    if ch and ch.hit_points.current > 0:
                        # 更新角色卡 HP + 施加 Unconscious + 打断集中
                        new_hp = ch.hit_points.model_copy(update={"current": 0})
                        conds = list(ch.conditions)
                        if _Cond.UNCONSCIOUS not in conds:
                            conds.append(_Cond.UNCONSCIOUS)
                        ch = ch.model_copy(update={"hit_points": new_hp, "conditions": conds})
                        if ch.concentration_effect_id:
                            _break_concentration(ch)
                        await save_character(ch)
                        # 广播 CONDITION_UPDATE
                        cond_upd = ConditionUpdateData(
                            target_id=char_id,
                            target_type="character",
                            condition="unconscious",
                            action="add",
                        )
                        await manager.broadcast(
                            campaign_id,
                            WSMessage(type=WSMsgType.CONDITION_UPDATE, sender="server",
                                      data=cond_upd.model_dump()),
                        )
                except Exception as _e:
                    pass
            _asyncio.create_task(_handle_drop_to_zero(creature_char_id))

        # ---- 集中检定（自动掷骰 + 自动判定）----
        # 若受伤角色正在集中：自动掷 CON 豁免，失败则打断集中并广播结果
        if hp_data.damage_taken > 0 and creature_char_id:
            import asyncio as _asyncio
            async def _auto_concentration_check(char_id: str, damage: int):
                try:
                    from character.concentration import on_damage_received as _conc_check
                    ch = await get_character(char_id)
                    if not (ch and ch.concentration_effect_id):
                        return
                    conc_effect = next(
                        (e for e in ch.active_effects if e.id == ch.concentration_effect_id),
                        None,
                    )
                    conc_name = conc_effect.name if conc_effect else "集中法术"

                    updated_ch, event = _conc_check(ch, damage)
                    if event is None:
                        return  # 没有集中，不处理

                    # 持久化（无论成功失败都保存，失败时 concentration_effect_id 已清除）
                    await save_character(updated_ch)

                    dc    = event["dc"]
                    total = event["total"]
                    success = event["success"]
                    auto_fail = event.get("auto_fail", False)

                    if auto_fail:
                        result_text = f"自动失败（已失能/倒地）"
                    else:
                        result_text = f"投出 {total} vs DC {dc} — {'成功' if success else '失败'}"

                    broke_text = f"，【{conc_name}】被打断！" if not success else f"，维持【{conc_name}】"
                    msg_text = f"{ch.name} 受到 {damage} 点伤害，集中检定：{result_text}{broke_text}"

                    notify_msg = WSMessage(
                        type=WSMsgType.CHAT,
                        sender="server",
                        data={
                            "text": msg_text,
                            "is_ooc": True,
                            "concentration_result": {
                                "character_id": char_id,
                                "spell": conc_name,
                                "dc": dc,
                                "total": total,
                                "success": success,
                                "concentration_broken": not success,
                            },
                        },
                    )
                    # 广播给全员（集中成功/失败是公开信息）
                    await manager.broadcast(campaign_id, notify_msg)
                except Exception:
                    pass
            _asyncio.create_task(_auto_concentration_check(creature_char_id, hp_data.damage_taken))

        # DM 收到完整数据；玩家只收到模糊 HP 状态
        dm_msg = WSMessage(type=WSMsgType.CREATURE_HP, sender=sender, data=hp_data.model_dump())
        player_data = hp_data.model_dump()
        if not hp_data.is_hidden:
            # 非隐藏生物：玩家侧 HP 模糊化（只给 hp_status）
            ratio = hp_data.hp_current / hp_data.hp_max if hp_data.hp_max > 0 else 0
            if hp_data.hp_current <= 0:
                player_data["hp_status"] = "倒下"
            elif ratio > 0.75:
                player_data["hp_status"] = "状态良好"
            elif ratio > 0.5:
                player_data["hp_status"] = "轻微受伤"
            elif ratio > 0.25:
                player_data["hp_status"] = "重伤"
            else:
                player_data["hp_status"] = "濒死"
            player_data["hp_current"] = None   # 玩家看不到具体数值
            player_data["hp_max"] = None

        player_msg = WSMessage(type=WSMsgType.CREATURE_HP, sender=sender, data=player_data)

        room = manager._rooms.get(campaign_id, {})
        from starlette.websockets import WebSocketState
        for room_ws, member_info in list(room.items()):
            try:
                if room_ws.client_state != WebSocketState.CONNECTED:
                    continue
                if member_info.is_dm:
                    await manager.send_personal(room_ws, dm_msg)
                elif not hp_data.is_hidden:
                    await manager.send_personal(room_ws, player_msg)
            except Exception:
                pass
        return

    # ---- FOG_UPDATE（DM 操作迷雾）----
    if msg.type == WSMsgType.FOG_UPDATE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "迷雾操作需要 DM 权限", msg.msg_id)
            return
        try:
            fog = FogUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"FOG_UPDATE 格式错误: {e}", msg.msg_id)
            return
        # 广播给所有人（客户端根据已揭示格子渲染迷雾）
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.FOG_UPDATE, sender=sender, data=fog.model_dump()),
        )
        return

    # ---- POI_REVEAL（DM 揭示大地图地点）----
    if msg.type == WSMsgType.POI_REVEAL:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "地点揭示需要 DM 权限", msg.msg_id)
            return
        try:
            poi_data = PoiRevealData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"POI_REVEAL 格式错误: {e}", msg.msg_id)
            return

        # 更新 DB：标记 POI 为已揭示
        try:
            from maps.storage import get_campaign_world_map, save_world_map
            wmap = await get_campaign_world_map(campaign_id)
            if wmap:
                for poi in wmap.pois:
                    if poi.id == poi_data.poi_id:
                        poi.is_hidden = False
                        break
                await save_world_map(wmap)
        except Exception:
            pass

        reveal_msg = WSMessage(type=WSMsgType.POI_REVEAL, sender=sender, data=poi_data.model_dump())

        # 广播给指定玩家（或所有人）
        if poi_data.visible_to:
            for target_owner in poi_data.visible_to:
                await manager.send_to_member(campaign_id, target_owner, reveal_msg)
            # DM 自己也收到回执
            await manager.send_personal(ws, reveal_msg)
        else:
            await manager.broadcast(campaign_id, reveal_msg)
        return

    # ---- REST_COMPLETE（休息完成，服务器广播）----
    # 注意：此消息类型由 HTTP REST 端点触发，经 WS 广播通知其他玩家
    # 直接客户端发来的 REST_COMPLETE 忽略（防止伪造）
    if msg.type == WSMsgType.REST_COMPLETE:
        # 不接受客户端发起，只由服务器内部发送
        await _ws_error(ws, "REST_COMPLETE 消息不可由客户端发起", msg.msg_id)
        return

    # ---- MAP_UPDATE（通用地图更新推送，仅服务器发出）----
    if msg.type == WSMsgType.MAP_UPDATE:
        # 仅 DM 可手动触发地图全量同步推送
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "地图更新需要 DM 权限", msg.msg_id)
            return
        try:
            map_upd = MapUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"MAP_UPDATE 格式错误: {e}", msg.msg_id)
            return
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.MAP_UPDATE, sender=sender, data=map_upd.model_dump()),
        )
        return

    # ================================================================
    #  战斗回合推进 + 死亡豁免 + 状态异常（Phase E 续）
    # ================================================================

    # ---- COMBAT_START（DM 开启战斗）----
    if msg.type == WSMsgType.COMBAT_START:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "开始战斗需要 DM 权限", msg.msg_id)
            return
        try:
            csd = CombatStartData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"COMBAT_START 格式错误: {e}", msg.msg_id)
            return
        # 重置回合计数到 1，保留现有先攻列表
        state = manager.get_room_state(campaign_id)
        from ws_models import InitiativeEntry as WSInitEntry
        existing_entries = [WSInitEntry.model_validate(e) for e in state.initiative]
        manager.update_initiative(campaign_id, InitiativeUpdateData(
            entries=existing_entries,
            current_turn=0,
            round_number=1,
        ))

        # 重置所有玩家角色与怪物的动作资源（行动/附赠动作/反应/移动力）
        import asyncio as _asyncio
        async def _reset_all_action_economy():
            # 重置玩家角色
            for entry in existing_entries:
                if entry.character_id:
                    try:
                        ch = await get_character(entry.character_id)
                        if ch:
                            ch = ch.model_copy(update={
                                "action_used": False,
                                "bonus_action_used": False,
                                "reaction_used": False,
                                "movement_used": 0,
                            })
                            await save_character(ch)
                    except Exception:
                        pass
            # 重置遭遇战地图上所有怪物
            try:
                from maps.storage import get_encounter_map, save_encounter_map
                _state = manager.get_room_state(campaign_id)
                if _state.active_encounter_map_id:
                    emap = await get_encounter_map(_state.active_encounter_map_id)
                    if emap:
                        changed = False
                        for mc in emap.creatures:
                            if mc.movement_used != 0 or mc.action_used \
                                    or mc.bonus_action_used or mc.reaction_used \
                                    or mc.legendary_actions_used != 0:
                                mc.movement_used = 0
                                mc.action_used = False
                                mc.bonus_action_used = False
                                mc.reaction_used = False
                                mc.legendary_actions_used = 0
                                changed = True
                        if changed:
                            await save_encounter_map(emap)
            except Exception:
                pass
        _asyncio.create_task(_reset_all_action_economy())

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.COMBAT_START, sender=sender, data=csd.model_dump()),
        )
        return

    # ---- COMBAT_END（DM 结束战斗，重置动作资源）----
    if msg.type == WSMsgType.COMBAT_END:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "结束战斗需要 DM 权限", msg.msg_id)
            return
        try:
            ced = CombatEndData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"COMBAT_END 格式错误: {e}", msg.msg_id)
            return
        # 清空先攻列表，回合归零
        manager.update_initiative(campaign_id, InitiativeUpdateData(
            entries=[], current_turn=0, round_number=0
        ), actor_id=sender)
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.COMBAT_END, sender=sender, data=ced.model_dump()),
        )
        return

    # ---- TURN_ADVANCE（推进到下一行动者）----
    if msg.type == WSMsgType.TURN_ADVANCE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "回合推进需要 DM 权限", msg.msg_id)
            return

        state = manager.get_room_state(campaign_id)
        if not state.initiative:
            await _ws_error(ws, "先攻列表为空，无法推进回合", msg.msg_id)
            return

        from ws_models import InitiativeEntry as WSInitEntry
        entries = [WSInitEntry.model_validate(e) for e in state.initiative]
        active_entries = [e for e in entries if e.active]
        if not active_entries:
            await _ws_error(ws, "没有活跃参与者，无法推进回合", msg.msg_id)
            return

        old_turn = state.current_turn
        old_round = state.round_number

        # 找下一个 active 参与者（跳过非活跃）
        n = len(entries)
        next_idx = (old_turn + 1) % n
        loops = 0
        while not entries[next_idx].active and loops < n:
            next_idx = (next_idx + 1) % n
            loops += 1

        round_started = next_idx <= old_turn   # 索引回绕说明进入新一轮
        new_round = old_round + 1 if round_started else old_round
        active = entries[next_idx]

        # 重置当前行动者的动作经济
        if active.character_id:
            try:
                ch = await get_character(active.character_id)
                if ch:
                    ch = ch.model_copy(update={
                        "action_used": False,
                        "bonus_action_used": False,
                        "reaction_used": False,
                        "movement_used": 0,
                    })
                    import asyncio as _asyncio
                    _asyncio.create_task(save_character(ch))
            except Exception:
                pass
        else:
            # 怪物回合开始，重置该生物的全部行动经济（移动力 + 行动/附赠动作/反应）
            try:
                emap_id = state.active_encounter_map_id
                if emap_id:
                    from maps.storage import get_encounter_map, save_encounter_map
                    emap = await get_encounter_map(emap_id)
                    if emap:
                        monster_c = next(
                            (c for c in emap.creatures if c.instance_id == active.id), None
                        )
                        if monster_c:
                            needs_save = any([
                                monster_c.movement_used != 0,
                                monster_c.action_used,
                                monster_c.bonus_action_used,
                                monster_c.reaction_used,
                                monster_c.legendary_actions_used != 0,
                            ])
                            if needs_save:
                                monster_c.movement_used = 0
                                monster_c.action_used = False
                                monster_c.bonus_action_used = False
                                monster_c.reaction_used = False
                                monster_c.legendary_actions_used = 0  # 轮到自己时重置传奇动作
                                import asyncio as _asyncio
                                _asyncio.create_task(save_encounter_map(emap))
            except Exception:
                pass

        # 更新 session 内存状态并持久化
        new_init = InitiativeUpdateData(
            entries=entries,
            current_turn=next_idx,
            round_number=new_round,
        )
        manager.update_initiative(campaign_id, new_init, actor_id=sender)

        adv_data = TurnAdvanceData(
            current_turn=next_idx,
            round_number=new_round,
            active_entry_id=active.id,
            active_entry_name=active.name,
            round_started=round_started,
        )
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.TURN_ADVANCE, sender=sender, data=adv_data.model_dump()),
        )
        return

    # ---- DEATH_SAVE（玩家为其角色掷死亡豁免）----
    if msg.type == WSMsgType.DEATH_SAVE:
        try:
            ds_req = DeathSaveData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"DEATH_SAVE 格式错误: {e}", msg.msg_id)
            return

        sheet = await get_character(ds_req.character_id)
        if sheet is None:
            await _ws_error(ws, f"角色不存在: {ds_req.character_id}", msg.msg_id)
            return
        # 只有角色本人或 DM 可以操作
        if sheet.owner_id != sender and not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "无权操作该角色的死亡豁免", msg.msg_id)
            return
        # HP > 0 时不需要死亡豁免
        if sheet.hit_points.current > 0:
            await _ws_error(ws, "角色 HP > 0，无需进行死亡豁免", msg.msg_id)
            return

        roll = ds_req.roll
        saves = sheet.hit_points.death_saves.model_copy()

        is_nat20 = roll == 20
        is_nat1 = roll == 1

        if is_nat20:
            # 自然 20：立即稳定
            saves = saves.model_copy(update={"stable": True, "successes": 3})
        elif is_nat1:
            # 自然 1：记 2 次失败
            saves = saves.model_copy(update={"failures": min(3, saves.failures + 2)})
        elif roll >= 10:
            saves = saves.model_copy(update={"successes": min(3, saves.successes + 1)})
        else:
            saves = saves.model_copy(update={"failures": min(3, saves.failures + 1)})

        # 判断最终状态
        is_stable = is_nat20 or saves.successes >= 3
        is_dead = saves.failures >= 3

        if is_stable:
            saves = saves.model_copy(update={"stable": True})

        # 持久化
        new_hp = sheet.hit_points.model_copy(update={"death_saves": saves})
        sheet = sheet.model_copy(update={"hit_points": new_hp})
        import asyncio as _asyncio
        _asyncio.create_task(save_character(sheet))

        result_data = DeathSaveData(
            character_id=ds_req.character_id,
            roll=roll,
            is_success=roll >= 10 or is_nat20,
            successes=saves.successes,
            failures=saves.failures,
            is_stable=is_stable,
            is_dead=is_dead,
            natural_20=is_nat20,
            natural_1=is_nat1,
        )
        # 广播给全员（死亡豁免结果公开）
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.DEATH_SAVE, sender=sender, data=result_data.model_dump()),
        )
        return

    # ---- CONDITION_UPDATE（DM 施加/移除状态异常）----
    if msg.type == WSMsgType.CONDITION_UPDATE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "状态异常操作需要 DM 权限", msg.msg_id)
            return
        try:
            cond = ConditionUpdateData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CONDITION_UPDATE 格式错误: {e}", msg.msg_id)
            return

        if cond.target_type == "character":
            # 修改角色的 conditions 列表
            sheet = await get_character(cond.target_id)
            if sheet is None:
                await _ws_error(ws, f"角色不存在: {cond.target_id}", msg.msg_id)
                return
            try:
                from character.models import Condition as CondEnum
                c_val = CondEnum(cond.condition)
            except ValueError:
                await _ws_error(ws, f"未知状态: {cond.condition}", msg.msg_id)
                return

            current = list(sheet.conditions)
            if cond.action == "add":
                if c_val not in current:
                    current.append(c_val)
            elif cond.action == "remove":
                current = [c for c in current if c != c_val]
            else:
                await _ws_error(ws, f"action 必须为 add 或 remove，收到: {cond.action}", msg.msg_id)
                return

            sheet = sheet.model_copy(update={"conditions": current})
            import asyncio as _asyncio
            _asyncio.create_task(save_character(sheet))

        elif cond.target_type == "creature":
            # 修改遭遇地图上怪物的状态
            if not cond.encounter_map_id:
                await _ws_error(ws, "creature 目标需要提供 encounter_map_id", msg.msg_id)
                return
            try:
                from maps.storage import get_encounter_map, save_encounter_map
                emap = await get_encounter_map(cond.encounter_map_id)
                if emap:
                    target_c = next(
                        (c for c in emap.creatures if c.instance_id == cond.target_id), None
                    )
                    if target_c:
                        if cond.action == "add" and cond.condition not in target_c.conditions:
                            target_c.conditions.append(cond.condition)
                        elif cond.action == "remove":
                            target_c.conditions = [
                                c for c in target_c.conditions if c != cond.condition
                            ]
                        import asyncio as _asyncio
                        _asyncio.create_task(save_encounter_map(emap))
            except Exception as e:
                await _ws_error(ws, f"状态更新失败: {e}", msg.msg_id)
                return
        else:
            await _ws_error(ws, f"未知 target_type: {cond.target_type}", msg.msg_id)
            return

        # 广播给所有人
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.CONDITION_UPDATE, sender=sender, data=cond.model_dump()),
        )
        return

    # ---- REACTION_USED（玩家消耗反应动作）----
    if msg.type == WSMsgType.REACTION_USED:
        try:
            ru = ReactionUsedData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"REACTION_USED 格式错误: {e}", msg.msg_id)
            return
        try:
            ch = await get_character(ru.character_id)
            if ch is None:
                await _ws_error(ws, f"角色不存在: {ru.character_id}", msg.msg_id)
                return
            ch = ch.model_copy(update={"reaction_used": True})
            import asyncio as _asyncio
            _asyncio.create_task(save_character(ch))
        except Exception as e:
            await _ws_error(ws, f"反应消耗失败: {e}", msg.msg_id)
            return
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.REACTION_USED, sender=sender, data=ru.model_dump()),
        )
        return

    # ---- CAST_CONCENTRATION_SPELL（玩家施放集中法术）----
    if msg.type == WSMsgType.CAST_CONCENTRATION_SPELL:
        try:
            ccs = CastConcentrationSpellData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CAST_CONCENTRATION_SPELL 格式错误: {e}", msg.msg_id)
            return
        try:
            ch = await get_character(ccs.character_id)
            if ch is None:
                await _ws_error(ws, f"角色不存在: {ccs.character_id}", msg.msg_id)
                return
            # 确认 effect_id 存在于 active_effects
            effect = next((e for e in ch.active_effects if e.id == ccs.effect_id), None)
            if effect is None:
                await _ws_error(ws, f"ActiveEffect {ccs.effect_id} 不存在于角色表", msg.msg_id)
                return
            # 若有旧集中，先解除
            if ch.concentration_effect_id and ch.concentration_effect_id != ccs.effect_id:
                from character.effects_engine import _break_concentration as _brk
                _brk(ch)
            ch.concentration_effect_id = ccs.effect_id
            import asyncio as _asyncio
            _asyncio.create_task(save_character(ch))
        except Exception as e:
            await _ws_error(ws, f"集中法术设置失败: {e}", msg.msg_id)
            return
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.CAST_CONCENTRATION_SPELL, sender=sender, data=ccs.model_dump()),
        )
        return

    # ---- LOOT_GRANT（DM 广播战利品/XP 消息）----
    if msg.type == WSMsgType.LOOT_GRANT:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "战利品分配需要 DM 权限", msg.msg_id)
            return
        try:
            loot = LootGrantData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"LOOT_GRANT 格式错误: {e}", msg.msg_id)
            return

        loot_msg = WSMessage(type=WSMsgType.LOOT_GRANT, sender=sender, data=loot.model_dump())
        if loot.recipient_ids:
            # 只发给指定角色的玩家
            for owner in loot.recipient_ids:
                await manager.send_to_member(campaign_id, owner, loot_msg)
            await manager.send_personal(ws, loot_msg)   # DM 自己也收到确认
        else:
            await manager.broadcast(campaign_id, loot_msg)
        return

    # ---- XP_GAIN（DM 手动广播 XP 分配，或客户端转播 REST API 结果）----
    if msg.type == WSMsgType.XP_GAIN:
        # 任何人均可广播 XP 结果（通常是 DM 通过 REST API 授予 XP 后由服务器广播）
        # 此处允许客户端直接发送 XP_GAIN 消息（例如：转播 REST 端点的返回值）
        try:
            xp_data = XpGainData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"XP_GAIN 格式错误: {e}", msg.msg_id)
            return
        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.XP_GAIN, sender=sender, data=xp_data.model_dump()),
        )
        return

    # ---- ATTACK（攻击解算管道）----
    if msg.type == WSMsgType.ATTACK:
        try:
            atk = AttackData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"ATTACK 格式错误: {e}", msg.msg_id)
            return

        # 权限：DM 可以操作任何攻击；玩家只能用自己的角色发起攻击
        is_dm_sender = manager.is_dm(ws, campaign_id)
        if not is_dm_sender:
            if not atk.attacker_character_id:
                await _ws_error(ws, "玩家只能用自己的角色发起攻击", msg.msg_id)
                return

        from maps.storage import get_encounter_map, save_encounter_map
        from character.calculator import (
            compute_ac, weapon_attack_bonus, spell_attack_bonus,
        )
        from character.damage import calculate_weapon_damage
        from character.concentration import on_damage_received as _conc_check

        # ── 1. 加载遭遇战地图 ──────────────────────────────
        try:
            emap = await get_encounter_map(atk.encounter_map_id)
        except Exception as e:
            await _ws_error(ws, f"加载地图失败: {e}", msg.msg_id)
            return
        if emap is None:
            await _ws_error(ws, f"遭遇战地图不存在: {atk.encounter_map_id}", msg.msg_id)
            return

        # ── 2. 解析攻击者 ──────────────────────────────────
        attacker_name = ""
        attacker_sheet = None
        attacker_creature = None

        if atk.attacker_character_id:
            attacker_sheet = await get_character(atk.attacker_character_id)
            if attacker_sheet is None:
                await _ws_error(ws, f"攻击者角色不存在: {atk.attacker_character_id}", msg.msg_id)
                return
            # 权限校验：玩家只能操作自己的角色
            if not is_dm_sender and attacker_sheet.owner_id != sender:
                await _ws_error(ws, "无权操作该角色发动攻击", msg.msg_id)
                return
            attacker_name = attacker_sheet.name
        elif atk.attacker_instance_id:
            attacker_creature = next(
                (c for c in emap.creatures if c.instance_id == atk.attacker_instance_id), None
            )
            if attacker_creature is None:
                await _ws_error(ws, f"攻击者生物不存在: {atk.attacker_instance_id}", msg.msg_id)
                return
            attacker_name = attacker_creature.name
        else:
            await _ws_error(ws, "必须指定攻击者（attacker_character_id 或 attacker_instance_id）", msg.msg_id)
            return

        # ── 3. 解析目标 ────────────────────────────────────
        target_name = ""
        target_sheet = None          # 目标是玩家角色时有值
        target_creature = None       # 目标是地图生物时有值
        target_monster = None        # 目标地图生物对应的 Monster 数据（若有）
        target_ac = 10
        target_resistances: list[str] = []
        target_immunities:  list[str] = []
        target_vulnerabilities: list[str] = []
        target_hp_before = 0

        if atk.target_character_id:
            target_sheet = await get_character(atk.target_character_id)
            if target_sheet is None:
                await _ws_error(ws, f"目标角色不存在: {atk.target_character_id}", msg.msg_id)
                return
            target_name = target_sheet.name
            target_ac = compute_ac(target_sheet)
            target_hp_before = target_sheet.hit_points.current
        elif atk.target_instance_id:
            target_creature = next(
                (c for c in emap.creatures if c.instance_id == atk.target_instance_id), None
            )
            if target_creature is None:
                await _ws_error(ws, f"目标生物不存在: {atk.target_instance_id}", msg.msg_id)
                return
            target_name = target_creature.name
            target_hp_before = target_creature.hp_current
            # 加载怪物数据（AC、抗性等）
            if target_creature.monster_id:
                try:
                    from monster.storage import get_monster
                    target_monster = await get_monster(target_creature.monster_id)
                except Exception:
                    pass
            if target_monster:
                target_ac = target_monster.ac
                target_resistances   = target_monster.damage_resistances
                target_immunities    = target_monster.damage_immunities
                target_vulnerabilities = target_monster.damage_vulnerabilities
            else:
                # 无 Monster 数据时：尝试用 MapCreature 的 hp_max 估算，AC 默认 10
                target_ac = 10
            # 若目标是玩家角色对应的地图代理，从 CharacterSheet 读 AC
            if target_creature.character_id:
                try:
                    proxy_sheet = await get_character(target_creature.character_id)
                    if proxy_sheet:
                        target_ac = compute_ac(proxy_sheet)
                        # 角色的抗性信息暂不处理（通常由玩家/DM 裁定）
                except Exception:
                    pass
        else:
            await _ws_error(ws, "必须指定目标（target_character_id 或 target_instance_id）", msg.msg_id)
            return

        # ── 4. 计算命中加值 ────────────────────────────────
        to_hit_bonus = atk.to_hit_bonus
        if atk.auto_calculate and attacker_sheet:
            try:
                if atk.attack_type == "spell":
                    bonus = spell_attack_bonus(attacker_sheet)
                    to_hit_bonus = bonus if bonus is not None else 0
                elif atk.attack_type == "unarmed":
                    from character.models import AbilityName
                    str_mod = attacker_sheet.ability_scores.modifier(AbilityName.STR)
                    to_hit_bonus = str_mod + attacker_sheet.proficiency_bonus
                else:
                    # weapon：查背包
                    weapon = next(
                        (it for it in attacker_sheet.inventory
                         if it.name.lower() == atk.weapon_name.lower()),
                        None
                    )
                    if weapon:
                        to_hit_bonus = weapon_attack_bonus(attacker_sheet, weapon)
                    else:
                        # 找不到武器 → 徒手打击
                        from character.models import AbilityName
                        str_mod = attacker_sheet.ability_scores.modifier(AbilityName.STR)
                        to_hit_bonus = str_mod + attacker_sheet.proficiency_bonus
            except Exception:
                to_hit_bonus = atk.to_hit_bonus   # 回退到手动值

        # ── 5. 投命中骰 ────────────────────────────────────
        adv_map = {"advantage": "1d20adv", "disadvantage": "1d20dis"}
        dice_expr = adv_map.get(atk.advantage, "1d20")
        hit_result = parse_and_roll(dice_expr)
        # 对优势/劣势，原始 d20 取 kept[0]（已是高/低值）
        raw_d20 = hit_result.kept[0]

        is_crit      = raw_d20 == 20
        is_crit_fail = raw_d20 == 1
        total_to_hit = raw_d20 + to_hit_bonus
        is_hit = is_crit or (not is_crit_fail and total_to_hit >= target_ac)

        # ── 6. 伤害计算（仅命中时）─────────────────────────
        dmg_result: dict = {}
        damage_final = 0
        if is_hit:
            # 从攻击者角色卡提取能力修正和魔法加值（用于 weapon/unarmed；法术不加）
            ability_mod = 0
            magical_bonus = atk.magical_bonus
            if attacker_sheet and atk.attack_type != "spell":
                try:
                    from character.models import AbilityName, WeaponProperty
                    _props: set = set()
                    _weapon = next(
                        (it for it in attacker_sheet.inventory
                         if it.name.lower() == atk.weapon_name.lower()),
                        None
                    )
                    if _weapon:
                        _props = set(_weapon.weapon_properties)
                        magical_bonus = _weapon.magical_bonus
                        _is_ranged = _weapon.weapon_category and "ranged" in _weapon.weapon_category.value
                        if _is_ranged:
                            ability_mod = attacker_sheet.ability_scores.modifier(AbilityName.DEX)
                        elif WeaponProperty.FINESSE in _props:
                            ability_mod = max(
                                attacker_sheet.ability_scores.modifier(AbilityName.STR),
                                attacker_sheet.ability_scores.modifier(AbilityName.DEX),
                            )
                        else:
                            ability_mod = attacker_sheet.ability_scores.modifier(AbilityName.STR)
                    else:
                        ability_mod = attacker_sheet.ability_scores.modifier(AbilityName.STR)
                except Exception:
                    pass

            dmg_result = calculate_weapon_damage(
                damage_dice=atk.damage_dice,
                ability_modifier=ability_mod,
                magical_bonus=magical_bonus,
                is_critical=is_crit,
                target_damage_type=atk.damage_type,   # "slashing"/"fire"/...
                target_resistances=target_resistances,
                target_immunities=target_immunities,
                target_vulnerabilities=target_vulnerabilities,
            )
            damage_final = dmg_result.get("final_damage", 0)

        # ── 7. 应用伤害 ────────────────────────────────────
        target_hp_after = target_hp_before
        target_is_down = False
        concentration_event: dict | None = None
        import asyncio as _asyncio

        if is_hit and damage_final > 0:
            target_hp_after = max(0, target_hp_before - damage_final)
            target_is_down = target_hp_after <= 0

            if target_sheet:
                # 目标是玩家角色
                new_hp_val = target_hp_after
                new_hp = target_sheet.hit_points.model_copy(update={"current": new_hp_val})
                target_sheet = target_sheet.model_copy(update={"hit_points": new_hp})

                # 集中检定
                target_sheet, concentration_event = _conc_check(target_sheet, damage_final)

                # HP=0 → 施加 Unconscious
                if target_is_down:
                    from character.models import Condition as _Cond
                    conds = list(target_sheet.conditions)
                    if _Cond.UNCONSCIOUS not in conds:
                        conds.append(_Cond.UNCONSCIOUS)
                    target_sheet = target_sheet.model_copy(update={"conditions": conds})

                _asyncio.create_task(save_character(target_sheet))

            elif target_creature:
                # 目标是地图生物
                target_creature.hp_current = target_hp_after
                _asyncio.create_task(save_encounter_map(emap))
                manager.update_creature_hp_in_room(
                    campaign_id, target_creature.instance_id, target_hp_after
                )

        # ── 8. 攻击者消耗行动（怪物自动标记 action_used）──
        if attacker_creature and is_hit is not None:
            attacker_creature.action_used = True
            _asyncio.create_task(save_encounter_map(emap))

        # ── 8b. 法术位自动扣减（命中时）────────────────────
        spell_slot_deducted = False
        if is_hit and atk.spell_slot_level > 0 and attacker_sheet:
            lvl = atk.spell_slot_level
            slot = attacker_sheet.spell_slots.slots.get(lvl)
            if slot and slot.current > 0:
                new_slot = slot.model_copy(update={"current": slot.current - 1})
                new_slots_dict = dict(attacker_sheet.spell_slots.slots)
                new_slots_dict[lvl] = new_slot
                new_spell_slots = attacker_sheet.spell_slots.model_copy(
                    update={"slots": new_slots_dict}
                )
                attacker_sheet = attacker_sheet.model_copy(
                    update={"spell_slots": new_spell_slots}
                )
                _asyncio.create_task(save_character(attacker_sheet))
                spell_slot_deducted = True
                # 广播角色表更新
                _asyncio.create_task(
                    manager.broadcast(
                        campaign_id,
                        WSMessage(
                            type=WSMsgType.CHARACTER_UPDATE,
                            sender="server",
                            data={
                                "character_id": attacker_sheet.id,
                                "changed_fields": {
                                    "spell_slots": {
                                        str(lvl): {"current": new_slot.current, "maximum": new_slot.maximum}
                                    }
                                },
                                "full_sync": False,
                            },
                        ),
                    )
                )

        # ── 9. 构建可读摘要 ────────────────────────────────
        if is_crit:
            hit_tag = "🎯 重击！"
        elif is_crit_fail:
            hit_tag = "💨 大失手"
        elif is_hit:
            hit_tag = "✅ 命中"
        else:
            hit_tag = "❌ 未命中"

        breakdown_parts = [
            f"{attacker_name} → {target_name}",
            f"攻击骰: {hit_result.breakdown} + 加值{to_hit_bonus:+d} = {total_to_hit} vs AC {target_ac} → {hit_tag}",
        ]
        if is_hit and dmg_result:
            breakdown_parts.append(
                f"伤害: {dmg_result.get('dice_rolled', atk.damage_dice)} = "
                f"{dmg_result.get('total_raw', damage_final)}"
                + (f" (抗性→{damage_final})" if dmg_result.get('resistant') else "")
                + (f" (易伤→{damage_final})" if dmg_result.get('vulnerable') else "")
                + (f" (免疫→0)" if dmg_result.get('immune') else "")
                + f"  HP: {target_hp_before}→{target_hp_after}"
            )
        if spell_slot_deducted:
            breakdown_parts.append(f"🔮 消耗 {atk.spell_slot_level} 环法术位")

        result = AttackResultData(
            encounter_map_id=atk.encounter_map_id,
            attacker_instance_id=atk.attacker_instance_id,
            attacker_character_id=atk.attacker_character_id,
            attacker_name=attacker_name,
            target_instance_id=atk.target_instance_id,
            target_character_id=atk.target_character_id,
            target_name=target_name,
            target_ac=target_ac,
            to_hit_bonus=to_hit_bonus,
            attack_roll=raw_d20,
            total_to_hit=total_to_hit,
            is_hit=is_hit,
            is_crit=is_crit,
            is_crit_fail=is_crit_fail,
            damage_dice_rolled=dmg_result.get("dice_rolled", "") if is_hit else "",
            damage_raw=dmg_result.get("total_raw", 0) if is_hit else 0,
            damage_final=damage_final,
            damage_type=atk.damage_type,
            resistant=dmg_result.get("resistant", False) if is_hit else False,
            immune=dmg_result.get("immune", False) if is_hit else False,
            vulnerable=dmg_result.get("vulnerable", False) if is_hit else False,
            target_hp_before=target_hp_before,
            target_hp_after=target_hp_after,
            target_is_down=target_is_down,
            concentration_check=concentration_event,
            roll_breakdown="\n".join(breakdown_parts),
        )

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.ATTACK_RESULT, sender=sender, data=result.model_dump()),
        )
        return

    # ---- CREATURE_ACTION（DM 标记怪物行动/附赠动作/反应已用或重置）----
    if msg.type == WSMsgType.CREATURE_ACTION:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "标记怪物行动需要 DM 权限", msg.msg_id)
            return
        try:
            ca = CreatureActionData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"CREATURE_ACTION 格式错误: {e}", msg.msg_id)
            return

        valid_actions = {"action", "bonus_action", "reaction", "reset"}
        if ca.action not in valid_actions:
            await _ws_error(ws, f"action 必须是 {valid_actions} 之一，收到: {ca.action!r}", msg.msg_id)
            return

        try:
            from maps.storage import get_encounter_map, save_encounter_map
            emap = await get_encounter_map(ca.encounter_map_id)
            if emap is None:
                await _ws_error(ws, f"遭遇战地图不存在: {ca.encounter_map_id}", msg.msg_id)
                return

            creature = next((c for c in emap.creatures if c.instance_id == ca.instance_id), None)
            if creature is None:
                await _ws_error(ws, f"生物不存在: {ca.instance_id}", msg.msg_id)
                return

            if ca.action == "reset":
                creature.movement_used = 0
                creature.action_used = False
                creature.bonus_action_used = False
                creature.reaction_used = False
            elif ca.action == "action":
                creature.action_used = ca.used
            elif ca.action == "bonus_action":
                creature.bonus_action_used = ca.used
            elif ca.action == "reaction":
                creature.reaction_used = ca.used

            import asyncio as _asyncio
            _asyncio.create_task(save_encounter_map(emap))

            # 构造回显消息（把最新状态一并下发给前端）
            ca_reply = CreatureActionData(
                encounter_map_id=ca.encounter_map_id,
                instance_id=ca.instance_id,
                action=ca.action,
                used=ca.used,
                action_used=creature.action_used,
                bonus_action_used=creature.bonus_action_used,
                reaction_used=creature.reaction_used,
                movement_used=creature.movement_used,
            )
        except Exception as e:
            await _ws_error(ws, f"CREATURE_ACTION 处理失败: {e}", msg.msg_id)
            return

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.CREATURE_ACTION, sender=sender, data=ca_reply.model_dump()),
        )
        return

    # ---- LEGENDARY_ACTION（DM 消耗或重置传奇动作点数）----
    if msg.type == WSMsgType.LEGENDARY_ACTION:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "传奇动作操作需要 DM 权限", msg.msg_id)
            return
        try:
            la = LegendaryActionData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"LEGENDARY_ACTION 格式错误: {e}", msg.msg_id)
            return

        if la.operation not in ("use", "reset"):
            await _ws_error(ws, "operation 必须是 'use' 或 'reset'", msg.msg_id)
            return

        try:
            from maps.storage import get_encounter_map, save_encounter_map
            emap = await get_encounter_map(la.encounter_map_id)
            if emap is None:
                await _ws_error(ws, f"遭遇战地图不存在: {la.encounter_map_id}", msg.msg_id)
                return

            creature = next((c for c in emap.creatures if c.instance_id == la.instance_id), None)
            if creature is None:
                await _ws_error(ws, f"生物不存在: {la.instance_id}", msg.msg_id)
                return

            if creature.legendary_actions_max == 0:
                await _ws_error(ws, f"该生物没有传奇动作: {creature.name}", msg.msg_id)
                return

            if la.operation == "reset":
                creature.legendary_actions_used = 0
            else:  # "use"
                new_used = creature.legendary_actions_used + la.cost
                if new_used > creature.legendary_actions_max:
                    await _ws_error(
                        ws,
                        f"传奇动作点数不足（已用 {creature.legendary_actions_used}/"
                        f"{creature.legendary_actions_max}，尝试消耗 {la.cost} 点）",
                        msg.msg_id,
                    )
                    return
                creature.legendary_actions_used = new_used

            import asyncio as _asyncio
            _asyncio.create_task(save_encounter_map(emap))

            la_reply = LegendaryActionData(
                encounter_map_id=la.encounter_map_id,
                instance_id=la.instance_id,
                operation=la.operation,
                cost=la.cost,
                action_name=la.action_name,
                legendary_actions_used=creature.legendary_actions_used,
                legendary_actions_max=creature.legendary_actions_max,
            )
        except Exception as e:
            await _ws_error(ws, f"LEGENDARY_ACTION 处理失败: {e}", msg.msg_id)
            return

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.LEGENDARY_ACTION, sender=sender, data=la_reply.model_dump()),
        )
        return

    # ---- SAVING_THROW（P1 — 通用豁免检定）----
    if msg.type == WSMsgType.SAVING_THROW:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "发起豁免检定需要 DM 权限", msg.msg_id)
            return
        try:
            st_req = SavingThrowData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"SAVING_THROW 格式错误: {e}", msg.msg_id)
            return

        if not st_req.target_character_id and not st_req.target_instance_id:
            await _ws_error(ws, "必须指定目标（target_character_id 或 target_instance_id）", msg.msg_id)
            return

        try:
            from maps.storage import get_encounter_map, save_encounter_map
            from character.saving_throw import roll_saving_throw as _roll_save
            import asyncio as _asyncio

            emap = await get_encounter_map(st_req.encounter_map_id)
            if emap is None:
                await _ws_error(ws, f"遭遇战地图不存在: {st_req.encounter_map_id}", msg.msg_id)
                return

            # 解析目标
            target_name = ""
            target_hp_before = 0
            save_roll = 0; save_bonus = 0; save_total = 0; save_success = False

            if st_req.target_character_id:
                t_sheet = await get_character(st_req.target_character_id)
                if t_sheet is None:
                    await _ws_error(ws, f"目标角色不存在: {st_req.target_character_id}", msg.msg_id)
                    return
                target_name = t_sheet.name
                target_hp_before = t_sheet.hit_points.current

                save_res = _roll_save(t_sheet, st_req.ability, st_req.dc)
                save_roll = save_res["roll"]; save_bonus = save_res["bonus"]
                save_total = save_res["total"]; save_success = save_res["success"]

            else:
                t_creature = next(
                    (c for c in emap.creatures if c.instance_id == st_req.target_instance_id), None
                )
                if t_creature is None:
                    await _ws_error(ws, f"目标生物不存在: {st_req.target_instance_id}", msg.msg_id)
                    return
                target_name = t_creature.name
                target_hp_before = t_creature.hp_current

                # 推算怪物豁免加值
                save_bonus = 0
                if t_creature.monster_id:
                    try:
                        from monster.storage import get_monster as _get_monster
                        t_monster = await _get_monster(t_creature.monster_id)
                        if t_monster:
                            # 属性名 → 短键映射
                            _SAVE_KEY = {
                                "strength": "str", "str": "str",
                                "dexterity": "dex", "dex": "dex",
                                "constitution": "con", "con": "con",
                                "intelligence": "int", "int": "int",
                                "wisdom": "wis", "wis": "wis",
                                "charisma": "cha", "cha": "cha",
                            }
                            sk = _SAVE_KEY.get(st_req.ability.lower(), st_req.ability.lower()[:3])
                            if sk in t_monster.saving_throws:
                                save_bonus = t_monster.saving_throws[sk]
                            else:
                                save_bonus = t_monster.abilities.modifier(sk)
                    except Exception:
                        pass
                import random as _random
                save_roll = _random.randint(1, 20)
                save_total = save_roll + save_bonus
                save_success = save_total >= st_req.dc

            # 计算伤害
            damage_rolled = 0; damage_applied = 0
            target_hp_after = target_hp_before
            target_is_down = False

            if st_req.damage_dice:
                try:
                    dmg_res = parse_and_roll(st_req.damage_dice)
                    damage_rolled = dmg_res.total
                except DiceError:
                    damage_rolled = 0

                if save_success and st_req.half_on_success:
                    damage_applied = damage_rolled // 2
                elif not save_success:
                    damage_applied = damage_rolled
                else:
                    damage_applied = 0

                if damage_applied > 0:
                    target_hp_after = max(0, target_hp_before - damage_applied)
                    target_is_down = target_hp_after <= 0

                    if st_req.target_character_id:
                        new_hp = t_sheet.hit_points.model_copy(update={"current": target_hp_after})
                        t_sheet = t_sheet.model_copy(update={"hit_points": new_hp})
                        if target_is_down:
                            from character.models import Condition as _Cond
                            conds = list(t_sheet.conditions)
                            if _Cond.UNCONSCIOUS not in conds:
                                conds.append(_Cond.UNCONSCIOUS)
                            t_sheet = t_sheet.model_copy(update={"conditions": conds})
                        _asyncio.create_task(save_character(t_sheet))
                    else:
                        t_creature.hp_current = target_hp_after
                        _asyncio.create_task(save_encounter_map(emap))
                        manager.update_creature_hp_in_room(
                            campaign_id, t_creature.instance_id, target_hp_after
                        )

            # 构建可读摘要
            save_label = "✅ 成功" if save_success else "❌ 失败"
            parts = [
                f"{target_name} 掷 {st_req.ability.upper()[:3]} 豁免（DC {st_req.dc}）",
                f"骰子: {save_roll} + 加值{save_bonus:+d} = {save_total} → {save_label}",
            ]
            if st_req.damage_dice:
                parts.append(
                    f"伤害: {st_req.damage_dice} = {damage_rolled}"
                    + (f" (减半→{damage_applied})" if save_success and st_req.half_on_success else "")
                    + f"  HP: {target_hp_before}→{target_hp_after}"
                )
            if st_req.description:
                parts.insert(0, f"[{st_req.description}]")

            st_result = SavingThrowResultData(
                encounter_map_id=st_req.encounter_map_id,
                target_character_id=st_req.target_character_id,
                target_instance_id=st_req.target_instance_id,
                target_name=target_name,
                ability=st_req.ability,
                dc=st_req.dc,
                roll=save_roll,
                bonus=save_bonus,
                total=save_total,
                success=save_success,
                damage_rolled=damage_rolled,
                damage_applied=damage_applied,
                damage_type=st_req.damage_type,
                hp_before=target_hp_before,
                hp_after=target_hp_after,
                target_is_down=target_is_down,
                description=st_req.description,
                roll_breakdown="\n".join(parts),
            )
        except Exception as e:
            await _ws_error(ws, f"SAVING_THROW 处理失败: {e}", msg.msg_id)
            return

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.SAVING_THROW_RESULT, sender=sender, data=st_result.model_dump()),
        )
        return

    # ---- AOE_ATTACK（P1 — AoE 伤害自动分发）----
    if msg.type == WSMsgType.AOE_ATTACK:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "发起 AoE 攻击需要 DM 权限", msg.msg_id)
            return
        try:
            aoe = AoeAttackData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"AOE_ATTACK 格式错误: {e}", msg.msg_id)
            return

        if not aoe.target_instance_ids and not aoe.target_character_ids:
            await _ws_error(ws, "AOE_ATTACK 至少需要一个目标", msg.msg_id)
            return

        try:
            from maps.storage import get_encounter_map, save_encounter_map
            from character.saving_throw import roll_saving_throw as _roll_save
            import asyncio as _asyncio
            import random as _random

            emap = await get_encounter_map(aoe.encounter_map_id)
            if emap is None:
                await _ws_error(ws, f"遭遇战地图不存在: {aoe.encounter_map_id}", msg.msg_id)
                return

            # D&D 5e AoE 规则：伤害骰只投一次，所有目标共享同一个伤害值
            damage_rolled = 0
            if aoe.damage_dice:
                try:
                    dmg_result = parse_and_roll(aoe.damage_dice)
                    damage_rolled = dmg_result.total
                except DiceError:
                    damage_rolled = 0

            results_list = []
            map_needs_save = False

            # 属性名 → 短键映射（怪物用）
            _SAVE_KEY = {
                "strength": "str", "str": "str",
                "dexterity": "dex", "dex": "dex",
                "constitution": "con", "con": "con",
                "intelligence": "int", "int": "int",
                "wisdom": "wis", "wis": "wis",
                "charisma": "cha", "cha": "cha",
            }

            # ── 处理地图生物 ────────────────────────────────
            for inst_id in aoe.target_instance_ids:
                t_creature = next(
                    (c for c in emap.creatures if c.instance_id == inst_id), None
                )
                if t_creature is None:
                    continue

                # 怪物豁免加值
                save_bonus = 0
                t_resistances: list[str] = []
                t_immunities: list[str] = []
                t_vulnerabilities: list[str] = []
                if t_creature.monster_id:
                    try:
                        from monster.storage import get_monster as _get_monster
                        t_monster = await _get_monster(t_creature.monster_id)
                        if t_monster:
                            sk = _SAVE_KEY.get(aoe.ability.lower(), aoe.ability.lower()[:3])
                            save_bonus = (
                                t_monster.saving_throws[sk]
                                if sk in t_monster.saving_throws
                                else t_monster.abilities.modifier(sk)
                            )
                            t_resistances   = t_monster.damage_resistances
                            t_immunities    = t_monster.damage_immunities
                            t_vulnerabilities = t_monster.damage_vulnerabilities
                    except Exception:
                        pass

                save_roll = _random.randint(1, 20)
                save_total = save_roll + save_bonus
                save_success = save_total >= aoe.dc

                # 伤害（直接应用抗性/免疫/易伤，不重新投骰）
                if save_success and aoe.half_on_success:
                    raw_dmg = damage_rolled // 2
                elif not save_success:
                    raw_dmg = damage_rolled
                else:
                    raw_dmg = 0

                final_dmg = 0
                resistant = immune = vulnerable = False
                if raw_dmg > 0:
                    dtype = aoe.damage_type.lower()
                    immune    = dtype in [x.lower() for x in t_immunities]
                    resistant = (not immune) and dtype in [x.lower() for x in t_resistances]
                    vulnerable = (not immune) and dtype in [x.lower() for x in t_vulnerabilities]
                    final_dmg = 0 if immune else (raw_dmg // 2 if resistant else (raw_dmg * 2 if vulnerable else raw_dmg))

                hp_before = t_creature.hp_current
                hp_after = max(0, hp_before - final_dmg)
                is_down = hp_after <= 0
                t_creature.hp_current = hp_after
                map_needs_save = True
                manager.update_creature_hp_in_room(campaign_id, inst_id, hp_after)

                results_list.append({
                    "instance_id": inst_id,
                    "name": t_creature.name,
                    "is_player": False,
                    "save_roll": save_roll, "save_bonus": save_bonus,
                    "save_total": save_total, "save_success": save_success,
                    "damage_applied": final_dmg,
                    "resistant": resistant, "immune": immune, "vulnerable": vulnerable,
                    "hp_before": hp_before, "hp_after": hp_after, "is_down": is_down,
                })

            if map_needs_save:
                _asyncio.create_task(save_encounter_map(emap))

            # ── 处理玩家角色 ────────────────────────────────
            for char_id in aoe.target_character_ids:
                t_sheet = await get_character(char_id)
                if t_sheet is None:
                    continue

                save_res = _roll_save(t_sheet, aoe.ability, aoe.dc)
                save_success = save_res["success"]

                if save_success and aoe.half_on_success:
                    raw_dmg = damage_rolled // 2
                elif not save_success:
                    raw_dmg = damage_rolled
                else:
                    raw_dmg = 0

                final_dmg = raw_dmg  # 角色暂不处理伤害类型抗性（角色抗性由 DM 裁定）
                hp_before = t_sheet.hit_points.current
                hp_after = max(0, hp_before - final_dmg)
                is_down = hp_after <= 0

                new_hp = t_sheet.hit_points.model_copy(update={"current": hp_after})
                t_sheet = t_sheet.model_copy(update={"hit_points": new_hp})
                if is_down:
                    from character.models import Condition as _Cond
                    conds = list(t_sheet.conditions)
                    if _Cond.UNCONSCIOUS not in conds:
                        conds.append(_Cond.UNCONSCIOUS)
                    t_sheet = t_sheet.model_copy(update={"conditions": conds})
                _asyncio.create_task(save_character(t_sheet))

                results_list.append({
                    "character_id": char_id,
                    "name": t_sheet.name,
                    "is_player": True,
                    "save_roll": save_res["roll"], "save_bonus": save_res["bonus"],
                    "save_total": save_res["total"], "save_success": save_success,
                    "damage_applied": final_dmg,
                    "resistant": False, "immune": False, "vulnerable": False,
                    "hp_before": hp_before, "hp_after": hp_after, "is_down": is_down,
                })

            total_successes = sum(1 for r in results_list if r["save_success"])
            total_failures  = len(results_list) - total_successes
            total_dmg = sum(r["damage_applied"] for r in results_list)

            aoe_result = AoeAttackResultData(
                encounter_map_id=aoe.encounter_map_id,
                description=aoe.description,
                ability=aoe.ability,
                dc=aoe.dc,
                damage_dice=aoe.damage_dice,
                damage_rolled=damage_rolled,
                damage_type=aoe.damage_type,
                results=results_list,
                total_targets=len(results_list),
                successes=total_successes,
                failures=total_failures,
                total_damage_dealt=total_dmg,
            )
        except Exception as e:
            await _ws_error(ws, f"AOE_ATTACK 处理失败: {e}", msg.msg_id)
            return

        await manager.broadcast(
            campaign_id,
            WSMessage(type=WSMsgType.AOE_ATTACK_RESULT, sender=sender, data=aoe_result.model_dump()),
        )
        return

    # ---- ROLL_INITIATIVE（P1 — 一键投先攻）----
    if msg.type == WSMsgType.ROLL_INITIATIVE:
        if not manager.is_dm(ws, campaign_id):
            await _ws_error(ws, "投先攻需要 DM 权限", msg.msg_id)
            return
        try:
            ri = RollInitiativeData.model_validate(msg.data)
        except Exception as e:
            await _ws_error(ws, f"ROLL_INITIATIVE 格式错误: {e}", msg.msg_id)
            return

        try:
            from campaign.api import _do_roll_initiative
            import asyncio as _asyncio

            result = await _do_roll_initiative(ri.encounter_map_id, ri.reroll_players)
            if "error" in result:
                await _ws_error(ws, result["error"], msg.msg_id)
                return

            initiative_order = result["initiative_order"]

            # 构建 INITIATIVE_UPDATE 消息并更新房间状态
            entries = [
                InitiativeEntry(
                    id=entry["instance_id"],
                    name=entry["name"],
                    initiative=entry["initiative"],
                    is_player=entry["is_player"],
                    character_id=entry.get("character_id"),
                    hp_current=entry.get("hp_current"),
                    hp_max=entry.get("hp_max"),
                )
                for entry in initiative_order
            ]
            init_update = InitiativeUpdateData(
                entries=entries,
                current_turn=0,
                round_number=1,
            )
            manager.update_initiative(campaign_id, init_update, actor_id=sender)

        except Exception as e:
            await _ws_error(ws, f"ROLL_INITIATIVE 处理失败: {e}", msg.msg_id)
            return

        await manager.broadcast(
            campaign_id,
            WSMessage(
                type=WSMsgType.INITIATIVE_UPDATE,
                sender=sender,
                data=init_update.model_dump(),
            ),
        )
        return

    # ---- 未知类型 ----
    await _ws_error(ws, f"未知消息类型: {msg.type!r}", msg.msg_id)


@app.websocket("/ws/{campaign_id}")
async def websocket_endpoint(
    ws: WebSocket,
    campaign_id: str,
    owner_id: str = Query(..., description="玩家 ID，格式: Nickname#1234"),
    role: str = Query("player", description="角色: player | dm"),
    character_id: str | None = Query(None, description="本次游戏使用的角色 ID"),
    display_name: str = Query("", description="显示昵称（可选）"),
):
    """
    WebSocket 联机入口。

    连接方式:
        ws://host/ws/{campaign_id}?owner_id=Alice%231234&role=player
        ws://host/ws/{campaign_id}?owner_id=DM%230000&role=dm

    连接成功后服务器立即推送一条 sync 消息，包含房间当前状态和成员列表。
    """
    member = MemberInfo(
        owner_id=owner_id,
        role=role,
        character_id=character_id,
        display_name=display_name or owner_id.split("#")[0],
    )

    await manager.connect(ws, campaign_id, member)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = WSMessage.decode(raw)
            except Exception:
                await _ws_error(ws, "无效的 JSON 消息格式")
                continue
            await _handle_message(ws, campaign_id, msg, member)

    except WebSocketDisconnect:
        left = manager.disconnect(ws, campaign_id)
        if left is not None:
            await manager.broadcast(
                campaign_id,
                WSMessage(
                    type=WSMsgType.LEAVE,
                    sender="server",
                    data=left.model_dump(),
                ),
            )


# ========== 兼容路由（对齐 sync_engine.py 的端点约定，Unity 客户端迁移期间保留）==========

@app.websocket("/ws/session/{client_id}")
async def websocket_session_compat(
    ws: WebSocket,
    client_id: str,
    role: str = Query("player", description="player | dm"),
    room_id: str = Query("ROOM-001", description="房间 ID，对应 campaign_id"),
    character_id: str | None = Query(None),
    display_name: str = Query(""),
):
    """
    兼容 sync_engine.py 的旧端点。
    Unity 客户端可沿用 /ws/session/{client_id} 连接，
    内部转发到完整的 /ws/{campaign_id} 逻辑。

    等价于:
        /ws/{room_id}?owner_id={client_id}&role={role}
    """
    member = MemberInfo(
        owner_id=client_id,
        role=role,
        character_id=character_id,
        display_name=display_name or client_id.split("#")[0],
    )
    await manager.connect(ws, room_id, member)
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = WSMessage.decode(raw)
            except Exception:
                # 兼容 sync_engine.py 的简单格式 {"type":..., "content":..., "sender":...}
                import json
                try:
                    raw_dict = json.loads(raw)
                    msg = WSMessage(
                        type=raw_dict.get("type", "chat"),
                        sender=raw_dict.get("sender", client_id),
                        data={"text": raw_dict.get("content", raw_dict.get("text", ""))},
                    )
                except Exception:
                    await _ws_error(ws, "无效的消息格式")
                    continue
            await _handle_message(ws, room_id, msg, member)
    except WebSocketDisconnect:
        left = manager.disconnect(ws, room_id)
        if left is not None:
            await manager.broadcast(
                room_id,
                WSMessage(type=WSMsgType.LEAVE, sender="server", data=left.model_dump()),
            )


# ========== 启动入口 ==========
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)