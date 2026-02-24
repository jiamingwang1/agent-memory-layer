"""
知识层 (Knowledge/Semantic Layer) — 第二层记忆

对应人脑：大脑皮层的语义记忆
存储：事实、偏好、规律、学到的知识 — 不带"什么时候学的"，只有"知道什么"
"""

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Fact:
    """一条知识/事实"""
    id: str
    category: str       # person/preference/rule/skill/world
    subject: str        # 关于谁/什么
    predicate: str      # 属性/关系
    value: str          # 值
    confidence: float = 0.8   # 0-1 置信度
    source: str = ""          # 从哪学到的
    created: str = ""
    updated: str = ""
    access_count: int = 0
    superseded_by: str = ""   # 如果被更新，指向新fact的id


class KnowledgeMemory:
    """知识记忆存储"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS facts (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    predicate TEXT NOT NULL,
                    value TEXT NOT NULL,
                    confidence REAL DEFAULT 0.8,
                    source TEXT DEFAULT '',
                    created TEXT NOT NULL,
                    updated TEXT NOT NULL,
                    access_count INTEGER DEFAULT 0,
                    superseded_by TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_subject 
                ON facts(subject)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_category 
                ON facts(category)
            """)

    def store(self, fact: Fact) -> str:
        """存储一条知识。如果subject+predicate已存在，更新而不是重复。"""
        now = datetime.now(timezone.utc).isoformat()
        if not fact.created:
            fact.created = now
        fact.updated = now

        with sqlite3.connect(self.db_path) as conn:
            # 检查是否已有同subject+predicate的fact
            existing = conn.execute(
                "SELECT id, value, confidence FROM facts "
                "WHERE subject=? AND predicate=? AND superseded_by=''",
                (fact.subject, fact.predicate)
            ).fetchone()

            if existing and existing[1] != fact.value:
                # 值变了 → 标记旧的为superseded
                conn.execute(
                    "UPDATE facts SET superseded_by=?, updated=? WHERE id=?",
                    (fact.id, now, existing[0])
                )

            conn.execute(
                "INSERT OR REPLACE INTO facts VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (fact.id, fact.category, fact.subject, fact.predicate,
                 fact.value, fact.confidence, fact.source,
                 fact.created, fact.updated, fact.access_count,
                 fact.superseded_by)
            )
        return fact.id

    def query(self, subject: str = None, category: str = None,
              predicate: str = None, active_only: bool = True,
              limit: int = 50) -> list[Fact]:
        """查询知识"""
        conditions = []
        params = []

        if active_only:
            conditions.append("superseded_by = ''")
        if subject:
            conditions.append("subject LIKE ?")
            params.append(f"%{subject}%")
        if category:
            conditions.append("category = ?")
            params.append(category)
        if predicate:
            conditions.append("predicate LIKE ?")
            params.append(f"%{predicate}%")

        where = " AND ".join(conditions) if conditions else "1=1"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"SELECT * FROM facts WHERE {where} "
                f"ORDER BY updated DESC LIMIT ?",
                params + [limit]
            ).fetchall()

            # 更新access_count
            ids = [r["id"] for r in rows]
            if ids:
                placeholders = ",".join("?" * len(ids))
                conn.execute(
                    f"UPDATE facts SET access_count = access_count + 1 "
                    f"WHERE id IN ({placeholders})", ids
                )

            return [self._row_to_fact(r) for r in rows]

    def about(self, subject: str) -> dict:
        """获取关于某个主题的所有知识，按predicate分组"""
        facts = self.query(subject=subject)
        result = {}
        for f in facts:
            result[f.predicate] = {
                "value": f.value,
                "confidence": f.confidence,
                "updated": f.updated,
            }
        return result

    def count(self, active_only: bool = True) -> int:
        with sqlite3.connect(self.db_path) as conn:
            where = "superseded_by = ''" if active_only else "1=1"
            return conn.execute(f"SELECT COUNT(*) FROM facts WHERE {where}").fetchone()[0]

    def format_knowledge(self, subject: str, max_chars: int = 1500) -> str:
        """格式化某主题的知识为可注入文本"""
        facts = self.query(subject=subject)
        if not facts:
            return ""

        lines = [f"## 📚 关于{subject}的知识\n"]
        chars = 0
        for f in facts:
            conf_tag = "✓" if f.confidence > 0.7 else "?"
            line = f"- {conf_tag} {f.predicate}: {f.value}\n"
            if chars + len(line) > max_chars:
                break
            lines.append(line)
            chars += len(line)

        return "\n".join(lines)

    def _row_to_fact(self, row) -> Fact:
        return Fact(
            id=row["id"],
            category=row["category"],
            subject=row["subject"],
            predicate=row["predicate"],
            value=row["value"],
            confidence=row["confidence"],
            source=row["source"],
            created=row["created"],
            updated=row["updated"],
            access_count=row["access_count"],
            superseded_by=row["superseded_by"],
        )


# ===== 测试 =====
if __name__ == "__main__":
    import tempfile, os

    with tempfile.TemporaryDirectory() as tmpdir:
        db = os.path.join(tmpdir, "knowledge.db")
        km = KnowledgeMemory(db)

        # 存储关于aa的知识
        km.store(Fact(id="f1", category="person", subject="aa",
                       predicate="年龄", value="17岁", confidence=1.0,
                       source="USER.md"))
        km.store(Fact(id="f2", category="person", subject="aa",
                       predicate="交易所", value="Gate.io", confidence=1.0,
                       source="对话"))
        km.store(Fact(id="f3", category="preference", subject="aa",
                       predicate="沟通风格", value="简洁直接，不要废话",
                       confidence=0.95, source="多次对话"))
        km.store(Fact(id="f4", category="rule", subject="小助",
                       predicate="铁律", value="做完就写记忆",
                       confidence=1.0, source="SOUL.md"))

        # 知识更新（aa以前用Binance，现在用Gate）
        km.store(Fact(id="f5", category="person", subject="aa",
                       predicate="交易所", value="Gate.io（之前用过Binance）",
                       confidence=1.0, source="2026-02纠正"))

        # 查询
        aa_facts = km.query(subject="aa")
        assert len(aa_facts) >= 3, f"应该有3+条关于aa的知识，实际{len(aa_facts)}"

        about = km.about("aa")
        assert "年龄" in about
        assert about["交易所"]["value"].startswith("Gate")

        # 格式化输出
        text = km.format_knowledge("aa")
        assert "Gate" in text

        print("=== 关于aa的知识 ===")
        print(text)
        print(f"\n总知识量: {km.count()} 条活跃, {km.count(active_only=False)} 条总计")
        print("\n✅ Knowledge层所有测试通过！")
