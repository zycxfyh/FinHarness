"""Market cockpit: one-screen visibility over watchlist evidence.

TradingView is useful because the operator can see chart state, indicator
state, alerts, and broken assumptions in one place. FinHarness does not need to
copy TradingView; it needs the same low-friction visibility over its evidence
stack. This module aggregates the existing market-data, indicator, validation,
receipt-audit, and review-queue surfaces into a read-only cockpit.

The cockpit is evidence aggregation only. It never authorizes orders, position
changes, or execution permission.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from finharness.indicator_graph import run_indicator_graph
from finharness.market_data import ROOT, display_path
from finharness.market_data_graph import run_market_data_graph
from finharness.metrics import METRICS_BACKEND, summarize
from finharness.receipt_usage_audit import build_receipt_usage_audit

WORKFLOW_VERSION = "finharness_market_cockpit_v1"
COCKPIT_RECEIPT = ROOT / "data" / "receipts" / "market-cockpit" / "latest.json"
COCKPIT_REPORT = ROOT / "docs" / "operations" / "market-cockpit-latest.md"


def _now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_symbols(symbols: str | list[str]) -> list[str]:
    raw = symbols.split(",") if isinstance(symbols, str) else symbols
    return [symbol.strip().upper() for symbol in raw if symbol.strip()]


def _history_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(row["close"]) for row in records if row.get("close") is not None]
    if len(closes) < 2:
        return {"ok": False, "reason": "fewer than two closes"}
    summary = summarize(closes)
    return {
        "ok": True,
        "backend": METRICS_BACKEND,
        "total_return": summary.total_return,
        "annualized_return": summary.annualized_return,
        "annualized_volatility": summary.annualized_volatility,
        "max_drawdown": summary.max_drawdown,
        "sharpe_ratio": summary.sharpe_ratio,
    }


def _latest_date(records: list[dict[str, Any]]) -> str | None:
    if not records:
        return None
    return str(records[-1].get("date"))


def _freshness(latest: str | None) -> dict[str, Any]:
    if not latest:
        return {"status": "missing", "age_days": None}
    try:
        latest_date = datetime.fromisoformat(latest.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            latest_date = date.fromisoformat(latest.split(" ")[0])
        except ValueError:
            return {"status": "unknown", "age_days": None}
    age_days = (datetime.now(UTC).date() - latest_date).days
    if age_days <= 3:
        status = "fresh"
    elif age_days <= 7:
        status = "aging"
    else:
        status = "stale"
    return {"status": status, "age_days": age_days}


def _load_latest_json(directory: Path, pattern: str) -> tuple[Path | None, dict[str, Any] | None]:
    matches = sorted(directory.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in matches:
        try:
            return path, json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None, None


def _latest_hypothesis_status(symbol: str, *, root: Path) -> dict[str, Any]:
    path, payload = _load_latest_json(root / "data" / "normalized" / "hypotheses", "hyps_*.json")
    if payload is None or path is None:
        return {"status": "missing", "record_count": 0, "payload_ref": None}
    universe = [str(item).upper() for item in payload.get("universe", [])]
    records = payload.get("records") or []
    if symbol not in universe:
        status = "not_in_latest_universe"
    elif not records:
        status = "zero_records"
    else:
        status = "records_available"
    return {
        "status": status,
        "record_count": len(records),
        "payload_ref": display_path(path),
        "snapshot_id": payload.get("hypothesis_snapshot_id"),
    }


def _latest_validation_status(symbol: str, *, root: Path) -> dict[str, Any]:
    path, payload = _load_latest_json(root / "data" / "normalized" / "validations", "vals_*.json")
    if payload is None or path is None:
        return {"status": "missing", "job_count": 0, "result_count": 0, "payload_ref": None}
    universe = [str(item).upper() for item in payload.get("universe", [])]
    jobs = payload.get("jobs") or []
    results = payload.get("results") or []
    if symbol not in universe:
        status = "not_in_latest_universe"
    elif not jobs and not results:
        status = "zero_results"
    elif jobs and not results:
        status = "jobs_without_results"
    else:
        status = "results_available"
    return {
        "status": status,
        "job_count": len(jobs),
        "result_count": len(results),
        "payload_ref": display_path(path),
        "snapshot_id": payload.get("validation_snapshot_id"),
    }


def _review_queue(*, root: Path, limit: int = 12) -> list[dict[str, str]]:
    queue: list[dict[str, str]] = []
    for path in sorted(
        (root / "docs" / "reviews").glob("*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        status_line = next((line for line in text.splitlines() if line.startswith("Status:")), "")
        if any(token in text for token in ["Status: warning", "Status: DEGRADED", "review_only"]):
            queue.append(
                {
                    "path": display_path(path),
                    "status": status_line.replace("Status:", "").strip() or "review_only",
                }
            )
        if len(queue) >= limit:
            break
    return queue


def _receipt_surface(*, root: Path) -> dict[str, Any]:
    try:
        audit = build_receipt_usage_audit(root=root)
    except Exception as exc:  # pragma: no cover - defensive summary path
        return {"status": "error", "error": str(exc)}
    return {
        "status": "ok",
        "summary": audit["summary"],
    }


def _next_action(issues: list[str]) -> str:
    if any(issue.startswith("market_data_error") for issue in issues):
        return "investigate_market_data"
    if any(issue.startswith("indicator_error") for issue in issues):
        return "investigate_indicators"
    if "validation_zero_results" in issues or "hypothesis_zero_records" in issues:
        return "review_only_build_hypothesis"
    if issues:
        return "review_only_investigate"
    return "review_only"


def _degraded_path_label(note: str) -> str:
    if "nautilus catalog write skipped" in note:
        return "market_data:nautilus_catalog_overlap_skipped"
    return f"market_data:{note}"


def _symbol_cockpit(
    symbol: str,
    *,
    root: Path,
    start: str,
    end: str,
    ma_fast: int,
    ma_slow: int,
) -> dict[str, Any]:
    issues: list[str] = []
    degraded_paths: list[str] = []
    market: dict[str, Any] | None = None
    indicator: dict[str, Any] | None = None
    records: list[dict[str, Any]] = []
    features: dict[str, Any] = {}

    try:
        market = run_market_data_graph(
            symbol=symbol,
            start=start,
            end=end,
            write_catalog=True,
        )
        records = market.get("normalized_records", [])
        notes = market["final"].get("quality_notes", [])
        if notes:
            degraded_paths.extend(_degraded_path_label(note) for note in notes)
        if not market["final"].get("quality_ok", False):
            issues.append("market_data_quality_failed")
    except Exception as exc:
        issues.append(f"market_data_error:{exc}")

    if market is not None and records:
        try:
            indicator = run_indicator_graph(
                symbol=symbol,
                start=start,
                end=end,
                ma_fast=ma_fast,
                ma_slow=ma_slow,
                market_data_snapshot=market["snapshot"],
                history_records=records,
            )
            features = indicator.get("features", {}).get("latest", {})
            if not indicator["final"].get("quality_ok", False):
                issues.append("indicator_quality_failed")
        except Exception as exc:
            issues.append(f"indicator_error:{exc}")

    hypothesis_status = _latest_hypothesis_status(symbol, root=root)
    validation_status = _latest_validation_status(symbol, root=root)
    if hypothesis_status["status"] == "zero_records":
        issues.append("hypothesis_zero_records")
    if validation_status["status"] == "zero_results":
        issues.append("validation_zero_results")

    latest = _latest_date(records)
    return {
        "symbol": symbol,
        "market_data": {
            "ok": market is not None and market["final"].get("quality_ok", False),
            "row_count": market["final"].get("row_count") if market else 0,
            "latest_date": latest,
            "freshness": _freshness(latest),
            "payload_ref": market["final"].get("payload_ref") if market else None,
            "receipt_ref": market["final"].get("receipt_ref") if market else None,
        },
        "risk_return": _history_metrics(records),
        "indicators": {
            "ok": indicator is not None and indicator["final"].get("quality_ok", False),
            "latest_date": features.get("date") or latest,
            "ma_trend": features.get("ma_trend"),
            "rsi": features.get("rsi"),
            "rsi_state": features.get("rsi_state"),
            "macd_bias": features.get("macd_bias"),
            "macd_hist": features.get("macd_hist"),
            "rolling_volatility_20d_annualized": features.get(
                "rolling_volatility_20d_annualized"
            ),
            "payload_ref": indicator["final"].get("payload_ref") if indicator else None,
            "receipt_ref": indicator["final"].get("receipt_ref") if indicator else None,
        },
        "hypothesis": hypothesis_status,
        "validation": validation_status,
        "issues": issues,
        "degraded_paths": degraded_paths,
        "next_action": _next_action(issues),
    }


def build_market_cockpit(
    *,
    symbols: str | list[str] = "SPY,QQQ,NVDA",
    start: str = "2025-01-01",
    end: str = "2026-06-13",
    ma_fast: int = 20,
    ma_slow: int = 50,
    root: Path = ROOT,
) -> dict[str, Any]:
    parsed_symbols = _parse_symbols(symbols)
    symbol_rows = [
        _symbol_cockpit(
            symbol,
            root=root,
            start=start,
            end=end,
            ma_fast=ma_fast,
            ma_slow=ma_slow,
        )
        for symbol in parsed_symbols
    ]
    receipt_surface = _receipt_surface(root=root)
    review_queue = _review_queue(root=root)
    broken_paths = [
        {"symbol": row["symbol"], "issue": issue}
        for row in symbol_rows
        for issue in row["issues"]
    ]
    degraded_paths = [
        {"symbol": row["symbol"], "path": path}
        for row in symbol_rows
        for path in row["degraded_paths"]
    ]
    if receipt_surface.get("summary", {}).get("missing_reference_count", 0):
        broken_paths.append(
            {
                "symbol": "repo",
                "issue": (
                    "receipt_missing_references:"
                    f"{receipt_surface['summary']['missing_reference_count']}"
                ),
            }
        )
    return {
        "workflow": WORKFLOW_VERSION,
        "generated_at": _now_utc(),
        "source": {
            "workflow": WORKFLOW_VERSION,
            "execution_allowed": False,
            "authority_boundary": (
                "This cockpit aggregates market evidence and review work. It "
                "does not produce orders, position changes, execution "
                "permission, or investment advice."
            ),
        },
        "config": {
            "symbols": parsed_symbols,
            "start": start,
            "end": end,
            "ma_fast": ma_fast,
            "ma_slow": ma_slow,
        },
        "symbols": symbol_rows,
        "broken_paths": broken_paths,
        "degraded_paths": degraded_paths,
        "review_queue": review_queue,
        "receipt_surface": receipt_surface,
        "execution_allowed": False,
    }


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2%}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_float(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def render_market_cockpit_markdown(cockpit: dict[str, Any]) -> str:
    lines = [
        "# Market Cockpit",
        "",
        f"Generated at: `{cockpit['generated_at']}`",
        f"Execution allowed: `{str(cockpit['execution_allowed']).lower()}`",
        "",
        "## Watchlist",
        "",
        "| Symbol | Latest | Fresh | Return | Max DD | Trend | RSI | MACD | Validation | Next |",
        "|---|---:|---:|---:|---:|---|---:|---|---|---|",
    ]
    for row in cockpit["symbols"]:
        market = row["market_data"]
        risk = row["risk_return"]
        indicators = row["indicators"]
        line = (
            "| {symbol} | {latest} | {fresh} | {ret} | {dd} | {trend} | "
            "{rsi} {rsi_state} | {macd} | {validation} | {next_action} |"
        )
        lines.append(
            line.format(
                symbol=row["symbol"],
                latest=market.get("latest_date") or "n/a",
                fresh=market.get("freshness", {}).get("status", "n/a"),
                ret=_fmt_pct(risk.get("total_return") if risk.get("ok") else None),
                dd=_fmt_pct(risk.get("max_drawdown") if risk.get("ok") else None),
                trend=indicators.get("ma_trend") or "n/a",
                rsi=_fmt_float(indicators.get("rsi")),
                rsi_state=indicators.get("rsi_state") or "",
                macd=indicators.get("macd_bias") or "n/a",
                validation=row["validation"]["status"],
                next_action=row["next_action"],
            )
        )
    lines.extend(["", "## Broken Paths", ""])
    if cockpit["broken_paths"]:
        lines.extend(f"- `{item['symbol']}`: {item['issue']}" for item in cockpit["broken_paths"])
    else:
        lines.append("- No broken paths detected in this cockpit run.")
    lines.extend(["", "## Degraded Paths", ""])
    if cockpit["degraded_paths"]:
        lines.extend(f"- `{item['symbol']}`: {item['path']}" for item in cockpit["degraded_paths"])
    else:
        lines.append("- No degraded paths detected in this cockpit run.")
    lines.extend(["", "## Human Review Queue", ""])
    if cockpit["review_queue"]:
        lines.extend(f"- `{item['status']}`: {item['path']}" for item in cockpit["review_queue"])
    else:
        lines.append("- No open warning/degraded review docs found.")
    summary = cockpit.get("receipt_surface", {}).get("summary", {})
    surface = summary.get("evidence_surface_counts", {})
    lines.extend(
        [
            "",
            "## Receipt Surface",
            "",
            f"- Receipt count: `{summary.get('receipt_count', 'n/a')}`",
            f"- Durable consumed: `{surface.get('durable_consumed', 'n/a')}`",
            f"- Candidate/draft: `{surface.get('candidate_or_draft', 'n/a')}`",
            f"- Runtime/unlinked: `{surface.get('generated_runtime_or_unlinked', 'n/a')}`",
            f"- Missing references: `{summary.get('missing_reference_count', 'n/a')}`",
            "",
            "## Boundary",
            "",
            (
                "This cockpit is review evidence only. It does not authorize "
                "orders, position changes, or live execution."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def write_market_cockpit_outputs(
    cockpit: dict[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, str]:
    receipt_path = root / COCKPIT_RECEIPT.relative_to(ROOT)
    report_path = root / COCKPIT_REPORT.relative_to(ROOT)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(cockpit, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(render_market_cockpit_markdown(cockpit), encoding="utf-8")
    return {"receipt": str(receipt_path), "report": str(report_path)}
