import logging
from typing import Optional, Dict, Any
from codeiq_dev.core.settings import (
    OPIK_API_KEY,
    OPIK_WORKSPACE,
    OPIK_PROJECT_NAME,
    OPIK_URL_OVERRIDE,
)

logger = logging.getLogger(__name__)

_opik_client = None
_opik_enabled = False

def init_opik() -> bool:
    """
    Initializes Opik client and configuration if credentials/settings are present.
    Returns True if Opik is configured and active, False otherwise.
    """
    global _opik_client, _opik_enabled
    if _opik_enabled and _opik_client is not None:
        return True

    try:
        import opik
        from opik.config import OpikConfig

        # Check if local override or API key is set
        if OPIK_URL_OVERRIDE:
            opik.configure(url_override=OPIK_URL_OVERRIDE, project_name=OPIK_PROJECT_NAME)
        elif OPIK_API_KEY:
            opik.configure(
                api_key=OPIK_API_KEY,
                workspace=OPIK_WORKSPACE,
                project_name=OPIK_PROJECT_NAME,
            )

        _opik_client = opik.Opik(project_name=OPIK_PROJECT_NAME)
        _opik_enabled = True
        return True
    except Exception as exc:
        logger.debug(f"Opik initialization skipped or failed: {exc}")
        _opik_enabled = False
        return False

def get_opik_client():
    """Returns the initialized Opik client instance or None."""
    if not _opik_enabled:
        init_opik()
    return _opik_client

def is_opik_enabled() -> bool:
    """Check if Opik is enabled."""
    return _opik_enabled
