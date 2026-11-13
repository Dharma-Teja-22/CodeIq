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


def record_cost_metric(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    session_id: Optional[str] = None,
    call_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record an LLM usage turn into the metrics store.
    Tracks model, date, prompt tokens, completion tokens, total tokens, USD cost,
    and optional call type (e.g. 'chat_turn', 'tool_turn', 'title_generation', 'commit_generation').

    Args:
        model_name: Identifier of the LLM model used.
        prompt_tokens: Prompt tokens for this turn.
        completion_tokens: Completion tokens for this turn.
        session_id: Session ID where the interaction occurred.
        call_type: Optional label indicating the operation type.

    Returns:
        Dict: Updated turn record including calculated cost.
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
    directory. Never write usage_data.js into the local workspace/repository.
    """
    try:
        # Convert daily_metrics structure to match USAGE_DATA format:
        # window.USAGE_DATA = {
        #   "2026-09-25": {
        #     "google/gemini-3.7-flash": {
        #       "prompt_tokens": 536494,
        #       "completion_tokens": 1387,
        #       "tokens": 537881,
        #       "requests": 7,
        #       "cost": 0.407571
        #     }
        #   }
        # }
        daily = metrics.get("daily_metrics", {})
        usage_data: Dict[str, Any] = {}
        for d, models_dict in daily.items():
            usage_data[d] = {}
            for m, vals in models_dict.items():
                usage_data[d][m] = {
                    "prompt_tokens": vals.get("prompt_tokens", 0),
                    "completion_tokens": vals.get("completion_tokens", 0),
                    "tokens": vals.get("total_tokens", vals.get("prompt_tokens", 0) + vals.get("completion_tokens", 0)),
                    "requests": vals.get("turns", 0),
                    "cost": vals.get("cost_usd", 0.0),
                }

        # Include summary and logs metadata as extra properties on window.USAGE_DATA
        usage_data["_summary"] = metrics.get("summary", {})
        usage_data["_logs"] = metrics.get("logs", [])
        usage_data["_updated_at"] = metrics.get("updated_at", "")

        js_content = f"window.USAGE_DATA = {json.dumps(usage_data, indent=2, ensure_ascii=False)};\n"

        # Strictly target ~/.codeiq/metrics directory
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
