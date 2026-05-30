#!/usr/bin/env python3
"""生成健康日报/周报。

用法:
  python3 health/summary.py              # 最近 7 天摘要
  python3 health/summary.py --days 1     # 今日摘要
  python3 health/summary.py --days 30    # 月度摘要
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean, median


DATA_FILE = Path("health/data/health_data.json")

THRESHOLDS = {
    "sleep_total_min": {"good": 420, "warn": 360},  # ≥7h good, <6h warn
    "sleep_deep_min": {"good": 90, "warn": 60},      # ≥1.5h good
    "sleep_score": {"good": 70, "warn": 50},
    "steps": {"good": 8000, "warn": 5000},
    "resting_hr": {"good": 60, "warn": 75},           # <60 good, >75 warn
    "spo2": {"good": 96, "block": 90},                # <90 = seek help
    "stress": {"warn": 3},
    "exercise_per_week": {"good": 3, "warn": 1},
}


def load_data() -> dict:
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run 'task health:import' first.")
        sys.exit(1)
    with open(DATA_FILE) as f:
        return json.load(f)


def filter_days(data: dict, days: int) -> dict:
    """只保留最近 N 天的数据。"""
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    filtered = {}
    for cat, records in data.items():
        if cat in ("sleep", "steps", "weight"):
            filtered[cat] = [r for r in records if r.get("date", "") >= cutoff]
        elif cat in ("heart_rate", "spo2", "stress"):
            filtered[cat] = [r for r in records if r.get("ts", "")[:10] >= cutoff]
        else:
            filtered[cat] = records
    return filtered


def summarize_sleep(records: list[dict]) -> dict:
    if not records:
        return {"status": "no_data", "avg_total_min": None, "avg_score": None}
    totals = [r["total_min"] for r in records]
    deeps = [r["deep_min"] for r in records]
    scores = [r["score"] for r in records]
    return {
        "status": "ok",
        "days": len(records),
        "avg_total_min": mean(totals),
        "avg_deep_min": mean(deeps) if deeps else 0,
        "avg_score": mean(scores),
        "best_score": max(scores),
        "worst_score": min(scores),
        "below_warn_days": sum(1 for t in totals if t < THRESHOLDS["sleep_total_min"]["warn"]),
    }


def summarize_steps(records: list[dict]) -> dict:
    if not records:
        return {"status": "no_data"}
    vals = [r["steps"] for r in records]
    return {
        "status": "ok",
        "days": len(records),
        "avg": mean(vals),
        "median": median(vals),
        "max": max(vals),
        "min": min(vals),
        "above_good_days": sum(1 for v in vals if v >= THRESHOLDS["steps"]["good"]),
        "below_warn_days": sum(1 for v in vals if v < THRESHOLDS["steps"]["warn"]),
    }


def summarize_heart_rate(records: list[dict]) -> dict:
    if not records:
        return {"status": "no_data"}
    # 静息心率: 取全天最低 10% 的均值作为近似
    all_bpm = sorted([r["bpm"] for r in records])
    n = max(1, len(all_bpm) // 10)
    resting = mean(all_bpm[:n])
    return {
        "status": "ok",
        "records": len(records),
        "resting_hr_est": round(resting, 1),
        "avg_hr": round(mean(all_bpm), 1),
        "max_hr": max(all_bpm),
        "min_hr": min(all_bpm),
    }


def summarize_spo2(records: list[dict]) -> dict:
    if not records:
        return {"status": "no_data"}
    vals = [r["spo2"] for r in records]
    below_block = sum(1 for v in vals if v < THRESHOLDS["spo2"]["block"])
    return {
        "status": "ok",
        "avg": mean(vals),
        "min": min(vals),
        "below_block": below_block,
        "alert": below_block > 0,
    }


def summarize_stress(records: list[dict]) -> dict:
    if not records:
        return {"status": "no_data"}
    levels = [r["level"] for r in records]
    avg = mean(levels)
    high_pct = sum(1 for l in levels if l >= THRESHOLDS["stress"]["warn"]) / len(levels) * 100
    return {
        "status": "ok",
        "avg_level": round(avg, 1),
        "high_pct": round(high_pct, 1),
        "alert": avg >= THRESHOLDS["stress"]["warn"],
    }


def summarize_exercise(records: list[dict], days: int) -> dict:
    if not records:
        return {"status": "no_data"}
    # 过滤最近 N 天的运动
    cutoff = (date.today() - timedelta(days=days - 1)).isoformat()
    recent = [r for r in records if (r.get("start", "") or "")[:10] >= cutoff]
    types = defaultdict(int)
    total_cal = 0
    for r in recent:
        types[r["type"]] += 1
        total_cal += r.get("calories", 0)
    weeks = max(1, days / 7)
    return {
        "status": "ok",
        "total_sessions": len(recent),
        "per_week": round(len(recent) / weeks, 1),
        "total_calories": total_cal,
        "types": dict(types),
    }


def print_report(summary: dict, days: int):
    """格式化输出。"""
    label = "今日" if days == 1 else f"最近 {days} 天"

    print(f"╔══════════════════════════════╗")
    print(f"║   🫀 健康摘要 — {label}  ║")
    print(f"╚══════════════════════════════╝")
    print()

    # 睡眠
    s = summary.get("sleep", {})
    if s.get("status") == "ok":
        score = s["avg_score"]
        emoji = "✅" if score >= 70 else ("⚠️" if score >= 50 else "🔴")
        print(f"😴 睡眠  {emoji}")
        print(f"   日均: {s['avg_total_min']:.0f}min ({s['avg_total_min']/60:.1f}h)")
        print(f"   深睡: {s['avg_deep_min']:.0f}min")
        print(f"   评分: {score:.0f}/100")
        if s["below_warn_days"]:
            print(f"   ⚠️  {s['below_warn_days']}/{s['days']} 天不足 6h")

    # 步数
    st = summary.get("steps", {})
    if st.get("status") == "ok":
        emoji = "✅" if st["avg"] >= 8000 else ("⚠️" if st["avg"] >= 5000 else "🔴")
        print(f"\n👟 步数  {emoji}")
        print(f"   日均: {st['avg']:.0f}")
        print(f"   达标: {st['above_good_days']}/{st['days']} 天 (≥8000)")
        if st["below_warn_days"]:
            print(f"   ⚠️  {st['below_warn_days']}/{st['days']} 天不足 5000")

    # 心率
    hr = summary.get("heart_rate", {})
    if hr.get("status") == "ok":
        rhr = hr["resting_hr_est"]
        emoji = "✅" if rhr <= 60 else ("⚠️" if rhr <= 75 else "🔴")
        print(f"\n💓 心率  {emoji}")
        print(f"   静息(估): {rhr} bpm")
        print(f"   全天均值: {hr['avg_hr']} bpm")

    # 运动
    ex = summary.get("exercise", {})
    if ex.get("status") == "ok":
        pw = ex["per_week"]
        emoji = "✅" if pw >= 3 else ("⚠️" if pw >= 1 else "🔴")
        print(f"\n🏃 运动  {emoji}")
        print(f"   次数: {ex['total_sessions']} ({pw}/周)")
        print(f"   消耗: {ex['total_calories']} kcal")
        if ex["types"]:
            types_str = ", ".join(f"{t}×{c}" for t, c in ex["types"].items())
            print(f"   类型: {types_str}")

    # 血氧
    sp = summary.get("spo2", {})
    if sp.get("status") == "ok":
        emoji = "✅" if not sp["alert"] else "🔴"
        print(f"\n🫁 血氧  {emoji}")
        print(f"   均值: {sp['avg']:.1f}%")
        if sp["alert"]:
            print(f"   🔴 低于 90%! 建议就医。")

    # 压力
    sts = summary.get("stress", {})
    if sts.get("status") == "ok":
        emoji = "⚠️" if sts["alert"] else "✅"
        print(f"\n🧠 压力  {emoji}")
        print(f"   均值: {sts['avg_level']}")
        print(f"   高压力占比: {sts['high_pct']:.0f}%")

    # 总体评估
    print(f"\n{'─' * 30}")
    alerts = _count_alerts(summary)
    if alerts == 0:
        print("✅ 全部指标在健康范围")
    elif alerts <= 2:
        print(f"⚠️  {alerts} 项指标需要关注")
    else:
        print(f"🔴 {alerts} 项指标需要行动")


def _count_alerts(summary: dict) -> int:
    count = 0
    s = summary.get("sleep", {})
    if s.get("avg_score", 100) < 50:
        count += 1
    st = summary.get("steps", {})
    if st.get("avg", 10000) < 5000:
        count += 1
    hr = summary.get("heart_rate", {})
    if hr.get("resting_hr_est", 60) > 75:
        count += 1
    ex = summary.get("exercise", {})
    if ex.get("per_week", 7) < 1:
        count += 1
    sp = summary.get("spo2", {})
    if sp.get("alert", False):
        count += 1
    sts = summary.get("stress", {})
    if sts.get("alert", False):
        count += 1
    return count


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="统计天数 (默认 7)")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args()

    data = load_data()
    filtered = filter_days(data, args.days)

    summary = {
        "sleep": summarize_sleep(filtered.get("sleep", [])),
        "steps": summarize_steps(filtered.get("steps", [])),
        "heart_rate": summarize_heart_rate(filtered.get("heart_rate", [])),
        "exercise": summarize_exercise(filtered.get("exercise", []), args.days),
        "spo2": summarize_spo2(filtered.get("spo2", [])),
        "stress": summarize_stress(filtered.get("stress", [])),
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
    else:
        print_report(summary, args.days)


if __name__ == "__main__":
    main()
