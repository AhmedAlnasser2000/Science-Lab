from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Optional

_CONFIGURED = False
_HANDLER: Optional[logging.Handler] = None


def configure_logging(base_dir: Optional[Path] = None) -> Dict[str, str]:
    global _CONFIGURED, _HANDLER
    root = base_dir or Path("data/roaming")
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "physicslab.log"

    logger_name = "physicslab" if base_dir is None else "physicslab.test"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if base_dir is None and not _CONFIGURED:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter(
            "ts=%(asctime)s level=%(levelname)s msg=%(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        _HANDLER = handler
        _CONFIGURED = True
    elif base_dir is not None and not logger.handlers:
        handler = logging.FileHandler(log_path, encoding="utf-8")
        formatter = logging.Formatter(
            "ts=%(asctime)s level=%(levelname)s msg=%(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return {
        "log_path": str(log_path),
        "format": "kv",
        "handlers": "file",
        "logger_name": logger_name,
    }


def get_logger() -> logging.Logger:
    return logging.getLogger("physicslab")
