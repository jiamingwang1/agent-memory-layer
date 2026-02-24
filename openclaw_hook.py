#!/usr/bin/env python3
"""
OpenClaw 集成钩子 (v2) — 适配新五层架构

使用方式：
  # session开始时注入记忆上下文
  python3 openclaw_hook.py inject --query "早上好"
  
  # 记录一条对话（心跳/compaction时批量调）
  python3 openclaw_hook.py record --text "aa说要做记忆层项目" --emotion excited --importance 0.8
  
  # 学习一个事实
  python3 openclaw_hook.py learn --subject "aa" --predicate "交易所" --value "Gate.io"
  
  # 睡眠整理（cron凌晨跑）
  python3 openclaw_hook.py sleep
  
  # 健康检查
  python3 openclaw_hook.py health
  
  # 压缩前刷盘（pre-compaction）
  python3 openclaw_hook.py flush --conversation-file /tmp/conv.json
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

from memory_system import MemorySystem
from layers.episodic import Episode

DATA_DIR = os.path.expanduser("~/.openclaw/workspace/memory-data")
EMBEDDING_KEY = os.getenv("EMBEDDING_API_KEY", "")
EMBEDDING_BASE = os.getenv("EMBEDDING_API_BASE", "https://ai.t8star.cn/v1")


def get_system() -> MemorySystem:
    return MemorySystem(data_dir=DATA_DIR)


def cmd_inject(args):
    """session开始时生成记忆注入文本"""
    ms = get_system()
    ctx = ms.on_session_start(opening_message=args.query or "", person_id=args.user)
    print(ctx)


def cmd_record(args):
    """记录一条情景记忆"""
    ms = get_system()
    valence = {"happy": 0.8, "excited": 0.9, "sad": -0.7, "angry": -0.8, "neutral": 0.0, "focused": 0.3}.get(args.emotion or "neutral", 0.0)
    ep = Episode(
        id=str(uuid.uuid4())[:8],
        timestamp=datetime.now(timezone.utc).isoformat(),
        summary=args.text,
        emotional_valence=valence,
        emotional_arousal=abs(valence) * 0.8,
        importance_score=float(args.importance or 0.5),
        participants=["xiaozhu"],
        tags=args.tags.split(",") if args.tags else [],
    )
    ms.episodic.store(ep)
    print(f"✅ 已记录: {args.text[:60]}...")


def cmd_learn(args):
    """学习一个知识三元组"""
    ms = get_system()
    fact_id = f"hook_{uuid.uuid4().hex[:8]}"
    ms.learn_fact(
        fact_id=fact_id,
        category="general",
        subject=args.subject,
        predicate=args.predicate,
        value=args.value,
        confidence=float(args.confidence or 0.9),
        source=args.source or "openclaw_hook",
    )
    print(f"✅ 已学习: {args.subject} → {args.predicate} → {args.value}")


def cmd_sleep(args):
    """运行睡眠整理"""
    ms = get_system()
    result = ms.sleep()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_health(args):
    """健康检查"""
    ms = get_system()
    report = ms.health_check()
    print(report)


def cmd_flush(args):
    """压缩前刷盘 — 从对话JSON提取记忆"""
    ms = get_system()
    
    if args.conversation_file and os.path.exists(args.conversation_file):
        with open(args.conversation_file) as f:
            conversation = json.load(f)
    else:
        # 从stdin读
        data = sys.stdin.read().strip()
        if not data:
            print("❌ 没有对话数据")
            return
        conversation = json.loads(data)
    
    # 提取关键信息存入情景记忆
    count = 0
    for msg in conversation:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if not content or role == "system":
            continue
        # 只存重要的（长度>50或用户消息）
        if role == "user" or len(content) > 100:
            ms.episodic.remember(
                content=f"[{role}] {content[:300]}",
                emotion="neutral",
                importance=0.4 if role == "assistant" else 0.6,
            )
            count += 1
    
    ms.on_session_end()
    print(f"✅ 刷盘完成: {count}条记忆已保存")


def cmd_recall(args):
    """测试回忆"""
    ms = get_system()
    memories = ms.remember(query=args.query, user_id=args.user, top_k=int(args.limit or 5))
    for m in memories:
        print(f"  [{m.get('score', '?'):.2f}] {m.get('content', '')[:100]}")


def main():
    parser = argparse.ArgumentParser(description="Memory Layer OpenClaw Hook v2")
    sub = parser.add_subparsers(dest="command")
    
    # inject
    p = sub.add_parser("inject", help="注入记忆上下文")
    p.add_argument("--query", default="")
    p.add_argument("--user", default="aa")
    
    # record
    p = sub.add_parser("record", help="记录情景记忆")
    p.add_argument("--text", required=True)
    p.add_argument("--emotion", default="neutral")
    p.add_argument("--importance", default="0.5")
    p.add_argument("--tags", default="")
    
    # learn
    p = sub.add_parser("learn", help="学习知识")
    p.add_argument("--subject", required=True)
    p.add_argument("--predicate", required=True)
    p.add_argument("--value", required=True)
    p.add_argument("--confidence", default="0.9")
    p.add_argument("--source", default="")
    
    # sleep
    sub.add_parser("sleep", help="睡眠整理")
    
    # health
    sub.add_parser("health", help="健康检查")
    
    # flush
    p = sub.add_parser("flush", help="压缩前刷盘")
    p.add_argument("--conversation-file", default="")
    
    # recall
    p = sub.add_parser("recall", help="测试回忆")
    p.add_argument("--query", required=True)
    p.add_argument("--user", default="aa")
    p.add_argument("--limit", default="5")
    
    args = parser.parse_args()
    
    commands = {
        "inject": cmd_inject,
        "record": cmd_record,
        "learn": cmd_learn,
        "sleep": cmd_sleep,
        "health": cmd_health,
        "flush": cmd_flush,
        "recall": cmd_recall,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
