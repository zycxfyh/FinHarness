#!/usr/bin/env python3
"""导入华为健康导出数据，标准化为内部 JSON 格式。

用法:
  python3 health/import_health.py health/data/export_20260530/

华为健康导出格式:
  我的 → 设置 → 导出数据 → 解压后的目录

支持的 CSV 文件:
  - 心率/*.csv
  - 睡眠/*.csv
  - 步数/*.csv
  - 运动记录/*.csv
  - 血氧/*.csv
  - 压力/*.csv
  - 体重/*.csv
"""

from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any


def find_csv_files(root: Path) -> dict[str, list[Path]]:
    """扫描目录，按类型分类 CSV 文件。"""
    categories: dict[str, list[Path]] = defaultdict(list)
    key_map = {
        "心率": "heart_rate",
        "heart": "heart_rate",
        "睡眠": "sleep",
        "sleep": "sleep",
        "步数": "steps",
        "step": "steps",
        "运动记录": "exercise",
        "运动": "exercise",
        "exercise": "exercise",
        "血氧": "spo2",
        "spo2": "spo2",
        "压力": "stress",
        "stress": "stress",
        "体重": "weight",
        "weight": "weight",
        "体脂": "weight",
    }

    for csv_path in root.rglob("*.csv"):
        # 从路径推断类别
        parent = csv_path.parent.name.lower()
        fname = csv_path.name.lower()
        for key, cat in key_map.items():
            if key in parent or key in fname:
                categories[cat].append(csv_path)
                break
        else:
            categories["unknown"].append(csv_path)

    return dict(categories)


def parse_heart_rate(paths: list[Path]) -> list[dict]:
    """心率 CSV: 时间列 + 心率列。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = _parse_time(row)
                    hr = _find_value(row, ["心率", "heart_rate", "bpm", "value"])
                    if hr and ts:
                        records.append({"ts": ts, "bpm": int(float(hr))})
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["ts"])


def parse_sleep(paths: list[Path]) -> list[dict]:
    """睡眠 CSV: 日期 + 深睡/浅睡/REM/清醒(分钟)。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = _parse_date(row)
                    deep = _find_value(row, ["深睡", "deep", "deep_sleep"]) or 0
                    light = _find_value(row, ["浅睡", "light", "light_sleep"]) or 0
                    rem = _find_value(row, ["REM", "rem", "rem_sleep"]) or 0
                    awake = _find_value(row, ["清醒", "awake"]) or 0
                    total = int(float(deep)) + int(float(light)) + int(float(rem)) + int(float(awake))
                    records.append({
                        "date": d,
                        "deep_min": int(float(deep)),
                        "light_min": int(float(light)),
                        "rem_min": int(float(rem)),
                        "awake_min": int(float(awake)),
                        "total_min": total,
                        "score": _sleep_score(int(float(deep)), int(float(rem)), total),
                    })
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["date"])


def parse_steps(paths: list[Path]) -> list[dict]:
    """步数 CSV: 日期 + 步数。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = _parse_date(row)
                    steps = _find_value(row, ["步数", "steps", "step_count", "value"])
                    if steps and d:
                        records.append({"date": d, "steps": int(float(steps))})
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["date"])


def parse_exercise(paths: list[Path]) -> list[dict]:
    """运动记录 CSV。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    start = _find_value(row, ["开始时间", "start_time", "start"])
                    end = _find_value(row, ["结束时间", "end_time", "end"])
                    etype = _find_value(row, ["运动类型", "type", "exercise_type"]) or "未知"
                    cal = _find_value(row, ["卡路里", "calories", "calorie"]) or 0
                    avg_hr = _find_value(row, ["平均心率", "avg_heart_rate", "avg_hr"])
                    duration = _find_value(row, ["时长", "duration", "duration_min"])
                    records.append({
                        "start": start or "",
                        "end": end or "",
                        "type": etype,
                        "calories": int(float(cal)) if cal else 0,
                        "avg_hr": int(float(avg_hr)) if avg_hr else None,
                        "duration_min": int(float(duration)) if duration else None,
                    })
                except (ValueError, KeyError):
                    continue
    return records


def parse_spo2(paths: list[Path]) -> list[dict]:
    """血氧 CSV。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = _parse_time(row)
                    spo2 = _find_value(row, ["血氧", "spo2", "SpO2", "value"])
                    if spo2 and ts:
                        records.append({"ts": ts, "spo2": int(float(spo2))})
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["ts"])


def parse_stress(paths: list[Path]) -> list[dict]:
    """压力 CSV。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = _parse_time(row)
                    level = _find_value(row, ["压力等级", "stress_level", "stress", "level", "value"])
                    if level and ts:
                        records.append({"ts": ts, "level": int(float(level))})
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["ts"])


def parse_weight(paths: list[Path]) -> list[dict]:
    """体重/体成分 CSV。"""
    records = []
    for p in paths:
        with open(p, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    d = _parse_date(row)
                    weight = _find_value(row, ["体重", "weight", "weight_kg"])
                    bmi = _find_value(row, ["BMI", "bmi"])
                    bodyfat = _find_value(row, ["体脂率", "body_fat", "bodyfat", "fat_rate"])
                    records.append({
                        "date": d,
                        "weight_kg": float(weight) if weight else None,
                        "bmi": float(bmi) if bmi else None,
                        "bodyfat_pct": float(bodyfat) if bodyfat else None,
                    })
                except (ValueError, KeyError):
                    continue
    return sorted(records, key=lambda r: r["date"])


# === 辅助函数 ===

def _parse_time(row: dict) -> str | None:
    for key in ["时间", "time", "timestamp", "ts", "date_time"]:
        if key in row and row[key]:
            return row[key].strip()
    # 尝试第一列
    for v in row.values():
        if v and ("-" in v or ":" in v or "T" in v):
            return v.strip()
    return None


def _parse_date(row: dict) -> str | None:
    for key in ["日期", "date", "day"]:
        if key in row and row[key]:
            return row[key].strip()[:10]
    # 尝试从时间列提取日期
    ts = _parse_time(row)
    if ts:
        return ts[:10]
    return None


def _find_value(row: dict, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in row and row[c]:
            return row[c].strip()
    return None


def _sleep_score(deep_min: int, rem_min: int, total_min: int) -> int:
    """简单睡眠评分 (0-100)。"""
    if total_min == 0:
        return 0
    score = 50  # baseline
    # 时长
    if total_min >= 480:
        score += 20
    elif total_min >= 420:
        score += 10
    elif total_min < 360:
        score -= 20
    # 深睡比例
    deep_pct = deep_min / total_min
    if deep_pct >= 0.25:
        score += 15
    elif deep_pct >= 0.15:
        score += 5
    else:
        score -= 10
    # REM 比例
    rem_pct = rem_min / total_min
    if 0.18 <= rem_pct <= 0.30:
        score += 15
    elif rem_pct < 0.10:
        score -= 10
    return max(0, min(100, score))


# === 主入口 ===

PARSERS = {
    "heart_rate": parse_heart_rate,
    "sleep": parse_sleep,
    "steps": parse_steps,
    "exercise": parse_exercise,
    "spo2": parse_spo2,
    "stress": parse_stress,
    "weight": parse_weight,
}


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 health/import_health.py <export_dir>")
        print("Example: python3 health/import_health.py health/data/export_20260530/")
        sys.exit(1)

    export_dir = Path(sys.argv[1])
    if not export_dir.exists():
        print(f"ERROR: {export_dir} not found")
        sys.exit(1)

    csv_files = find_csv_files(export_dir)
    print(f"Found {sum(len(v) for v in csv_files.values())} CSV files in {len(csv_files)} categories\n")

    all_data: dict[str, list[dict]] = {}
    for cat, parser in PARSERS.items():
        if cat in csv_files:
            try:
                records = parser(csv_files[cat])
                print(f"  {cat}: {len(records)} records parsed")
                all_data[cat] = records
            except Exception as e:
                print(f"  {cat}: PARSE ERROR - {e}")
        else:
            print(f"  {cat}: no data")

    if "unknown" in csv_files and csv_files["unknown"]:
        print(f"\n  unknown ({len(csv_files['unknown'])} files):")
        for f in csv_files["unknown"]:
            print(f"    - {f.name}")

    # 输出标准化 JSON
    out_dir = Path("health/data")
    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / "health_data.json"
    with open(out_path, "w") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n→ 写入 {out_path}")
    print(f"→ 运行 task health:summary 生成摘要")


if __name__ == "__main__":
    main()
