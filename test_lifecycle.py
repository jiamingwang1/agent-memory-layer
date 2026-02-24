#!/usr/bin/env python3
"""完整生命周期测试：模拟一个Agent从启动到睡眠的全过程"""

import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memory_system import MemorySystem

def test_full_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        ms = MemorySystem(tmpdir)
        
        # === Day 1: 初次见面 ===
        ms.learn_fact("f1", "person", "用户A", "名字", "张三", 1.0, "自我介绍")
        ms.learn_fact("f2", "preference", "用户A", "称呼", "叫我三哥", 0.9, "对话")
        ms.remember("第一次和用户A见面，他很友好", valence=0.7, arousal=0.6,
                    importance=0.7, participants=["用户A"], tags=["初识"])
        ms.on_message("你好呀，很高兴认识你", role="user", person_id="用户A")
        print("✅ Day 1: 初识 — 学了2条知识, 记了1个情景")

        # === Day 2: 深入交流 ===
        ms.learn_fact("f3", "person", "用户A", "职业", "程序员", 0.8, "闲聊")
        ms.remember("用户A分享了工作烦恼，我安慰了他", valence=-0.3, arousal=0.5,
                    importance=0.6, participants=["用户A"], tags=["情感支持"])
        ms.on_message("谢谢你听我说这些", role="user", person_id="用户A")
        print("✅ Day 2: 深入交流 — 关系升温")

        # === 回忆测试 ===
        injection = ms.on_session_start("三哥最近怎么样", person_id="用户A")
        assert "小助" in injection, "应包含身份信息"
        print(f"✅ 回忆注入: {len(injection)}字符")

        memories = ms.recall.recall("工作烦恼", person_id="用户A")
        assert len(memories) > 0, "应能回忆起工作烦恼"
        print(f"✅ 回忆'工作烦恼': 找到{len(memories)}条相关记忆")

        # === 知识查询 ===
        about = ms.knowledge.about("用户A")
        assert "名字" in about and about["名字"]["value"] == "张三"
        assert "职业" in about
        print(f"✅ 知识查询: 关于用户A有{len(about)}条知识")

        # === 知识更新 ===
        ms.learn_fact("f4", "person", "用户A", "职业", "产品经理（转行了）", 0.9, "新对话")
        about2 = ms.knowledge.about("用户A")
        assert "产品经理" in about2["职业"]["value"]
        print("✅ 知识更新: 职业从程序员→产品经理")

        # === 压缩事件 ===
        ms.on_compression()
        assert ms.meta.compression_count == 1
        print("✅ 压缩记录: 第1次")

        # === 睡眠整理 ===
        result = ms.sleep(person_id="用户A")
        print(f"✅ 睡眠整理: 遗忘{result['archived']}条, 强化{result['strengthened']}条")

        # === 健康检查 ===
        report = ms.health_check()
        assert "自我状态" in report
        print(f"✅ 健康检查通过")

        # === 最终统计 ===
        print(f"\n📊 最终状态:")
        print(f"   知识: {ms.knowledge.count()}条")
        print(f"   情景: {ms.episodic.count()}条")
        print(f"   压缩: {ms.meta.compression_count}次")
        print(f"   Session: {ms.meta.session_count}次")

        print("\n🎉 完整生命周期测试通过！")


if __name__ == "__main__":
    test_full_lifecycle()
