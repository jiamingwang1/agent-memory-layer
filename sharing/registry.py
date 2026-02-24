"""
Agent Registry — Agent注册/状态/权限管理

管理所有Agent的元数据、在线状态、能力和权限。
CEO可以通过聚合视图了解全员状态。
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

from .bus import SCOPE_GLOBAL, SCOPE_GLOBAL_ALERT, TEAM_TECH, TEAM_CONTENT, SCOPE_PRIVATE


@dataclass
class AgentInfo:
    id: str
    name: str
    role: str                     # ceo/cto/creative/fullstack/devops
    team: str = ""                # tech/content
    capabilities: list[str] = field(default_factory=list)
    status: str = "offline"       # online/offline/busy
    last_seen: str = ""
    memory_stats: dict = field(default_factory=dict)
    current_task: str = ""
    reliability_score: float = 0.5
    registered_at: str = ""

    def visible_scopes(self) -> list[str]:
        scopes = [SCOPE_GLOBAL, SCOPE_GLOBAL_ALERT]
        if self.role == "ceo":
            scopes.extend([TEAM_TECH, TEAM_CONTENT])
        elif self.team == "tech":
            scopes.append(TEAM_TECH)
        elif self.team == "content":
            scopes.append(TEAM_CONTENT)
        return scopes


class AgentRegistry:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

    def register(self, agent: AgentInfo) -> AgentInfo:
        now = datetime.now(timezone.utc).isoformat()
        if not agent.registered_at:
            agent.registered_at = now
        agent.last_seen = now
        self._save(agent)
        return agent

    def unregister(self, agent_id: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
        conn.commit()
        conn.close()

    def get(self, agent_id: str) -> Optional[AgentInfo]:
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT data_json FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return self._deserialize(row[0])

    def list_all(self) -> list[AgentInfo]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("SELECT data_json FROM agents ORDER BY id").fetchall()
        conn.close()
        return [self._deserialize(r[0]) for r in rows]

    def update_status(self, agent_id: str, status: str,
                      current_task: str = ""):
        agent = self.get(agent_id)
        if not agent:
            return
        agent.status = status
        agent.last_seen = datetime.now(timezone.utc).isoformat()
        if current_task:
            agent.current_task = current_task
        self._save(agent)

    def update_memory_stats(self, agent_id: str, stats: dict):
        agent = self.get(agent_id)
        if not agent:
            return
        agent.memory_stats = stats
        self._save(agent)

    def heartbeat(self, agent_id: str):
        agent = self.get(agent_id)
        if agent:
            agent.last_seen = datetime.now(timezone.utc).isoformat()
            agent.status = "online"
            self._save(agent)

    def get_team_status(self) -> dict:
        agents = self.list_all()
        return {
            "total": len(agents),
            "online": sum(1 for a in agents if a.status == "online"),
            "agents": [
                {
                    "id": a.id,
                    "name": a.name,
                    "role": a.role,
                    "team": a.team,
                    "capabilities": a.capabilities,
                    "status": a.status,
                    "last_seen": a.last_seen,
                    "current_task": a.current_task,
                    "reliability": a.reliability_score,
                    "memory_stats": a.memory_stats,
                }
                for a in agents
            ],
        }

    def _save(self, agent: AgentInfo):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO agents (id, data_json, updated_at) VALUES (?, ?, ?)",
            (agent.id, self._serialize(agent),
             datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        conn.close()

    def _serialize(self, agent: AgentInfo) -> str:
        return json.dumps(asdict(agent), ensure_ascii=False)

    def _deserialize(self, json_str: str) -> AgentInfo:
        d = json.loads(json_str)
        return AgentInfo(**d)
