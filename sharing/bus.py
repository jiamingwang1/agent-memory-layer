"""
SharedMemoryBus — 多Agent记忆共享总线

负责：
- 记忆发布/订阅（pub/sub）
- 自动范围分类（global/team/private）
- 冲突检测与解决
"""

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


SCOPE_GLOBAL = "global"
SCOPE_GLOBAL_ALERT = "global:alert"
SCOPE_PRIVATE = "private"

TEAM_TECH = "team:tech"
TEAM_CONTENT = "team:content"

ROLE_TO_TEAM = {
    "cto": TEAM_TECH,
    "fullstack": TEAM_TECH,
    "devops": TEAM_TECH,
    "creative": TEAM_CONTENT,
    "content": TEAM_CONTENT,
    "ceo": None,
}

AUTHORITY_MAP = {
    ("cto", "tech"): 0.9,
    ("cto", "content"): 0.3,
    ("creative", "content"): 0.9,
    ("creative", "tech"): 0.4,
    ("fullstack", "tech"): 0.8,
    ("devops", "tech"): 0.7,
    ("ceo", "tech"): 0.7,
    ("ceo", "content"): 0.7,
}


@dataclass
class SharedMemoryItem:
    id: str
    source_agent: str
    scope: str
    layer: str                # instinct/knowledge/episodic/relational/meta
    content_type: str         # fact/episode/alert/decision/insight
    title: str
    body: str
    metadata: dict = field(default_factory=dict)
    timestamp: str = ""
    resolved: bool = False
    conflict_with: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class ConflictResolver:
    """基于时间+来源权威度的冲突解决"""

    def check_conflict(self, existing: SharedMemoryItem,
                       incoming: SharedMemoryItem) -> bool:
        if existing.layer != incoming.layer:
            return False
        if existing.content_type != incoming.content_type:
            return False
        if existing.title == incoming.title and existing.body != incoming.body:
            return True
        return False

    def resolve(self, existing: SharedMemoryItem,
                incoming: SharedMemoryItem,
                existing_role: str = "unknown",
                incoming_role: str = "unknown") -> Optional[SharedMemoryItem]:
        domain = self._infer_domain(incoming)
        inc_auth = AUTHORITY_MAP.get((incoming_role, domain), 0.5)
        ext_auth = AUTHORITY_MAP.get((existing_role, domain), 0.5)

        if inc_auth > ext_auth:
            return incoming
        if ext_auth > inc_auth:
            return existing
        inc_ts = datetime.fromisoformat(incoming.timestamp)
        ext_ts = datetime.fromisoformat(existing.timestamp)
        return incoming if inc_ts >= ext_ts else existing

    def _infer_domain(self, item: SharedMemoryItem) -> str:
        tech_kw = ["api", "code", "deploy", "server", "bug", "script", "docker"]
        content_kw = ["brand", "design", "copy", "marketing", "content", "video"]
        text = (item.title + " " + item.body).lower()
        tech_score = sum(1 for kw in tech_kw if kw in text)
        content_score = sum(1 for kw in content_kw if kw in text)
        if tech_score > content_score:
            return "tech"
        if content_score > tech_score:
            return "content"
        return "general"


class SharedMemoryBus:
    """记忆共享总线 — 中央协调器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.resolver = ConflictResolver()
        self._subscribers: dict[str, list[str]] = {}
        self._pending_events: list[SharedMemoryItem] = []
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS shared_memories (
                id TEXT PRIMARY KEY,
                source_agent TEXT NOT NULL,
                scope TEXT NOT NULL,
                layer TEXT NOT NULL,
                content_type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                timestamp TEXT NOT NULL,
                resolved INTEGER DEFAULT 0,
                conflict_with TEXT DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_scope
            ON shared_memories(scope)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_ts
            ON shared_memories(timestamp DESC)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_shared_layer
            ON shared_memories(layer)
        """)
        conn.commit()
        conn.close()

    def publish(self, item: SharedMemoryItem) -> SharedMemoryItem:
        if item.scope == SCOPE_PRIVATE:
            return item

        conflicts = self._find_conflicts(item)
        for existing in conflicts:
            winner = self.resolver.resolve(existing, item)
            if winner.id == existing.id:
                item.resolved = True
                item.conflict_with = existing.id
            else:
                self._mark_resolved(existing.id, item.id)

        self._store(item)
        self._pending_events.append(item)
        return item

    def pull(self, agent_id: str, agent_scopes: list[str],
             query: str = "", limit: int = 20,
             layer: str = "", content_type: str = "") -> list[SharedMemoryItem]:
        conn = sqlite3.connect(self.db_path)
        conditions = ["resolved = 0"]
        params: list = []

        if agent_scopes:
            placeholders = ",".join("?" * len(agent_scopes))
            conditions.append(f"scope IN ({placeholders})")
            params.extend(agent_scopes)

        if layer:
            conditions.append("layer = ?")
            params.append(layer)
        if content_type:
            conditions.append("content_type = ?")
            params.append(content_type)
        if query:
            conditions.append("(title LIKE ? OR body LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        where = " AND ".join(conditions)
        rows = conn.execute(
            f"SELECT * FROM shared_memories WHERE {where} "
            f"ORDER BY timestamp DESC LIMIT ?",
            params + [limit]
        ).fetchall()
        conn.close()
        return [self._row_to_item(r) for r in rows]

    def feed(self, limit: int = 50, since: str = "") -> list[SharedMemoryItem]:
        conn = sqlite3.connect(self.db_path)
        if since:
            rows = conn.execute(
                "SELECT * FROM shared_memories WHERE timestamp > ? "
                "ORDER BY timestamp DESC LIMIT ?",
                (since, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM shared_memories ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        conn.close()
        return [self._row_to_item(r) for r in rows]

    def stats(self) -> dict:
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM shared_memories").fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM shared_memories WHERE resolved = 0"
        ).fetchone()[0]
        conflicts = conn.execute(
            "SELECT COUNT(*) FROM shared_memories WHERE conflict_with != ''"
        ).fetchone()[0]
        by_scope = {}
        for row in conn.execute(
            "SELECT scope, COUNT(*) FROM shared_memories GROUP BY scope"
        ):
            by_scope[row[0]] = row[1]
        by_agent = {}
        for row in conn.execute(
            "SELECT source_agent, COUNT(*) FROM shared_memories GROUP BY source_agent"
        ):
            by_agent[row[0]] = row[1]
        conn.close()
        return {
            "total": total,
            "active": active,
            "conflicts": conflicts,
            "by_scope": by_scope,
            "by_agent": by_agent,
        }

    def drain_events(self) -> list[SharedMemoryItem]:
        events = self._pending_events[:]
        self._pending_events.clear()
        return events

    @staticmethod
    def auto_classify_scope(layer: str, content_type: str,
                            importance: float = 0.5,
                            agent_role: str = "unknown",
                            has_urgent_signal: bool = False) -> str:
        if has_urgent_signal:
            return SCOPE_GLOBAL_ALERT

        if layer == "knowledge":
            if content_type in ("fact", "decision", "config"):
                return SCOPE_GLOBAL
            return SCOPE_PRIVATE

        if layer == "episodic":
            if importance > 0.7:
                return SCOPE_GLOBAL
            if importance > 0.4:
                team = ROLE_TO_TEAM.get(agent_role)
                return team if team else SCOPE_GLOBAL
            return SCOPE_PRIVATE

        if layer in ("relational", "meta", "instinct"):
            return SCOPE_PRIVATE

        return SCOPE_PRIVATE

    def _find_conflicts(self, item: SharedMemoryItem) -> list[SharedMemoryItem]:
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT * FROM shared_memories WHERE layer = ? AND content_type = ? "
            "AND title = ? AND resolved = 0 AND id != ?",
            (item.layer, item.content_type, item.title, item.id)
        ).fetchall()
        conn.close()
        return [self._row_to_item(r) for r in rows]

    def _mark_resolved(self, item_id: str, conflict_with: str):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE shared_memories SET resolved = 1, conflict_with = ? WHERE id = ?",
            (conflict_with, item_id)
        )
        conn.commit()
        conn.close()

    def _store(self, item: SharedMemoryItem):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO shared_memories
            (id, source_agent, scope, layer, content_type, title, body,
             metadata, timestamp, resolved, conflict_with)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item.id, item.source_agent, item.scope,
            item.layer, item.content_type, item.title, item.body,
            json.dumps(item.metadata, ensure_ascii=False),
            item.timestamp, int(item.resolved), item.conflict_with,
        ))
        conn.commit()
        conn.close()

    def _row_to_item(self, row) -> SharedMemoryItem:
        return SharedMemoryItem(
            id=row[0], source_agent=row[1], scope=row[2],
            layer=row[3], content_type=row[4], title=row[5],
            body=row[6], metadata=json.loads(row[7]),
            timestamp=row[8], resolved=bool(row[9]),
            conflict_with=row[10],
        )
