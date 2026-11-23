from dataclasses import dataclass
from datetime import UTC, timedelta
import hmac
import logging
import re
import secrets
from urllib.parse import urlsplit
import uuid

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from productpulse.api_common import ApiError, page_meta, request_id, safe_audit, validate_idempotency_key
from productpulse.api_schemas import (
    CreateUserRequest,
    DeactivateUserRequest,
    LoginRequest,
    LoginResponse,
    PageMeta,
    PasswordChangeRequest,
    PreLoginCsrfResponse,
    PublicUser,
    ResetUserPasswordRequest,
    UserPage,
)
from productpulse.auth_state import LoginThrottle, PreLoginTokens
from productpulse.db_session import get_db
from productpulse.models import AuditEvent, SessionRecord, User
from productpulse.security.identity import EmailIdentityError, normalize_email
from productpulse.security.passwords import PasswordPolicyError, hash_password, password_needs_rehash, validate_password, verify_password
from productpulse.security.sessions import (
    ABSOLUTE_SECONDS,
    IDLE_SECONDS,
    PRELOGIN_CSRF_COOKIE,
    SESSION_COOKIE,
    bearer_hash,
    clear_session_cookie,
    new_session,
    parse_utc,
    set_session_cookie,
    session_csrf,
    utc_now,
    utc_text,
    valid_session_csrf,
)


router = APIRouter()
_SECURITY_LOG = logging.getLogger("productpulse.security.auth")
_EMAIL_SHAPE = re.compile(r"^[^\s@<>]+@[^\s@<>]+$")
_DUMMY_HASH = hash_password("not-a-real-user-password-for-timing-padding", enforce_policy=False)


@dataclass
class AuthContext:
    user: User
    session: SessionRecord
    bearer: str
    db: Session
    request: Request


def _public_user(user: User) -> dict[str, object]:
    return {
        "user_id": user.user_id,
        "email": user.email,
        "role": user.role,
        "status": user.status,
        "must_change_password": bool(user.must_change_password),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    source = origin if origin is not None else request.headers.get("referer")
    if not source:
        return False
    try:
        provided = urlsplit(source)
        expected = urlsplit(str(request.base_url))
        if not provided.scheme or not provided.hostname or not expected.hostname:
            return False
        if provided.username or provided.password:
            return False
        default_port = {"http": 80, "https": 443}
        provided_port = provided.port or default_port.get(provided.scheme.lower())
        expected_port = expected.port or default_port.get(expected.scheme.lower())
        if origin is not None and provided.path not in ("", "/"):
            return False
        return (
            provided.scheme.lower() == expected.scheme.lower()
            and provided.hostname.casefold() == expected.hostname.casefold()
            and provided_port == expected_port
        )
    except ValueError:
        return False


def _check_prelogin_csrf(request: Request, token: str | None) -> None:
    cookie = request.cookies.get(PRELOGIN_CSRF_COOKIE)
    if not token or not cookie or not hmac.compare_digest(token, cookie):
        raise ApiError(403, "CSRF_INVALID", "The request could not be verified.", "Request denied")
    if not _same_origin(request):
        raise ApiError(403, "ORIGIN_INVALID", "The request could not be verified.", "Request denied")
    if not request.app.state.prelogin_tokens.valid(token):
        raise ApiError(403, "CSRF_INVALID", "The request could not be verified.", "Request denied")


def _check_session_csrf(context: AuthContext, token: str | None) -> None:
    if not valid_session_csrf(context.bearer, token):
        raise ApiError(403, "CSRF_INVALID", "The request could not be verified.", "Request denied")


def _rate_limit_error(retry_after: int) -> ApiError:
    return ApiError(
        429,
        "LOGIN_RATE_LIMITED",
        "Sign-in is temporarily unavailable. Try again later.",
        "Too many requests",
        {"Retry-After": str(retry_after), "Cache-Control": "no-store"},
    )


def _candidate_key(email: str) -> str:
    try:
        _, normalized = normalize_email(email)
        return normalized
    except EmailIdentityError:
        return email.strip(" \t\n\r\v\f").casefold()


def _record_authorization_denial(context: AuthContext, action: str) -> None:
    safe_audit(
        context.db,
        action="AUTHORIZATION_DENIED",
        resource_type="ROUTE",
        resource_id=action,
        actor_user_id=context.user.user_id,
        outcome="DENIED",
        after={"role": context.user.role, "credential_change_required": bool(context.user.must_change_password)},
        request_id_value=request_id(context.request),
    )
    context.db.commit()


def get_auth_context(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthContext:
    bearer = request.cookies.get(SESSION_COOKIE)
    if not bearer:
        raise ApiError(401, "UNAUTHENTICATED", "Sign in to continue.", "Authentication required")
    session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(bearer)))
    if session is None or session.revoked_at is not None:
        raise ApiError(401, "SESSION_INVALID", "Sign in to continue.", "Authentication required")
    now = utc_now()
    last_seen = parse_utc(session.last_seen_at or session.created_at)
    absolute_expiry = parse_utc(session.expires_at)
    if now >= absolute_expiry or now >= last_seen + timedelta(seconds=IDLE_SECONDS):
        raise ApiError(401, "SESSION_EXPIRED", "Your session has expired. Sign in again.", "Authentication required")
    user = db.get(User, session.user_id)
    if user is None or user.status != "ACTIVE":
        raise ApiError(401, "SESSION_INVALID", "Sign in to continue.", "Authentication required")
    session.last_seen_at = utc_text(now)
    db.commit()
    set_session_cookie(response, bearer, session, now)
    return AuthContext(user=user, session=session, bearer=bearer, db=db, request=request)


def get_normal_context(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if context.user.must_change_password:
        _record_authorization_denial(context, "NORMAL_APPLICATION_ACCESS")
        raise ApiError(403, "PASSWORD_CHANGE_REQUIRED", "Change your temporary password before continuing.", "Access denied")
    return context


def get_admin_context(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
    if context.user.role != "ADMIN" or context.user.must_change_password:
        _record_authorization_denial(context, "ADMIN_USER_MANAGEMENT")
        raise ApiError(403, "FORBIDDEN", "You do not have permission to perform this action.", "Access denied")
    return context


@router.get("/auth/csrf", response_model=PreLoginCsrfResponse)
def bootstrap_csrf(request: Request, response: Response) -> PreLoginCsrfResponse:
    token = request.app.state.prelogin_tokens.issue()
    response.set_cookie(
        PRELOGIN_CSRF_COOKIE,
        token,
        max_age=600,
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id(request)
    return PreLoginCsrfResponse(csrf_token=token)


@router.post("/auth/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
) -> LoginResponse:
    _check_prelogin_csrf(request, csrf_token)
    candidate = _candidate_key(body.email)
    source_ip = request.client.host if request.client else "unknown"
    retry_after = request.app.state.login_throttle.check(candidate, source_ip)
    if retry_after is not None:
        _SECURITY_LOG.info("event=LOGIN_THROTTLED request_id=%s", request_id(request))
        raise _rate_limit_error(retry_after)

    try:
        _display_email, normalized_email = normalize_email(body.email)
        if not _EMAIL_SHAPE.match(body.email.strip(" \t\n\r\v\f")):
            raise EmailIdentityError("invalid")
    except EmailIdentityError:
        normalized_email = ""
    user = db.scalar(select(User).where(User.email_normalized == normalized_email)) if normalized_email else None
    password_matches = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    if user is None or not password_matches or user.status != "ACTIVE":
        request.app.state.login_throttle.record_attempt(candidate, source_ip, failed=True)
        _SECURITY_LOG.info("event=LOGIN_FAILED request_id=%s", request_id(request))
        raise ApiError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.", "Sign-in failed")

    now = utc_now()
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    session, bearer, csrf = new_session(user.user_id, now)
    db.add(session)
    safe_audit(
        db,
        action="LOGIN_SUCCEEDED",
        resource_type="USER",
        resource_id=user.user_id,
        actor_user_id=user.user_id,
        after={"role": user.role, "status": user.status, "credential_change_required": bool(user.must_change_password)},
        request_id_value=request_id(request),
    )
    db.commit()
    request.app.state.login_throttle.record_attempt(candidate, source_ip, failed=False)
    set_session_cookie(response, bearer, session, now)
    response.delete_cookie(PRELOGIN_CSRF_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id(request)
    return LoginResponse(user=PublicUser(**_public_user(user)), csrf_token=csrf)


@router.get("/auth/session", response_model=LoginResponse)
def get_current_session(context: AuthContext = Depends(get_auth_context)) -> LoginResponse:
    return LoginResponse(
        user=PublicUser(**_public_user(context.user)),
        csrf_token=session_csrf(context.bearer),
    )


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_auth_context),
) -> Response:
    _check_session_csrf(context, csrf_token)
    now = utc_text()
    context.session.revoked_at = now
    safe_audit(
        context.db,
        action="LOGOUT",
        resource_type="SESSION",
        resource_id=context.session.session_id,
        actor_user_id=context.user.user_id,
        request_id_value=request_id(request),
    )
    safe_audit(
        context.db,
        action="SESSION_REVOKED",
        resource_type="USER",
        resource_id=context.user.user_id,
        actor_user_id=context.user.user_id,
        request_id_value=request_id(request),
    )
    context.db.commit()
    clear_session_cookie(response)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id(request)
    response.status_code = 204
    return response


@router.post("/auth/password-change", response_model=LoginResponse)
def change_temporary_password(
    body: PasswordChangeRequest,
    request: Request,
    response: Response,
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_auth_context),
) -> LoginResponse:
    _check_session_csrf(context, csrf_token)
    if not context.user.must_change_password:
        raise ApiError(403, "PASSWORD_CHANGE_NOT_REQUIRED", "This password change is not available.", "Access denied")
    if not verify_password(body.current_password, context.user.password_hash):
        raise ApiError(422, "CURRENT_PASSWORD_INVALID", "The current password is incorrect.", "Validation failed")
    try:
        new_hash = hash_password(body.new_password)
    except PasswordPolicyError as error:
        raise ApiError(422, "PASSWORD_POLICY", str(error), "Validation failed") from error

    now = utc_now()
    context.user.password_hash = new_hash
    context.user.must_change_password = False
    context.user.updated_at = utc_text(now)
    live_sessions = context.db.scalars(
        select(SessionRecord).where(
            SessionRecord.user_id == context.user.user_id,
            SessionRecord.revoked_at.is_(None),
        )
    ).all()
    for record in live_sessions:
        record.revoked_at = utc_text(now)
    new_record, bearer, csrf = new_session(context.user.user_id, now)
    context.db.add(new_record)
    safe_audit(
        context.db,
        action="PASSWORD_CHANGED",
        resource_type="USER",
        resource_id=context.user.user_id,
        actor_user_id=context.user.user_id,
        before={"credential_change_required": True},
        after={"credential_change_required": False},
        request_id_value=request_id(request),
    )
    safe_audit(
        context.db,
        action="SESSION_REVOKED",
        resource_type="USER",
        resource_id=context.user.user_id,
        actor_user_id=context.user.user_id,
        after={"revoked_session_count": len(live_sessions)},
        request_id_value=request_id(request),
    )
    context.db.commit()
    set_session_cookie(response, bearer, new_record, now)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Request-ID"] = request_id(request)
    return LoginResponse(user=PublicUser(**_public_user(context.user)), csrf_token=csrf)


@router.get("/admin/users", response_model=UserPage)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(ACTIVE|DEACTIVATED)$"),
    role_filter: str | None = Query(default=None, alias="role", pattern="^(ADMIN|BUSINESS_USER)$"),
    context: AuthContext = Depends(get_admin_context),
) -> UserPage:
    filters = []
    if status_filter:
        filters.append(User.status == status_filter)
    if role_filter:
        filters.append(User.role == role_filter)
    total = context.db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    users = context.db.scalars(
        select(User).where(*filters).order_by(User.created_at, User.user_id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return UserPage(items=[PublicUser(**_public_user(user)) for user in users], page=PageMeta(**page_meta(page, page_size, total)))


@router.post("/admin/users", response_model=PublicUser, status_code=201)
def create_user(
    body: CreateUserRequest,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> PublicUser:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    try:
        email, email_normalized = normalize_email(body.email)
        if not _EMAIL_SHAPE.match(email):
            raise EmailIdentityError("invalid")
        encoded = hash_password(body.initial_password)
    except EmailIdentityError as error:
        raise ApiError(422, "EMAIL_INVALID", "Enter a valid email address.", "Validation failed") from error
    except PasswordPolicyError as error:
        raise ApiError(422, "PASSWORD_POLICY", str(error), "Validation failed") from error

    db = context.db
    try:
        db.execute(text("BEGIN IMMEDIATE"))
        previous = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "ACCOUNT_CREATED", AuditEvent.request_id == key)
        )
        if previous is not None:
            existing = db.get(User, previous.resource_id) if previous.resource_id else None
            same_request = (
                existing is not None
                and existing.email_normalized == email_normalized
                and existing.role == body.role
                and verify_password(body.initial_password, existing.password_hash)
            )
            db.commit()
            if same_request:
                return PublicUser(**_public_user(existing))
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different request.", "Conflict")
        if db.scalar(select(User.user_id).where(User.email_normalized == email_normalized)) is not None:
            db.rollback()
            raise ApiError(409, "EMAIL_ALREADY_EXISTS", "An account with this email address already exists.", "Conflict")
        now = utc_text()
        user = User(
            user_id=f"usr_{uuid.uuid4().hex}",
            email=email,
            email_normalized=email_normalized,
            password_hash=encoded,
            role=body.role,
            status="ACTIVE",
            must_change_password=True,
            created_at=now,
            updated_at=now,
            deactivated_at=None,
        )
        db.add(user)
        safe_audit(
            db,
            action="ACCOUNT_CREATED",
            resource_type="USER",
            resource_id=user.user_id,
            actor_user_id=context.user.user_id,
            after={"role": user.role, "status": user.status, "credential_change_required": True},
            request_id_value=key,
        )
        db.commit()
        return PublicUser(**_public_user(user))
    except IntegrityError as error:
        db.rollback()
        raise ApiError(409, "EMAIL_ALREADY_EXISTS", "An account with this email address already exists.", "Conflict") from error


@router.get("/admin/users/{user_id}", response_model=PublicUser)
def get_user(user_id: str, context: AuthContext = Depends(get_admin_context)) -> PublicUser:
    user = context.db.get(User, user_id)
    if user is None:
        raise ApiError(404, "USER_NOT_FOUND", "The requested user was not found.", "Not found")
    return PublicUser(**_public_user(user))


@router.patch("/admin/users/{user_id}", response_model=PublicUser)
def deactivate_user(
    user_id: str,
    body: DeactivateUserRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> PublicUser:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    db = context.db
    db.execute(text("BEGIN IMMEDIATE"))
    previous = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "ACCOUNT_DEACTIVATED", AuditEvent.request_id == key)
    )
    if previous is not None:
        user = db.get(User, previous.resource_id) if previous.resource_id else None
        db.commit()
        if user is None or user.user_id != user_id:
            raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different request.", "Conflict")
        return PublicUser(**_public_user(user))
    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        raise ApiError(404, "USER_NOT_FOUND", "The requested user was not found.", "Not found")
    if user.status == "DEACTIVATED":
        db.commit()
        return PublicUser(**_public_user(user))
    now = utc_text()
    before = {"role": user.role, "status": user.status, "credential_change_required": bool(user.must_change_password)}
    user.status = "DEACTIVATED"
    user.deactivated_at = now
    user.updated_at = now
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    safe_audit(
        db,
        action="ACCOUNT_DEACTIVATED",
        resource_type="USER",
        resource_id=user.user_id,
        actor_user_id=context.user.user_id,
        before=before,
        after={"role": user.role, "status": user.status, "credential_change_required": bool(user.must_change_password)},
        request_id_value=key,
    )
    safe_audit(
        db,
        action="SESSION_REVOKED",
        resource_type="USER",
        resource_id=user.user_id,
        actor_user_id=context.user.user_id,
        after={"status": "DEACTIVATED"},
        request_id_value=key,
    )
    db.commit()
    if response is not None and user.user_id == context.user.user_id:
        clear_session_cookie(response)
    return PublicUser(**_public_user(user))


@router.post("/admin/users/{user_id}/password-reset", response_model=PublicUser)
def reset_user_password(
    user_id: str,
    body: ResetUserPasswordRequest,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    context: AuthContext = Depends(get_admin_context),
) -> PublicUser:
    _check_session_csrf(context, csrf_token)
    key = validate_idempotency_key(idempotency_key)
    try:
        encoded = hash_password(body.temporary_password)
    except PasswordPolicyError as error:
        raise ApiError(422, "PASSWORD_POLICY", str(error), "Validation failed") from error
    db = context.db
    db.execute(text("BEGIN IMMEDIATE"))
    previous = db.scalar(select(AuditEvent).where(AuditEvent.action == "PASSWORD_RESET", AuditEvent.request_id == key))
    if previous is not None:
        user = db.get(User, previous.resource_id) if previous.resource_id else None
        same_request = (
            user is not None
            and user.user_id == user_id
            and bool(user.must_change_password)
            and verify_password(body.temporary_password, user.password_hash)
        )
        db.commit()
        if same_request:
            return PublicUser(**_public_user(user))
        raise ApiError(409, "IDEMPOTENCY_CONFLICT", "The Idempotency-Key was already used for a different request.", "Conflict")
    user = db.get(User, user_id)
    if user is None:
        db.rollback()
        raise ApiError(404, "USER_NOT_FOUND", "The requested user was not found.", "Not found")
    now = utc_text()
    before = {"credential_change_required": bool(user.must_change_password), "status": user.status}
    user.password_hash = encoded
    user.must_change_password = True
    user.updated_at = now
    db.execute(
        update(SessionRecord)
        .where(SessionRecord.user_id == user.user_id, SessionRecord.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    safe_audit(
        db,
        action="PASSWORD_RESET",
        resource_type="USER",
        resource_id=user.user_id,
        actor_user_id=context.user.user_id,
        before=before,
        after={"credential_change_required": True, "status": user.status},
        request_id_value=key,
    )
    safe_audit(
        db,
        action="SESSION_REVOKED",
        resource_type="USER",
        resource_id=user.user_id,
        actor_user_id=context.user.user_id,
        after={"credential_change_required": True},
        request_id_value=key,
    )
    db.commit()
    if response is not None and user.user_id == context.user.user_id:
        clear_session_cookie(response)
    return PublicUser(**_public_user(user))

