#!/bin/bash
# 心跳时快速调用记忆系统——可在HEARTBEAT.md中引用
# 用法: bash projects/memory-layer/heartbeat_hook.sh
cd "$(dirname "$0")"
python3 cli.py health 2>/dev/null
