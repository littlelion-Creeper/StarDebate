# -*- coding: utf-8 -*-
"""
辩论智能助手插件
==================
功能：
  1. 一键分析辩稿质量（逻辑、论据、结构）
  2. 自动生成改进建议
  3. 导出 Markdown 分析报告
  4. 监听辩稿保存事件，自动触发分析

使用方法：
  - 导入插件后自动生效
  - 保存一辩稿时自动分析（可配置关闭）
  - 手动调用 analyze() 随时分析当前辩稿
"""

import json
import os
from datetime import datetime
from workers.plugin_manager import get_api

# ── 插件元信息 ──
PLUGIN_ID = "debate_assistant"
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
#  工具函数
# ============================================================

def load_config() -> dict:
    """读取插件配置"""
    config_path = os.path.join(PLUGIN_DIR, "plugin.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("config", {})
    except Exception:
        return {}


def get_side_label(side: str) -> str:
    """将 'pro'/'con' 转为中文标签"""
    return "正方" if side == "pro" else "反方"


def count_stats(text: str) -> dict:
    """统计文本的基本指标"""
    chars = len(text.replace("\n", "").replace(" ", ""))
    lines = len(text.split("\n"))
    paragraphs = len([p for p in text.split("\n\n") if p.strip()])
    # 估算句子数（以中文句号、问号、感叹号分隔）
    import re
    sentences = len(re.findall(r'[。！？；]', text))
    return {
        "total_chars": chars,
        "total_lines": lines,
        "paragraphs": paragraphs,
        "sentences": max(sentences, 1),
    }


# ============================================================
#  核心分析功能
# ============================================================

def build_system_prompt(depth: str) -> str:
    """根据分析深度构建系统提示词"""
    base = (
        "你是一位资深的辩论教练和裁判，拥有丰富的辩论评审经验。\n"
        "你的分析应当专业、客观、具体，避免空洞的赞美或批评。\n"
        "请始终用中文输出。"
    )

    if depth == "simple":
        return base + "\n请给出简洁的分析，每部分控制在2-3句话。"
    elif depth == "detailed":
        return base + (
            "\n请提供详细的分析，包括：\n"
            "1. 每个论点的逻辑结构\n"
            "2. 论据的有效性评估\n"
            "3. 具体可操作的改进建议\n"
            "4. 整体评分（1-10分）"
        )
    else:  # comprehensive
        return base + (
            "\n请提供最全面的分析，从以下维度展开：\n"
            "一、论点结构与逻辑链\n"
            "二、论据质量与引用\n"
            "三、语言表达与修辞\n"
            "四、反驳预案与防御\n"
            "五、整体战略评估\n"
            "六、与经典辩论理论的对比\n"
            "七、具体改进路径图"
        )


def analyze_speech(side: str) -> str | None:
    """
    分析指定一方的辩稿质量。
    返回 Markdown 格式的分析报告，失败返回 None。
    """
    api = get_api()
    config = load_config()

    # ── 读取辩稿 ──
    text = api.get_speech_content(side)
    if not text or len(text.strip()) < 20:
        api.show_notification(
            "分析失败",
            f"{get_side_label(side)}一辩稿内容过短（不足20字），请先编辑辩稿。"
        )
        return None

    info = api.get_debate_info()
    if not info.get("title"):
        api.show_notification("分析失败", "请先打开一个辩论项目。")
        return None

    # ── 基础统计 ──
    stats = count_stats(text)
    side_label = get_side_label(side)

    # ── 构建 AI 请求 ──
    system_prompt = build_system_prompt(config.get("analysis_depth", "detailed"))

    user_prompt = (
        f"请分析以下辩论稿的质量：\n\n"
        f"【辩题】{info.get('title', '未知')}\n"
        f"【方立场】{side_label} — {info.get(f'{side}_side', '')}\n"
        f"【基础数据】字数: {stats['total_chars']}, "
        f"段落: {stats['paragraphs']}, 句子: {stats['sentences']}\n\n"
        f"=== 辩稿正文 ===\n{text}\n=== 正文结束 ===\n\n"
        f"请给出分析结果。"
    )

    api.update_status(f"正在 AI 分析{side_label}辩稿...")
    max_tokens = config.get("max_output_tokens", 2048)

    try:
        analysis = api.call_ai(
            messages=[{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=0.3,  # 低温度以获得一致的分析
        )

        # ── 构建完整报告 ──
        report = build_report(info, side_label, stats, analysis)
        return report

    except ValueError as e:
        api.show_notification("参数错误", f"AI 调用参数有误: {e}")
        return None
    except RuntimeError as e:
        api.show_notification("AI 调用失败", str(e)[:200])
        return None
    except Exception as e:
        api.show_notification("未知错误", f"分析过程出错: {str(e)[:200]}")
        return None


def build_report(info: dict, side_label: str, stats: dict, ai_analysis: str) -> str:
    """组装 Markdown 格式的完整分析报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = (
        f"# 辩论辩稿分析报告\n\n"
        f"> 生成时间：{now}  |  插件：辩论智能助手 v1.0.0\n\n"
        f"---\n\n"
        f"## 📋 基本信息\n\n"
        f"| 项目 | 内容 |\n"
        f"|------|------|\n"
        f"| 辩题 | {info.get('title', '未知')} |\n"
        f"| 分析方 | {side_label} — {info.get('pro_side' if side_label == '正方' else 'con_side', '')} |\n"
        f"| 字数 | {stats['total_chars']} |\n"
        f"| 段落 | {stats['paragraphs']} |\n"
        f"| 句子 | {stats['sentences']} |\n\n"
        f"---\n\n"
        f"## 🤖 AI 分析\n\n"
        f"{ai_analysis}\n\n"
        f"---\n\n"
        f"## 📊 统计信息\n\n"
        f"- 总字符数：{stats['total_chars']}\n"
        f"- 总行数：{stats['total_lines']}\n"
        f"- 段落数：{stats['paragraphs']}\n"
        f"- 句子数：{stats['sentences']}\n\n"
        f"---\n\n"
        f"*报告由 StarDebate「辩论智能助手」插件自动生成*\n"
    )
    return report


# ============================================================
#  公开接口（供用户手动调用）
# ============================================================

def analyze(side: str = ""):
    """
    手动分析辩稿。
    调用方式（在其他代码中）：
        from plugins.debate_assistant.main import analyze
        analyze("pro")   # 分析正方
        analyze("con")   # 分析反方
        analyze()        # 分析双方
    """
    api = get_api()

    if side:
        sides = [side]
    else:
        sides = ["pro", "con"]

    info = api.get_debate_info()
    if not info.get("title"):
        api.show_notification("操作失败", "请先打开一个辩论项目。")
        return

    for s in sides:
        report = analyze_speech(s)
        if report:
            side_label = get_side_label(s)
            filename = f"analysis_report_{side_label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            success = api.write_file_in_project(filename, report)
            if success:
                api.update_status(f"{side_label}分析报告已保存: {filename}")
                api.show_notification(
                    f"分析完成 — {side_label}",
                    f"报告已保存到项目目录:\n{filename}"
                )
            else:
                api.show_notification(
                    "保存失败",
                    f"无法保存{side_label}报告，请检查项目是否有效。"
                )


def analyze_all():
    """分析双方辩稿（analyze() 的别名）"""
    analyze()


def quick_feedback():
    """快速一句话反馈当前辩稿"""
    api = get_api()
    info = api.get_debate_info()
    if not info.get("title"):
        api.show_notification("操作失败", "请先打开一个辩论项目。")
        return

    feedbacks = []
    for s in ["pro", "con"]:
        text = api.get_speech_content(s)
        if text and len(text.strip()) >= 20:
            try:
                reply = api.call_ai(
                    messages=[{
                        "role": "user",
                        "content": f"请用一句话（20字内）点评这篇辩稿的优势：{text[:500]}"
                    }],
                    system_prompt="你是辩论教练，点评简洁有力。",
                    max_tokens=60,
                    temperature=0.5,
                )
                feedbacks.append(f"- **{get_side_label(s)}**：{reply.strip()}")
            except Exception:
                pass

    if feedbacks:
        api.show_notification(
            "快速反馈",
            "\n".join(feedbacks)
        )
    else:
        api.show_notification("快速反馈", "双方辩稿内容不足，无法分析。")


# ============================================================
#  事件钩子
# ============================================================

def _on_speech_saved(side: str):
    """辩稿保存时的回调"""
    api = get_api()
    config = load_config()

    if not config.get("auto_analyze_on_save", True):
        return

    text = api.get_speech_content(side)
    stats = count_stats(text)
    api.update_status(
        f"📊 {get_side_label(side)}辩稿: {stats['total_chars']}字 | "
        f"可在插件中调用 analyze() 进行 AI 分析"
    )


# ============================================================
#  生命周期
# ============================================================

def on_enable():
    """插件启用时调用"""
    api = get_api()
    # 注册右侧导航栏按钮：一键分析双方辩稿
    api.register_nav_button(
        side="right",
        emoji="🤖",
        label="分析",
        tooltip="AI 分析双方辩稿质量",
        callback=analyze_all,
    )
    api.update_status("辩论智能助手已就绪！")
    # 监听辩稿保存事件
    api.on("speech_saved", _on_speech_saved)


def on_disable():
    """插件禁用时调用"""
    api = get_api()
    api.off("speech_saved", _on_speech_saved)
    api.update_status("辩论智能助手已停止")


# ============================================================
#  调试入口（直接运行此文件可测试）
# ============================================================

if __name__ == "__main__":
    # 独立测试（需要先启动 StarDebate 主窗口）
    print("=" * 50)
    print("  辩论智能助手 v1.0.0")
    print("  请在 StarDebate 中导入此插件使用")
    print("=" * 50)
    print()
    print("可用功能：")
    print("  analyze('pro')    — 分析正方辩稿")
    print("  analyze('con')    — 分析反方辩稿")
    print("  analyze()         — 分析双方辩稿")
    print("  quick_feedback()  — 快速一句话反馈")
    print("  analyze_all()     — 同 analyze()")
    print()
    print("导入步骤：")
    print("  1. 打开 StarDebate → 🔌 插件 → 📥 导入插件")
    print("  2. 选择 debate_assistant 文件夹")
    print("  3. 插件自动启用")
