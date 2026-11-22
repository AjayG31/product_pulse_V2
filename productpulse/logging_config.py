import logging
import re


_SENSITIVE_FIELD = re.compile(
    r"(?i)(\b(?:api[_ -]?key|password|passwd|token|secret|feedback|"
    r"review_text|return_text|prompt|authorization)\b\s*[=:]\s*)[^\r\n]*"
)
_BEARER_TOKEN = re.compile(r"(?i)(\bbearer\s+)\S+")
_OPENAI_KEY = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")


class RedactingFilter(logging.Filter):
    """Redact common sensitive values before a log record is emitted."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            message = "[REDACTED: invalid log record]"
        message = _SENSITIVE_FIELD.sub(r"\1[REDACTED]", message)
        message = _BEARER_TOKEN.sub(r"\1[REDACTED]", message)
        message = _OPENAI_KEY.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        root_logger.addHandler(handler)
    for handler in root_logger.handlers:
        if not any(isinstance(item, RedactingFilter) for item in handler.filters):
            handler.addFilter(RedactingFilter())
    root_logger.setLevel(logging.INFO)

