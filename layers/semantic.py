"""
知识层 (Semantic Layer) — 第二层记忆

对应人脑：颞叶 + 海马体长期存储区
存储：用户显式偏好、隐式推断、习得的规律、事实性知识
"""

import json
import sqlite3
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class ExplicitFact:
    """用户明确说出的事实"""
    key: str            # 分类:具体项，如 "偏好:称呼"
    value: str          # "叫他aa，不要叫宝贝"
    source: str = ""    # 来源（哪次对话提到的）
    confidence: float = 1.0
    first_seen: str = ""
    last_confirmed: str = ""
    access_count: int = 0


@dataclass
class ImplicitFact:
    """从行为推断的知识"""
    id: str
    fact: str           # "用户可能是夜猫子"
    evidence: list[str] = field(default_factory=list)  # 推断依据
    confidence: float = 0.5  # 0-1，随验证增减
    created: str = ""
    last_accessed: str = ""
    access_count: int = 0


class SemanticMemory:
    """知识层 — KV显式 + 向量隐式 混合存储"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explicit_facts (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                source TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                first_seen TEXT NOT NULL,
                last_confirmed TEXT NOT NULL,
                access_count INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS implicit_facts (
                id TEXT PRIMARY KEY,
                fact TEXT NOT NULL,
                evidence TEXT DEFAULT '[]',
                confidence REAL DEFAULT 0.5,
                created TEXT NOT NULL,
                last_accessed TEXT DEFAULT '',
                access_count INTEGER DEFAULT 0,
                archived INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
    
    # === 显式事实 ===
    
    def add_explicit(self, key: str, value: str, source: str = ""):
        """添加/更新用户明确说出的事实"""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        existing = conn.execute(
            "SELECT first_seen FROM explicit_facts WHERE key = ?", (key,)
        ).fetchone()
        
        if existing:
            conn.execute("""
                UPDATE explicit_facts 
                SET value = ?, source = ?, last_confirmed = ?, 
                    access_count = access_count + 1
                WHERE key = ?
            """, (value, source, now, key))
        else:
            conn.execute("""
                INSERT INTO explicit_facts 
                (key, value, source, confidence, first_seen, last_confirmed)
                VALUES (?, ?, ?, 1.0, ?, ?)
            """, (key, value, source, now, now))
        
        conn.commit()
        conn.close()
    
    def get_explicit(self, key: str) -> Optional[str]:
        """获取一个显式事实"""
        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT value FROM explicit_facts WHERE key = ?", (key,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE explicit_facts SET access_count = access_count + 1 WHERE key = ?",
                (key,)
            )
            conn.commit()
        conn.close()
        return row[0] if row else None
    
    def search_explicit(self, keyword: str, limit: int = 10) -> list[ExplicitFact]:
        """搜索显式事实"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT key, value, source, confidence, first_seen, last_confirmed, access_count
            FROM explicit_facts 
            WHERE key LIKE ? OR value LIKE ?
            ORDER BY access_count DESC
            LIMIT ?
        """, (f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        conn.close()
        return [ExplicitFact(
            key=r[0], value=r[1], source=r[2], confidence=r[3],
            first_seen=r[4], last_confirmed=r[5], access_count=r[6]
        ) for r in rows]
    
    def all_explicit(self, limit: int = 100) -> list[ExplicitFact]:
        """获取所有显式事实"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT key, value, source, confidence, first_seen, last_confirmed, access_count
            FROM explicit_facts ORDER BY access_count DESC LIMIT ?
        """, (limit,)).fetchall()
        conn.close()
        return [ExplicitFact(
            key=r[0], value=r[1], source=r[2], confidence=r[3],
            first_seen=r[4], last_confirmed=r[5], access_count=r[6]
        ) for r in rows]
    
    # === 隐式推断 ===
    
    def add_implicit(self, fact_id: str, fact: str, evidence: list[str], 
                     confidence: float = 0.5):
        """添加推断的知识"""
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            INSERT OR REPLACE INTO implicit_facts 
            (id, fact, evidence, confidence, created, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fact_id, fact, json.dumps(evidence, ensure_ascii=False), 
              confidence, now, now))
        conn.commit()
        conn.close()
    
    def get_implicit(self, min_confidence: float = 0.5, 
                     limit: int = 20) -> list[ImplicitFact]:
        """获取高置信度的隐式知识"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT id, fact, evidence, confidence, created, last_accessed, access_count
            FROM implicit_facts 
            WHERE confidence >= ? AND archived = 0
            ORDER BY confidence DESC
            LIMIT ?
        """, (min_confidence, limit)).fetchall()
        conn.close()
        return [ImplicitFact(
            id=r[0], fact=r[1], evidence=json.loads(r[2]), 
            confidence=r[3], created=r[4], last_accessed=r[5], access_count=r[6]
        ) for r in rows]
    
    def decay_implicit(self, rate: float = 0.01):
        """隐式知识衰减 — 长期未验证的降低置信度"""
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute("""
            SELECT id, confidence, last_accessed, created 
            FROM implicit_facts WHERE archived = 0
        """).fetchall()
        
        now = datetime.now(timezone.utc)
        for row in rows:
            fact_id, conf, last_acc, created = row
            ref_time = last_acc if last_acc else created
            try:
                days = (now - datetime.fromisoformat(ref_time)).total_seconds() / 86400
            except:
                days = 0
            
            if days > 14:  # 两周未访问开始衰减
                new_conf = conf * (1 - rate) ** (days - 14)
                new_conf = max(0.1, new_conf)  # 最低不低于0.1
                if new_conf < 0.2:
                    # 太低了就归档
                    conn.execute(
                        "UPDATE implicit_facts SET archived = 1 WHERE id = ?",
                        (fact_id,)
                    )
                else:
                    conn.execute(
                        "UPDATE implicit_facts SET confidence = ? WHERE id = ?",
                        (new_conf, fact_id)
                    )
        
        conn.commit()
        conn.close()
    
    # === 格式化输出 ===
    
    def format_for_context(self, keyword: str = "", limit: int = 20) -> str:
        """格式化知识用于注入上下文"""
        parts = []
        
        # 显式事实
        if keyword:
            facts = self.search_explicit(keyword, limit=limit)
        else:
            facts = self.all_explicit(limit=limit)
        
        if facts:
            lines = ["【已知事实】"]
            for f in facts:
                lines.append(f"- {f.key}: {f.value}")
            parts.append("\n".join(lines))
        
        # 高置信度推断
        inferences = self.get_implicit(min_confidence=0.6, limit=10)
        if inferences:
            lines = ["【推断知识】"]
            for inf in inferences:
                lines.append(f"- {inf.fact} (置信度:{inf.confidence:.0%})")
            parts.append("\n".join(lines))
        
        return "\n\n".join(parts) if parts else ""
    
    def count(self) -> dict:
        """统计"""
        conn = sqlite3.connect(self.db_path)
        explicit = conn.execute("SELECT COUNT(*) FROM explicit_facts").fetchone()[0]
        implicit = conn.execute(
            "SELECT COUNT(*) FROM implicit_facts WHERE archived = 0"
        ).fetchone()[0]
        conn.close()
        return {"explicit": explicit, "implicit": implicit}
