#!/usr/bin/env python3
"""
记忆系统 CLI — OpenClaw可通过exec调用

用法：
  python3 cli.py init                          # 初始化（首次）
  python3 cli.py inject [--person aa] [--query "..."]  # 生成注入文本
  python3 cli.py remember "发生了什么" [--tags t1,t2] [--importance 0.8]
  python3 cli.py learn <subject> <predicate> <value> [--confidence 0.9]
  python3 cli.py health                        # 健康报告
  python3 cli.py compression                   # 记录压缩事件
  python3 cli.py about <subject>               # 查询某主题知识
  python3 cli.py recall <query> [--person aa]  # 回忆相关记忆
"""

import argparse
import os
import sys

# 确保能找到本项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from memory_system import MemorySystem

DEFAULT_DATA_DIR = os.path.join(
    os.path.expanduser("~"), ".openclaw", "workspace", "memory-data"
)

# embedding配置（贞贞工坊）
EMBEDDING_CONFIG = {
    "api_base": "https://ai.t8star.cn/v1",
    "api_key": os.environ.get("EMBEDDING_API_KEY", ""),
    "model": "text-embedding-3-small",
}


def get_system(data_dir: str = None) -> MemorySystem:
    d = data_dir or os.environ.get("MEMORY_DATA_DIR", DEFAULT_DATA_DIR)
    emb = EMBEDDING_CONFIG if EMBEDDING_CONFIG["api_key"] else None
    return MemorySystem(d, embedding_config=emb)


def cmd_init(args):
    ms = get_system(args.data_dir)
    print(f"✅ 记忆系统初始化完成: {ms.data_dir}")
    print(f"   本能层: v{ms.instinct.profile.version}")
    print(f"   知识层: {ms.knowledge.count()}条")
    print(f"   情景层: {ms.episodic.count()}条")
    print(f"   元认知: session#{ms.meta.session_count}")


def cmd_inject(args):
    ms = get_system(args.data_dir)
    text = ms.on_session_start(
        opening_message=args.query or "",
        person_id=args.person,
    )
    print(text)


def cmd_remember(args):
    ms = get_system(args.data_dir)
    tags = args.tags.split(",") if args.tags else []
    ms.remember(
        summary=args.summary,
        valence=args.valence,
        arousal=args.arousal,
        importance=args.importance,
        participants=args.person.split(",") if args.person else [],
        tags=tags,
    )
    print(f"✅ 已记住: {args.summary}")


def cmd_learn(args):
    import hashlib
    fact_id = "f_" + hashlib.md5(
        f"{args.subject}:{args.predicate}".encode()
    ).hexdigest()[:8]
    ms = get_system(args.data_dir)
    ms.learn_fact(
        fact_id=fact_id,
        category=args.category,
        subject=args.subject,
        predicate=args.predicate,
        value=args.value,
        confidence=args.confidence,
        source=args.source,
    )
    print(f"✅ 已学习: {args.subject}.{args.predicate} = {args.value}")


def cmd_health(args):
    ms = get_system(args.data_dir)
    print(ms.health_check())


def cmd_compression(args):
    ms = get_system(args.data_dir)
    ms.on_compression()
    print(f"⚠️ 已记录第{ms.meta.compression_count}次压缩")


def cmd_about(args):
    ms = get_system(args.data_dir)
    text = ms.knowledge.format_knowledge(args.subject)
    if text:
        print(text)
    else:
        print(f"没有关于 {args.subject} 的知识")


def cmd_sleep(args):
    ms = get_system(args.data_dir)
    result = ms.sleep(person_id=args.person or "default")
    print(f"😴 睡眠整理完成:")
    print(f"   遗忘: {result['archived']}条")
    print(f"   强化: {result['strengthened']}条")
    if result.get('patterns'):
        print(f"   发现模式: {len(result['patterns'])}个")
    if result.get('mood_trend') != 'unknown':
        print(f"   情绪趋势: {result['mood_trend']}")


def cmd_recall(args):
    ms = get_system(args.data_dir)
    memories = ms.recall.recall(
        query=args.query,
        person_id=args.person,
        max_results=args.limit,
    )
    if not memories:
        print("没有回忆起相关记忆")
        return
    text = ms.recall.format_for_injection(memories)
    print(text)


def main():
    parser = argparse.ArgumentParser(description="五层记忆系统 CLI")
    parser.add_argument("--data-dir", default=None, help="数据目录")
    sub = parser.add_subparsers(dest="command")

    # init
    sub.add_parser("init", help="初始化记忆系统")

    # inject
    p = sub.add_parser("inject", help="生成session注入文本")
    p.add_argument("--person", default=None)
    p.add_argument("--query", default="")

    # remember
    p = sub.add_parser("remember", help="记住一件事")
    p.add_argument("summary")
    p.add_argument("--tags", default="")
    p.add_argument("--person", default="")
    p.add_argument("--importance", type=float, default=0.5)
    p.add_argument("--valence", type=float, default=0.0)
    p.add_argument("--arousal", type=float, default=0.5)

    # learn
    p = sub.add_parser("learn", help="学习一条知识")
    p.add_argument("subject")
    p.add_argument("predicate")
    p.add_argument("value")
    p.add_argument("--category", default="general")
    p.add_argument("--confidence", type=float, default=0.8)
    p.add_argument("--source", default="cli")

    # health
    sub.add_parser("health", help="健康报告")

    # compression
    sub.add_parser("compression", help="记录压缩事件")

    # about
    p = sub.add_parser("about", help="查询主题知识")
    p.add_argument("subject")

    # recall
    p = sub.add_parser("recall", help="回忆相关记忆")
    p.add_argument("query")
    p.add_argument("--person", default=None)
    p.add_argument("--limit", type=int, default=8)

    # sleep
    p = sub.add_parser("sleep", help="执行睡眠整理")
    p.add_argument("--person", default=None)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    cmds = {
        "init": cmd_init, "inject": cmd_inject,
        "remember": cmd_remember, "learn": cmd_learn,
        "health": cmd_health, "compression": cmd_compression,
        "about": cmd_about, "recall": cmd_recall, "sleep": cmd_sleep,
    }
    cmds[args.command](args)


if __name__ == "__main__":
    main()
