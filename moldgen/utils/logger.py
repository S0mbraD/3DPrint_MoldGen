"""日志配置 — 控制台 + 文件滚动 + JSON 结构化"""

import logging
import logging.handlers
import sys
from pathlib import Path


_LOG_DIR = Path("data/logs")
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 5
_CONSOLE_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)s:%(lineno)d | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on reload
    for h in root.handlers[:]:
        root.removeHandler(h)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))
    root.addHandler(console)

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "moldgen.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_DATE_FMT))
    root.addHandler(file_handler)

    err_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "moldgen-error.log",
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_DATE_FMT))
    root.addHandler(err_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_recent_logs(n: int = 200) -> list[str]:
    """Return the last *n* lines from the main log file."""
    log_file = _LOG_DIR / "moldgen.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]


def get_recent_errors(n: int = 100) -> list[str]:
    """Return the last *n* lines from the error log file."""
    log_file = _LOG_DIR / "moldgen-error.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-n:]
