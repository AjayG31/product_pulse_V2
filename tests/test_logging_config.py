import logging

from productpulse.logging_config import RedactingFilter


def test_log_filter_redacts_secret_and_feedback_fields():
    api_key = "sk-test-0123456789abcdef0123456789"
    raw_feedback = "private synthetic review text"
    record = logging.LogRecord(
        "productpulse.test",
        logging.INFO,
        __file__,
        1,
        "api_key=%s feedback=%s request_id=%s",
        (api_key, raw_feedback, "req-123"),
        None,
    )

    assert RedactingFilter().filter(record) is True
    emitted = record.getMessage()
    assert api_key not in emitted
    assert raw_feedback not in emitted
    assert "[REDACTED]" in emitted


def test_log_filter_redacts_bearer_credentials():
    token = "token-that-must-not-leak"
    record = logging.LogRecord(
        "productpulse.test", logging.INFO, __file__, 1, "Authorization: Bearer %s", (token,), None
    )

    RedactingFilter().filter(record)

    assert token not in record.getMessage()

