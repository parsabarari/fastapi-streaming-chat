import logging
import sys

from app.config import settings


class _SessionIdFilter(logging.Filter):
    """Ensures every log record has a `session_id` attribute so the format
    string below never raises, even for logs emitted outside a chat request.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "session_id"):
            record.session_id = "-"
        return True


def setup_logging() -> None:
    """Configure root logging once at process startup.

    Format includes timestamp, level, logger name, and session_id so that
    request-scoped logs (see services/*) can be correlated per chat session.
    """
    level = logging.DEBUG if settings.environment == "development" else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_SessionIdFilter())
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | session=%(session_id)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)

    # Quiet down noisy third-party loggers unless we're debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
