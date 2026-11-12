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
    """Return an accessible path for storing cost metrics."""
    # First try user home directory: ~/.codeiq/metrics/cost_metrics.json
    try:
        user_dir = Path.home() / ".codeiq" / "metrics"
        user_dir.mkdir(parents=True, exist_ok=True)
        # Test write permission
        test_file = user_dir / ".test_write"
        with open(test_file, "w") as f:
            f.write("ok")
        test_file.unlink()
        return user_dir / "cost_metrics.json"
    except Exception:
        pass
    # Fallback to local project directory: ./cost_metrics.json
    return Path.cwd() / "cost_metrics.json"


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
    Load the cost metrics JSON file.

    Returns:
        Dict: JSON metrics dictionary containing daily aggregation and log records.
    """
    global METRICS_FILE
    if not METRICS_FILE.parent.exists():
        METRICS_FILE = _get_metrics_file()

    if METRICS_FILE.exists():
        try:
            with open(METRICS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.debug("Failed to read metrics file: %s", exc)

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
) -> Dict[str, Any]:
    """
    Record an LLM usage turn into the metrics store.
    Tracks model, date, prompt tokens, completion tokens, total tokens, and USD cost.

    Args:
        model_name: Identifier of the LLM model used.
        prompt_tokens: Prompt tokens for this turn.
        completion_tokens: Completion tokens for this turn.
        session_id: Session ID where the interaction occurred.

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

    try:
        with open(METRICS_FILE, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        # Fallback to local cwd
        fallback_file = Path.cwd() / "cost_metrics.json"
        try:
            with open(fallback_file, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, ensure_ascii=False)
            METRICS_FILE = fallback_file
        except Exception:
            logger.warning("Could not persist cost metrics: %s", exc)

    return record
