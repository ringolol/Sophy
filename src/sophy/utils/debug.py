import logging
import os

is_debug = bool(os.environ.get("DEBUG", ""))

_logger = logging.getLogger("sophy")
_initialized = False


def _ensure_logger():
    global _initialized
    if _initialized:
        return
    _initialized = True

    _logger.setLevel(logging.DEBUG)

    # File handler — always active, writes to logs/sophy.log
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(os.path.join(log_dir, "sophy.log"), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    _logger.addHandler(file_handler)

    # Console handler — only when DEBUG=1
    if is_debug:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        console_handler.setFormatter(_DebugFormatter())
        _logger.addHandler(console_handler)


class _DebugFormatter(logging.Formatter):
    """Replicate the original print_debug format for console output."""

    def format(self, record: logging.LogRecord) -> str:
        # Extract the child logger name (e.g. "sophy.TG INPUT" -> "TG INPUT")
        name = record.name
        if name.startswith("sophy."):
            name = name[len("sophy."):]

        header = f"=== DEBUG {name} ===" if name else "=== DEBUG ==="
        return f"{header}\n{record.getMessage()}\n{'=' * len(header)}"


def get_logger(name: str = "") -> logging.Logger:
    _ensure_logger()
    if name:
        return _logger.getChild(name)
    return _logger


def print_debug(*args, debug_name: str = "", **kwargs):
    _ensure_logger()

    parts = [str(a) for a in args]
    message = " ".join(parts)

    logger_name = debug_name or "DEBUG"
    child = _logger.getChild(logger_name)
    child.debug(message)
