import json
import logging
import os
from datetime import datetime, date
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Pricing per million tokens (prompt, completion) in USD
MODEL_RATES = {
    # Gemini 3.5 / 2.5 Flash Lite
    "gemini-3.5-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
    "gemini-3.1-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
    "gemini-2.5-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
    "gemini-2.0-flash-lite": {"prompt_per_m": 0.075, "completion_per_m": 0.30},
    "gemini-flash-latest": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-3.8-flash": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-3.6-flash": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-2.0-flash-exp": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
    "gemini-3.1-pro-preview": {"prompt_per_m": 1.25, "completion_per_m": 5.00},
    "gemini-1.5-pro": {"prompt_per_m": 1.25, "completion_per_m": 5.00},
    "gemini-4-argon": {"prompt_per_m": 1.25, "completion_per_m": 5.00},
    # Default fallback
    "default": {"prompt_per_m": 0.15, "completion_per_m": 0.60},
}


def _get_metrics_file() -> Path:
    """Return an accessible path for storing cost metrics in ~/.codeiq/metrics."""
    target_dir = Path.home() / ".codeiq" / "metrics"
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / "usage_data.js"
    except Exception:
        # Fallback to local project directory if home directory is not writable
        return Path.cwd() / "usage_data.js"


METRICS_FILE = _get_metrics_file()


def calculate_cost(model_name: str, prompt_tokens: int, completion_tokens: int) -> float:
    """
    Calculate the estimated cost in USD for a given model and token count.

    Args:
        model_name: Model identifier string.
        prompt_tokens: Number of prompt/query tokens.
        completion_tokens: Number of completion/output tokens.

    Returns:
        float: Estimated cost in USD rounded to 6 decimal places.
    """
    rates = MODEL_RATES.get(model_name)
    if not rates:
        for k, v in MODEL_RATES.items():
            if k in model_name or model_name in k:
                rates = v
                break
    if not rates:
        rates = MODEL_RATES["default"]

    prompt_cost = (prompt_tokens / 1_000_000.0) * rates["prompt_per_m"]
    comp_cost = (completion_tokens / 1_000_000.0) * rates["completion_per_m"]
    return round(prompt_cost + comp_cost, 6)


def load_cost_metrics() -> Dict[str, Any]:
    """
    Load metrics directly from usage_data.js.

    Returns:
        Dict: Metrics dictionary containing summary, daily_metrics, and logs.
    """
    global METRICS_FILE
    if not METRICS_FILE.parent.exists():
        METRICS_FILE = _get_metrics_file()

    if METRICS_FILE.exists():
        try:
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            # Extract JSON object from window.USAGE_DATA = { ... };
            idx_start = content.find("{")
            idx_end = content.rfind("}")
            if idx_start != -1 and idx_end != -1:
                usage_data = json.loads(content[idx_start : idx_end + 1])
                summary = usage_data.get("_summary", {})
                logs = usage_data.get("_logs", [])
                updated_at = usage_data.get("_updated_at", datetime.now().isoformat())

                # Reconstruct daily_metrics
                daily_metrics: Dict[str, Any] = {}
                for k, v in usage_data.items():
                    if k.startswith("_") or not isinstance(v, dict):
                        continue
                    daily_metrics[k] = {}
                    for model_name, stats in v.items():
                        daily_metrics[k][model_name] = {
                            "prompt_tokens": stats.get("prompt_tokens", 0),
                            "completion_tokens": stats.get("completion_tokens", 0),
                            "total_tokens": stats.get("tokens", stats.get("total_tokens", 0)),
                            "cost_usd": stats.get("cost", stats.get("cost_usd", 0.0)),
                            "turns": stats.get("requests", stats.get("turns", 0)),
                        }

                return {
                    "updated_at": updated_at,
                    "summary": summary,
                    "daily_metrics": daily_metrics,
                    "logs": logs,
                }
        except Exception as exc:
            logger.debug("Failed to read usage_data.js: %s", exc)

    return {
        "updated_at": datetime.now().isoformat(),
        "summary": {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "total_turns": 0,
        },
        "daily_metrics": {},
        "logs": [],
    }


def _percentile(values: List[float], pct: float) -> float:
    """Calculate the percentile value from an unsorted or sorted list of floats."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    return round(sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f]), 3)


def record_cost_metric(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    session_id: Optional[str] = None,
    call_type: Optional[str] = None,
    ttft: Optional[float] = None,
    total_latency: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Record an LLM usage turn into the metrics store.
    Tracks model, date, prompt tokens, completion tokens, total tokens, USD cost,
    latency, TTFT, and optional call type.

    Args:
        model_name: Identifier of the LLM model used.
        prompt_tokens: Prompt tokens for this turn.
        completion_tokens: Completion tokens for this turn.
        session_id: Session ID where the interaction occurred.
        call_type: Optional label indicating the operation type.
        ttft: Time to first token in seconds.
        total_latency: Total request duration in seconds.

    Returns:
        Dict: Updated turn record including calculated cost and latency.
    """
    global METRICS_FILE
    model_name = model_name or "unknown"
    turn_total_tokens = prompt_tokens + completion_tokens
    turn_cost = calculate_cost(model_name, prompt_tokens, completion_tokens)
    today_str = date.today().isoformat()
    now_iso = datetime.now().isoformat()

    metrics = load_cost_metrics()

    # Update summary totals
    summary = metrics.setdefault("summary", {})
    summary["total_prompt_tokens"] = summary.get("total_prompt_tokens", 0) + prompt_tokens
    summary["total_completion_tokens"] = summary.get("total_completion_tokens", 0) + completion_tokens
    summary["total_tokens"] = summary.get("total_tokens", 0) + turn_total_tokens
    summary["total_cost_usd"] = round(summary.get("total_cost_usd", 0.0) + turn_cost, 6)
    summary["total_turns"] = summary.get("total_turns", 0) + 1

    # Update daily breakdown by date & model
    daily = metrics.setdefault("daily_metrics", {})
    day_entry = daily.setdefault(today_str, {})
    model_entry = day_entry.setdefault(
        model_name,
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "turns": 0,
        },
    )

    model_entry["prompt_tokens"] += prompt_tokens
    model_entry["completion_tokens"] += completion_tokens
    model_entry["total_tokens"] += turn_total_tokens
    model_entry["cost_usd"] = round(model_entry["cost_usd"] + turn_cost, 6)
    model_entry["turns"] += 1

    # Append to detailed log (keep recent 1,000 entries)
    record = {
        "timestamp": now_iso,
        "date": today_str,
        "session_id": session_id or "",
        "call_type": call_type or "chat_turn",
        "model": model_name,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": turn_total_tokens,
        "cost_usd": turn_cost,
    }
    if ttft is not None:
        record["ttft"] = round(ttft, 3)
    if total_latency is not None:
        record["total_latency"] = round(total_latency, 3)

    logs = metrics.setdefault("logs", [])
    logs.append(record)
    if len(logs) > 1000:
        metrics["logs"] = logs[-1000:]

    metrics["updated_at"] = now_iso

    # Persist directly into usage_data.js in ~/.codeiq/metrics
    _export_usage_data_js(metrics)

    return record


def _export_usage_data_js(metrics: Dict[str, Any]) -> None:
    """
    Export metrics to usage_data.js strictly in the Path.home() / .codeiq / metrics
    directory. Includes P50, P95, and TTFT telemetry calculations.
    """
    try:
        daily = metrics.get("daily_metrics", {})
        logs = metrics.get("logs", [])

        # Overall latency and TTFT percentiles
        all_lats = [l["total_latency"] for l in logs if "total_latency" in l]
        all_ttfts = [l["ttft"] for l in logs if "ttft" in l]

        summary = dict(metrics.get("summary", {}))
        summary["p50_latency"] = _percentile(all_lats, 0.50)
        summary["p95_latency"] = _percentile(all_lats, 0.95)
        summary["avg_ttft"] = round(sum(all_ttfts) / len(all_ttfts), 3) if all_ttfts else 0.0
        summary["p95_ttft"] = _percentile(all_ttfts, 0.95)

        usage_data: Dict[str, Any] = {}
        for d, models_dict in daily.items():
            usage_data[d] = {}
            for m, vals in models_dict.items():
                m_logs = [l for l in logs if l.get("date") == d and l.get("model") == m]
                m_lats = [l["total_latency"] for l in m_logs if "total_latency" in l]
                m_ttfts = [l["ttft"] for l in m_logs if "ttft" in l]

                usage_data[d][m] = {
                    "prompt_tokens": vals.get("prompt_tokens", 0),
                    "completion_tokens": vals.get("completion_tokens", 0),
                    "tokens": vals.get("total_tokens", vals.get("prompt_tokens", 0) + vals.get("completion_tokens", 0)),
                    "requests": vals.get("turns", 0),
                    "cost": vals.get("cost_usd", 0.0),
                    "p50_latency": _percentile(m_lats, 0.50),
                    "p95_latency": _percentile(m_lats, 0.95),
                    "avg_ttft": round(sum(m_ttfts) / len(m_ttfts), 3) if m_ttfts else 0.0,
                    "p95_ttft": _percentile(m_ttfts, 0.95),
                }

        usage_data["_summary"] = summary
        usage_data["_logs"] = logs
        usage_data["_updated_at"] = metrics.get("updated_at", "")

        js_content = f"window.USAGE_DATA = {json.dumps(usage_data, indent=2, ensure_ascii=False)};\n"

        target_dir = Path.home() / ".codeiq" / "metrics"
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            metrics_js = target_dir / "usage_data.js"
            with open(metrics_js, "w", encoding="utf-8") as f:
                f.write(js_content)
        except Exception as dir_err:
            logger.debug("Could not write usage_data.js to %s: %s", target_dir, dir_err)
    except Exception as exc:
        logger.debug("Could not write usage_data.js: %s", exc)
