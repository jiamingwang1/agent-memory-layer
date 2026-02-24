"""
Memory Nexus API Server

FastAPI server exposing the five-layer memory system + multi-agent sharing.
Serves REST endpoints and WebSocket real-time hub.
"""

import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from memory_system import MemorySystem
from layers import (
    InstinctMemory, KnowledgeMemory, Fact,
    EpisodicMemory, Episode,
    RelationalMemory, MetaMemory,
)
from sharing import SharedMemoryBus, SharedMemoryItem, AgentRegistry, AgentInfo

DATA_DIR = os.environ.get(
    "MEMORY_DATA_DIR",
    os.path.expanduser("~/.openclaw/workspace/memory-data"),
)
SHARED_DIR = os.path.join(DATA_DIR, "shared")
EMBEDDING_CONFIG = {
    "api_base": os.environ.get("EMBEDDING_API_BASE", "https://ai.t8star.cn/v1"),
    "api_key": os.environ.get("EMBEDDING_API_KEY", ""),
    "model": "text-embedding-3-small",
}

ws_clients: list[WebSocket] = []


def _init_globals():
    global ms, bus, registry
    if ms is not None:
        return
    os.makedirs(SHARED_DIR, exist_ok=True)
    ms = MemorySystem(DATA_DIR, embedding_config=EMBEDDING_CONFIG)
    bus = SharedMemoryBus(os.path.join(SHARED_DIR, "shared.db"))
    registry = AgentRegistry(os.path.join(SHARED_DIR, "registry.db"))
    _seed_default_agents()


ms: Optional[MemorySystem] = None
bus: Optional[SharedMemoryBus] = None
registry: Optional[AgentRegistry] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_globals()
    yield


app = FastAPI(title="Memory Nexus API", version="0.1.0", lifespan=lifespan)

@app.middleware("http")
async def ensure_init(request, call_next):
    _init_globals()
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _seed_default_agents():
    if registry.list_all():
        return
    defaults = [
        AgentInfo(id="xiaozhu", name="小助", role="ceo", team="", capabilities=["调度", "决策", "记忆管理"]),
        AgentInfo(id="arnold", name="阿诺", role="cto", team="tech", capabilities=["研究", "开发", "审计"]),
        AgentInfo(id="xiaom", name="小M", role="creative", team="content", capabilities=["设计", "文案", "策略"]),
        AgentInfo(id="yuanzheng", name="远征", role="devops", team="tech", capabilities=["运维", "部署", "脚本"]),
        AgentInfo(id="leiting", name="雷霆", role="fullstack", team="tech", capabilities=["全栈", "交互", "推广"]),
    ]
    for a in defaults:
        registry.register(a)


async def broadcast(event: dict):
    dead = []
    data = json.dumps(event, ensure_ascii=False)
    for ws in ws_clients:
        try:
            await ws.send_text(data)
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


# ─── Pydantic models ───

class PublishRequest(BaseModel):
    source_agent: str
    layer: str
    content_type: str
    title: str
    body: str
    scope: str = ""
    metadata: dict = {}

class AgentStatusUpdate(BaseModel):
    status: str
    current_task: str = ""


# ─── WebSocket ───

@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in ws_clients:
            ws_clients.remove(websocket)


# ─── Agents ───

@app.get("/api/agents")
def list_agents():
    return registry.get_team_status()

@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: str):
    agent = registry.get(agent_id)
    if not agent:
        return {"error": "not found"}
    from dataclasses import asdict
    return asdict(agent)

@app.put("/api/agents/{agent_id}/status")
async def update_agent_status(agent_id: str, body: AgentStatusUpdate):
    registry.update_status(agent_id, body.status, body.current_task)
    await broadcast({"type": "agent_status", "agent_id": agent_id, "status": body.status})
    return {"ok": True}

@app.post("/api/agents/{agent_id}/heartbeat")
async def agent_heartbeat(agent_id: str):
    registry.heartbeat(agent_id)
    return {"ok": True}


# ─── Memories by layer ───

@app.get("/api/memories/knowledge")
def get_knowledge(
    subject: str = "", category: str = "",
    limit: int = Query(50, le=200),
):
    facts = ms.knowledge.query(subject=subject or None, category=category or None, limit=limit)
    return [
        {
            "id": f.id, "category": f.category,
            "subject": f.subject, "predicate": f.predicate,
            "value": f.value, "confidence": f.confidence,
            "source": f.source, "created": f.created,
            "updated": f.updated, "access_count": f.access_count,
        }
        for f in facts
    ]

@app.get("/api/memories/episodic")
def get_episodes(
    days: int = 30, limit: int = Query(50, le=200),
    min_importance: float = 0.0,
):
    episodes = ms.episodic.recent(days=days, limit=limit)
    if min_importance > 0:
        episodes = [e for e in episodes if e.importance_score >= min_importance]
    return [_episode_dict(e) for e in episodes]

@app.get("/api/memories/instinct")
def get_instinct():
    p = ms.instinct.profile
    from dataclasses import asdict
    return asdict(p)

@app.get("/api/memories/meta")
def get_meta():
    a = ms.meta.assessments[-1] if ms.meta.assessments else ms.meta.self_assess()
    return {
        "session_count": ms.meta.session_count,
        "compression_count": ms.meta.compression_count,
        "last_full_check": ms.meta.last_full_check,
        "drift_signals": [vars(d) for d in ms.meta.drift_signals[-20:]],
        "assessment": vars(a),
    }

@app.get("/api/memories/relational")
def get_relationships():
    import sqlite3
    conn = sqlite3.connect(ms.relational.db_path)
    rows = conn.execute("SELECT user_id, state_json FROM relationships").fetchall()
    conn.close()
    results = []
    for uid, state_json in rows:
        state = json.loads(state_json)
        results.append({
            "user_id": uid,
            "temperature": state.get("temperature", 0),
            "trust_level": state.get("trust_level", 1),
            "total_interactions": state.get("total_interactions", 0),
            "first_interaction": state.get("first_interaction", ""),
            "last_interaction": state.get("last_interaction", ""),
            "style": state.get("style", {}),
            "emotional_model": state.get("emotional_model", {}),
            "shared_contexts": state.get("shared_contexts", []),
            "temperature_history": state.get("temperature_history", []),
        })
    return results

@app.get("/api/relationships/{person_id}/history")
def get_relationship_history(person_id: str):
    state = ms.relational.get(person_id)
    from dataclasses import asdict
    return {
        "user_id": state.user_id,
        "temperature": state.temperature,
        "temperature_history": state.temperature_history,
        "style": asdict(state.style),
        "emotional_model": asdict(state.emotional_model),
        "shared_contexts": state.shared_contexts,
        "trust_level": state.trust_level,
        "total_interactions": state.total_interactions,
    }


# ─── Search ───

@app.get("/api/memories/search")
def search_memories(q: str = "", limit: int = 20):
    results = []
    if not q:
        return results

    facts = ms.knowledge.query(subject=q, limit=limit // 2)
    for f in facts:
        results.append({
            "layer": "knowledge", "id": f.id,
            "title": f"{f.subject} → {f.predicate}",
            "body": f.value, "score": f.confidence,
            "timestamp": f.updated,
        })

    episodes = ms.episodic.recent(days=365, limit=100)
    q_lower = q.lower()
    for e in episodes:
        if q_lower in e.summary.lower() or any(q_lower in t.lower() for t in e.tags):
            results.append({
                "layer": "episodic", "id": e.id,
                "title": e.summary[:80],
                "body": e.summary,
                "score": e.importance_score,
                "timestamp": e.timestamp,
            })

    shared = bus.pull("__search__", ["global", "global:alert", "team:tech", "team:content"],
                      query=q, limit=limit // 2)
    for s in shared:
        results.append({
            "layer": "shared", "id": s.id,
            "title": s.title,
            "body": s.body,
            "score": 0.5,
            "timestamp": s.timestamp,
        })

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:limit]


# ─── Timeline ───

@app.get("/api/episodes/timeline")
def get_timeline(days: int = 30, limit: int = 100):
    episodes = ms.episodic.recent(days=days, limit=limit)
    return [_episode_dict(e) for e in episodes]


# ─── Knowledge graph ───

@app.get("/api/knowledge/graph")
def get_knowledge_graph(limit: int = 100):
    facts = ms.knowledge.query(limit=limit)
    nodes = {}
    edges = []
    for f in facts:
        if f.subject not in nodes:
            nodes[f.subject] = {
                "id": f.subject, "label": f.subject,
                "type": "entity", "group": f.category,
            }
        val_id = f"{f.subject}_{f.predicate}"
        if val_id not in nodes:
            nodes[val_id] = {
                "id": val_id, "label": f.value[:40],
                "type": "value", "group": f.category,
            }
        edges.append({
            "source": f.subject, "target": val_id,
            "label": f.predicate, "weight": f.confidence,
        })
    return {"nodes": list(nodes.values()), "edges": edges}


# ─── Shared memory ───

@app.get("/api/shared/feed")
def shared_feed(limit: int = 50, since: str = ""):
    items = bus.feed(limit=limit, since=since)
    return [_shared_dict(i) for i in items]

@app.post("/api/shared/publish")
async def publish_shared(req: PublishRequest):
    scope = req.scope
    if not scope:
        agent = registry.get(req.source_agent)
        role = agent.role if agent else "unknown"
        scope = SharedMemoryBus.auto_classify_scope(
            req.layer, req.content_type, agent_role=role,
        )
    item = SharedMemoryItem(
        id=f"sm_{uuid.uuid4().hex[:12]}",
        source_agent=req.source_agent,
        scope=scope,
        layer=req.layer,
        content_type=req.content_type,
        title=req.title,
        body=req.body,
        metadata=req.metadata,
    )
    result = bus.publish(item)
    await broadcast({"type": "shared_memory", "item": _shared_dict(result)})
    return _shared_dict(result)


# ─── Stats ───

@app.get("/api/stats")
def get_stats():
    shared_stats = bus.stats()
    return {
        "knowledge_count": ms.knowledge.count(),
        "episodic_count": ms.episodic.count(),
        "session_count": ms.meta.session_count,
        "compression_count": ms.meta.compression_count,
        "agents": registry.get_team_status(),
        "shared": shared_stats,
    }


# ─── Health ───

@app.get("/api/health")
def get_health():
    report = ms.health_check()
    a = ms.meta.assessments[-1] if ms.meta.assessments else ms.meta.self_assess()
    return {
        "report_text": report,
        "assessment": {
            "personality_consistency": a.personality_consistency,
            "memory_health": a.memory_health,
            "task_reliability": a.task_reliability,
            "emotional_stability": a.emotional_stability,
            "self_drive_score": a.self_drive_score,
        },
        "drift_signals": [
            {
                "timestamp": d.timestamp,
                "dimension": d.dimension,
                "expected": d.expected,
                "actual": d.actual,
                "severity": d.severity,
                "resolved": d.resolved,
            }
            for d in ms.meta.drift_signals[-20:]
        ],
        "needs_recalibration": ms.meta.needs_recalibration(),
        "layers": {
            "instinct": {"version": ms.instinct.profile.version},
            "knowledge": {"count": ms.knowledge.count()},
            "episodic": {"count": ms.episodic.count()},
            "relational": {"status": "active"},
            "meta": {
                "sessions": ms.meta.session_count,
                "compressions": ms.meta.compression_count,
            },
        },
    }


@app.get("/api/sleep/report")
def sleep_report():
    return {
        "last_run": "N/A",
        "message": "Sleep consolidation has not been run yet. Use CLI: python cli.py sleep",
    }


# ─── Helpers ───

def _episode_dict(e: Episode) -> dict:
    return {
        "id": e.id, "timestamp": e.timestamp,
        "summary": e.summary,
        "emotional_valence": e.emotional_valence,
        "emotional_arousal": e.emotional_arousal,
        "importance_score": e.importance_score,
        "participants": e.participants,
        "tags": e.tags,
        "key_quotes": e.key_quotes,
        "access_count": e.access_count,
        "emotional_weight": e.emotional_weight,
        "age_days": round(e.age_days, 1),
    }

def _shared_dict(s: SharedMemoryItem) -> dict:
    return {
        "id": s.id, "source_agent": s.source_agent,
        "scope": s.scope, "layer": s.layer,
        "content_type": s.content_type,
        "title": s.title, "body": s.body,
        "metadata": s.metadata, "timestamp": s.timestamp,
        "resolved": s.resolved, "conflict_with": s.conflict_with,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8900)
