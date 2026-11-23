import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from productpulse.models import SessionRecord


SESSION_COOKIE = "__Host-productpulse_session"
PRELOGIN_CSRF_COOKIE = "__Host-productpulse_prelogin_csrf"
IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_text(value: datetime | None = None) -> str:
    point = value or utc_now()
    return point.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def bearer_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_session(user_id: str, now: datetime | None = None) -> tuple[SessionRecord, str, str]:
    created = now or utc_now()
    bearer = secrets.token_urlsafe(32)
    session = SessionRecord(
        session_id=secrets.token_urlsafe(18),
        user_id=user_id,
        token_hash=bearer_hash(bearer),
        created_at=utc_text(created),
        expires_at=utc_text(created + timedelta(seconds=ABSOLUTE_SECONDS)),
        last_seen_at=utc_text(created),
        revoked_at=None,
    )
    return session, bearer, session_csrf(bearer)


def session_csrf(bearer: str) -> str:
    value = hmac.new(bearer.encode("ascii"), b"productpulse-session-csrf-v1", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def valid_session_csrf(bearer: str, supplied: str | None) -> bool:
    return supplied is not None and hmac.compare_digest(session_csrf(bearer), supplied)


def session_cookie_lifetime(session: SessionRecord, now: datetime | None = None) -> tuple[int, datetime]:
    point = now or utc_now()
    absolute_deadline = parse_utc(session.expires_at)
    last_active = parse_utc(session.last_seen_at or session.created_at)
    deadline = min(last_active + timedelta(seconds=IDLE_SECONDS), absolute_deadline)
    return max(1, int((deadline - point).total_seconds())), deadline


def set_session_cookie(response, bearer: str, session: SessionRecord, now: datetime | None = None) -> None:
    max_age, expires = session_cookie_lifetime(session, now)
    response.set_cookie(
        SESSION_COOKIE,
        bearer,
        max_age=max_age,
        expires=expires,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )

