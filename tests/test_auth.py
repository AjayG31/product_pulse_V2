from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from productpulse.api_common import safe_audit
from productpulse import bootstrap_admin
from productpulse.auth_state import LoginThrottle, PreLoginTokens
from productpulse.database import create_database_engine
from productpulse.main import create_app
from productpulse.models import AuditEvent, Base, SessionRecord, User
from productpulse.security.identity import normalize_email
from productpulse.security.passwords import hash_password, validate_password, verify_password
from productpulse.security.sessions import PRELOGIN_CSRF_COOKIE, SESSION_COOKIE, bearer_hash, utc_now, utc_text
from productpulse.settings import Settings


@pytest.fixture
def auth_app(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    app = create_app(settings)
    app.state.database_engine = engine
    yield app, engine
    engine.dispose()


def add_user(engine, email="admin@example.test", role="ADMIN", password="Correct horse battery staple 2026"):
    display, normalized = normalize_email(email)
    now = utc_text()
    with Session(engine) as db:
        user = User(
            user_id=f"usr_{role.lower()}_{normalized.split('@')[0]}",
            email=display,
            email_normalized=normalized,
            password_hash=hash_password(password),
            role=role,
            status="ACTIVE",
            must_change_password=False,
            created_at=now,
            updated_at=now,
            deactivated_at=None,
        )
        db.add(user)
        db.commit()
        return user.user_id


def sign_in(client: TestClient, email="admin@example.test", password="Correct horse battery staple 2026"):
    csrf = client.get("/auth/csrf")
    assert csrf.status_code == 200
    token = csrf.json()["csrf_token"]
    response = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": token, "Origin": "https://testserver"},
        json={"email": email, "password": password},
    )
    return response


def session_csrf(client: TestClient) -> str:
    response = client.get("/auth/session")
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_password_policy_hash_and_email_canonicalization():
    encoded = hash_password("Correct horse battery staple 2026")
    assert encoded.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert "Correct horse battery staple 2026" not in encoded
    assert validate_password("e\u0301" + "very long phrase 2026") == "évery long phrase 2026"
    with pytest.raises(ValueError):
        validate_password("password1234567")
    with pytest.raises(ValueError):
        validate_password("x" * 129)
    with pytest.raises(ValueError):
        validate_password("Correct Horse Battery Staple")
    display, normalized = normalize_email("  Alice@exämple.test  ")
    assert display == "Alice@exämple.test"
    assert normalized == "alice@xn--exmple-cua.test"


def test_prelogin_csrf_cookie_login_session_and_logout(auth_app):
    app, engine = auth_app
    add_user(engine)
    with TestClient(app, base_url="https://testserver") as client:
        csrf_response = client.get("/auth/csrf")
        token = csrf_response.json()["csrf_token"]
        cookie = csrf_response.headers["set-cookie"]
        assert f"{PRELOGIN_CSRF_COOKIE}=" in cookie
        assert "secure" in cookie.lower() and "httponly" in cookie.lower()
        assert "samesite=strict" in cookie.lower() and "path=/" in cookie.lower()
        assert "max-age=600" in cookie.lower()
        assert csrf_response.headers["cache-control"] == "no-store"

        response = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": token, "Origin": "https://testserver"},
            json={"email": "ADMIN@example.test", "password": "Correct horse battery staple 2026"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["user"]["role"] == "ADMIN"
        assert payload["user"]["must_change_password"] is False
        assert "password_hash" not in payload and "password" not in payload
        assert client.cookies.get(SESSION_COOKIE)
        assert client.cookies.get(PRELOGIN_CSRF_COOKIE) is None
        set_cookie = response.headers["set-cookie"].lower()
        assert "secure" in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
        assert "path=/" in set_cookie and "domain=" not in set_cookie
        assert client.get("/auth/session").json()["csrf_token"] == payload["csrf_token"]

        old_bearer = client.cookies.get(SESSION_COOKIE)
        invalid = client.post("/auth/logout", headers={"X-CSRF-Token": "wrong"})
        assert invalid.status_code == 403
        with Session(engine) as db:
            session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(old_bearer)))
            assert session is not None and session.revoked_at is None
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 0

        logged_out = client.post("/auth/logout", headers={"X-CSRF-Token": payload["csrf_token"]})
        assert logged_out.status_code == 204
        assert client.get("/auth/session").status_code == 401
        with Session(engine) as db:
            session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(old_bearer)))
            assert session.revoked_at is not None
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "LOGOUT")) == 1


def test_login_requires_exact_same_origin_and_generic_credential_errors(auth_app):
    app, engine = auth_app
    add_user(engine)
    inactive_id = add_user(engine, "inactive@example.test", "BUSINESS_USER", "Inactive user phrase 2026!")
    with Session(engine) as db:
        inactive = db.get(User, inactive_id)
        assert inactive is not None
        inactive.status = "DEACTIVATED"
        inactive.deactivated_at = utc_text()
        db.commit()
    with TestClient(app, base_url="https://testserver") as client:
        csrf = client.get("/auth/csrf").json()["csrf_token"]
        denied = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": csrf, "Origin": "https://attacker.example"},
            json={"email": "admin@example.test", "password": "wrong password"},
        )
        assert denied.status_code == 403
        assert "password" not in denied.text.lower()
        assert client.cookies.get(PRELOGIN_CSRF_COOKIE) == csrf
        wrong = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
            json={"email": "admin@example.test", "password": "definitely wrong password"},
        )
        unknown = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
            json={"email": "unknown@example.test", "password": "definitely wrong password"},
        )
        inactive = client.post(
            "/auth/login",
            headers={"X-CSRF-Token": csrf, "Origin": "https://testserver"},
            json={"email": "inactive@example.test", "password": "Inactive user phrase 2026!"},
        )
        assert wrong.status_code == unknown.status_code == inactive.status_code == 401
        assert wrong.json()["detail"] == unknown.json()["detail"] == inactive.json()["detail"]
        assert "admin@example.test" not in wrong.text
        assert "definitely wrong password" not in wrong.text


def test_business_user_is_denied_admin_route_and_denial_is_audited(auth_app):
    app, engine = auth_app
    add_user(engine)
    add_user(engine, "business@example.test", "BUSINESS_USER", "Business user phrase 2026")
    with TestClient(app, base_url="https://testserver") as client:
        signed = sign_in(client, "business@example.test", "Business user phrase 2026")
        assert signed.status_code == 200
        denied = client.get("/admin/users")
        assert denied.status_code == 403
        assert denied.json()["code"] == "FORBIDDEN"
        with Session(engine) as db:
            events = db.scalars(select(AuditEvent).where(AuditEvent.action == "AUTHORIZATION_DENIED")).all()
            assert len(events) == 1
            assert events[0].resource_id == "ADMIN_USER_MANAGEMENT"
            assert "business@example.test" not in (events[0].before_state_text or "")


def test_every_admin_user_route_denies_direct_unauthenticated_and_business_requests(auth_app):
    app, engine = auth_app
    add_user(engine)
    target_id = add_user(engine, "target@example.test", "BUSINESS_USER", "Original user passphrase 2026!")
    routes = [
        ("GET", "/admin/users?page=1", None),
        ("GET", f"/admin/users/{target_id}", None),
        ("POST", "/admin/users", {"email": "new@example.test", "role": "BUSINESS_USER", "initial_password": "Temporary phrase 2026!"}),
        ("PATCH", f"/admin/users/{target_id}", {}),
        ("POST", f"/admin/users/{target_id}/password-reset", {"temporary_password": "Reset phrase 2026!"}),
    ]
    with TestClient(app, base_url="https://testserver") as anonymous:
        for method, path, body in routes:
            response = anonymous.request(method, path, json=body)
            assert response.status_code == 401

    with TestClient(app, base_url="https://testserver") as business:
        assert sign_in(business, "target@example.test", "Original user passphrase 2026!").status_code == 200
        for method, path, body in routes:
            response = business.request(method, path, json=body)
            assert response.status_code == 403

    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 2
        target = db.get(User, target_id)
        assert target is not None and target.status == "ACTIVE" and target.must_change_password is False
        events = db.scalars(select(AuditEvent).where(AuditEvent.action == "AUTHORIZATION_DENIED")).all()
        assert len(events) == len(routes)


def test_first_admin_hidden_prompt_and_one_time_provisioning(monkeypatch, tmp_path, capsys):
    settings = Settings(data_dir=tmp_path / "setup-data", sqlite_busy_timeout_ms=1000)
    engine = create_database_engine(settings)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(bootstrap_admin, "get_settings", lambda: settings)
    email_inputs = iter(["first@example.test"])
    hidden_password_inputs = iter(["First Admin phrase 2026!", "First Admin phrase 2026!"])
    hidden_prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: next(email_inputs))

    def hidden_prompt(prompt: str) -> str:
        hidden_prompts.append(prompt)
        return next(hidden_password_inputs)

    monkeypatch.setattr(bootstrap_admin.getpass, "getpass", hidden_prompt)
    assert bootstrap_admin.main() == 0
    assert "First Admin provisioned." in capsys.readouterr().out
    assert hidden_prompts == ["Initial Admin password: ", "Confirm initial Admin password: "]
    with Session(engine) as db:
        admin = db.scalar(select(User).where(User.role == "ADMIN"))
        assert admin is not None and verify_password("First Admin phrase 2026!", admin.password_hash)
        assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "ACCOUNT_CREATED")) == 1

    with pytest.raises(RuntimeError, match="already exists"):
        bootstrap_admin.provision_first_admin("second@example.test", "Second Admin phrase 2026!", "Second Admin phrase 2026!")
    engine.dispose()


def test_admin_user_create_idempotency_and_password_change_gate(auth_app):
    app, engine = auth_app
    add_user(engine)
    temporary = "A temporary passphrase 2026!"
    with TestClient(app, base_url="https://testserver") as client:
        assert sign_in(client).status_code == 200
        csrf = session_csrf(client)
        headers = {"X-CSRF-Token": csrf, "Idempotency-Key": "create-business-001"}
        body = {"email": "business@example.test", "role": "BUSINESS_USER", "initial_password": temporary}
        created = client.post("/admin/users", headers=headers, json=body)
        replay = client.post("/admin/users", headers=headers, json=body)
        assert created.status_code == replay.status_code == 201
        assert created.json()["user_id"] == replay.json()["user_id"]
        assert created.json()["must_change_password"] is True
        assert temporary not in created.text and "password_hash" not in created.text
        listed = client.get("/admin/users")
        detail = client.get(f"/admin/users/{created.json()['user_id']}")
        assert listed.status_code == detail.status_code == 200
        assert created.json()["user_id"] in {item["user_id"] for item in listed.json()["items"]}
        assert detail.json()["user_id"] == created.json()["user_id"]
        assert "password_hash" not in detail.text
        conflict = client.post(
            "/admin/users",
            headers=headers,
            json={**body, "initial_password": "Another temporary passphrase 2026!"},
        )
        assert conflict.status_code == 409

        with Session(engine) as db:
            target = db.get(User, created.json()["user_id"])
            assert target is not None and temporary not in target.password_hash
            assert db.scalar(select(func.count()).select_from(User)) == 2
            stored_audit = " ".join(
                (event.before_state_text or "") + (event.after_state_text or "")
                for event in db.scalars(select(AuditEvent)).all()
            )
            assert temporary not in stored_audit
            assert "password_hash" not in stored_audit

    with TestClient(app, base_url="https://testserver") as business_client:
        signed = sign_in(business_client, "business@example.test", temporary)
        assert signed.status_code == 200
        assert signed.json()["user"]["must_change_password"] is True
        old_bearer = business_client.cookies.get(SESSION_COOKIE)
        assert business_client.get("/admin/users").status_code == 403
        changed = business_client.post(
            "/auth/password-change",
            headers={"X-CSRF-Token": signed.json()["csrf_token"]},
            json={"current_password": temporary, "new_password": "A new permanent passphrase 2026!"},
        )
        assert changed.status_code == 200
        assert changed.json()["user"]["must_change_password"] is False
        assert business_client.cookies.get(SESSION_COOKIE) != old_bearer
        assert business_client.get("/auth/session").status_code == 200
        with Session(engine) as db:
            old_session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(old_bearer)))
            assert old_session is not None and old_session.revoked_at is not None
            user = db.get(User, signed.json()["user"]["user_id"])
            assert user is not None and user.must_change_password is False
            actions = set(db.scalars(select(AuditEvent.action)).all())
            assert {"PASSWORD_CHANGED", "SESSION_REVOKED"}.issubset(actions)


def test_admin_reset_and_deactivation_revoke_target_sessions(auth_app):
    app, engine = auth_app
    add_user(engine)
    target_id = add_user(engine, "target@example.test", "BUSINESS_USER", "Original user passphrase 2026!")
    with TestClient(app, base_url="https://testserver") as admin_client:
        assert sign_in(admin_client).status_code == 200
        csrf = session_csrf(admin_client)
        with TestClient(app, base_url="https://testserver") as target_client:
            target_login = sign_in(target_client, "target@example.test", "Original user passphrase 2026!")
            assert target_login.status_code == 200
            old_bearer = target_client.cookies.get(SESSION_COOKIE)
            temporary = "Reset temporary passphrase 2026!"
            reset = admin_client.post(
                f"/admin/users/{target_id}/password-reset",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reset-001"},
                json={"temporary_password": temporary},
            )
            assert reset.status_code == 200
            assert reset.json()["must_change_password"] is True
            assert temporary not in reset.text and "password_hash" not in reset.text
            assert target_client.get("/auth/session").status_code == 401
            with Session(engine) as db:
                old_session = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(old_bearer)))
                assert old_session is not None and old_session.revoked_at is not None
            replay = admin_client.post(
                f"/admin/users/{target_id}/password-reset",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "reset-001"},
                json={"temporary_password": temporary},
            )
            assert replay.status_code == 200
            assert replay.json()["must_change_password"] is True

            deactivated = admin_client.patch(
                f"/admin/users/{target_id}",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": "deactivate-001"},
                json={},
            )
            assert deactivated.status_code == 200
            assert deactivated.json()["status"] == "DEACTIVATED"
            with Session(engine) as db:
                target = db.get(User, target_id)
                assert target is not None and target.status == "DEACTIVATED"
                actions = set(db.scalars(select(AuditEvent.action)).all())
                assert {"PASSWORD_RESET", "SESSION_REVOKED", "ACCOUNT_DEACTIVATED"}.issubset(actions)


def test_session_idle_expiry_and_validation_error_redaction(auth_app):
    app, engine = auth_app
    add_user(engine)
    with TestClient(app, base_url="https://testserver") as client:
        signed = sign_in(client)
        assert signed.status_code == 200
        bearer = client.cookies.get(SESSION_COOKIE)
        with Session(engine) as db:
            record = db.scalar(select(SessionRecord).where(SessionRecord.token_hash == bearer_hash(bearer)))
            record.last_seen_at = utc_text(utc_now() - timedelta(minutes=31))
            db.commit()
        expired = client.get("/auth/session")
        assert expired.status_code == 401
        assert expired.json()["code"] == "SESSION_EXPIRED"

        invalid = client.post("/auth/login", json={"password": "sensitive submitted value"})
        assert invalid.status_code == 422
        assert "sensitive submitted value" not in invalid.text
        assert "input" not in invalid.text.lower()


def test_login_throttle_uses_hashed_local_keys_and_account_cooldown():
    limiter = LoginThrottle()
    now = 1_000.0
    for _ in range(9):
        limiter.record_attempt("candidate@example.test", "127.0.0.1", failed=True, now=now)
    assert limiter.check("candidate@example.test", "127.0.0.1", now=now) is None
    limiter.record_attempt("candidate@example.test", "127.0.0.1", failed=True, now=now)
    assert limiter.check("candidate@example.test", "192.0.2.10", now=now + 1) == 899
    assert limiter.check("other@example.test", "127.0.0.1", now=now) is None
    assert not any("candidate@example.test" in str(key) for key in limiter._account_failures)
    assert not any("127.0.0.1" in str(key) for key in limiter._ip_attempts)


def test_prelogin_csrf_tokens_are_signed_and_expire_at_ten_minutes(monkeypatch):
    import productpulse.auth_state as auth_state

    now = 1_800_000_000
    monkeypatch.setattr(auth_state.time, "time", lambda: now)
    tokens = PreLoginTokens()
    token = tokens.issue()
    assert tokens.valid(token)
    assert not tokens.valid(token + "x")
    assert not tokens.valid("not-a-token")

    monkeypatch.setattr(auth_state.time, "time", lambda: now + 600)
    assert tokens.valid(token)
    monkeypatch.setattr(auth_state.time, "time", lambda: now + 601)
    assert not tokens.valid(token)
    monkeypatch.setattr(auth_state.time, "time", lambda: now - 1)
    assert not tokens.valid(token)


def test_login_api_enforces_account_failure_limit(auth_app, caplog):
    import logging

    app, _engine = auth_app
    caplog.set_level(logging.INFO, logger="productpulse.security.auth")
    with TestClient(app, base_url="https://testserver") as client:
        token = client.get("/auth/csrf").json()["csrf_token"]
        headers = {"X-CSRF-Token": token, "Origin": "https://testserver"}
        for attempt in range(10):
            failed = client.post(
                "/auth/login",
                headers=headers,
                json={"email": "same@example.test", "password": f"wrong password {attempt}"},
            )
            assert failed.status_code == 401
        limited = client.post(
            "/auth/login",
            headers=headers,
            json={"email": "same@example.test", "password": "wrong password 11"},
        )
        assert limited.status_code == 429
        assert limited.headers["retry-after"]
        assert "same@example.test" not in limited.text
    security_messages = [record.getMessage() for record in caplog.records if record.name == "productpulse.security.auth"]
    assert any("event=LOGIN_FAILED" in message for message in security_messages)
    assert any("event=LOGIN_THROTTLED" in message for message in security_messages)
    assert all("same@example.test" not in message and "wrong password" not in message for message in security_messages)


def test_login_throttle_enforces_ip_limit_and_expires_window():
    limiter = LoginThrottle()
    now = 2_000.0
    for index in range(limiter.IP_ATTEMPT_LIMIT):
        limiter.record_attempt(f"candidate-{index}@example.test", "192.0.2.8", failed=True, now=now)
    assert limiter.check("another@example.test", "192.0.2.8", now=now) == 900
    assert limiter.check("another@example.test", "192.0.2.8", now=now + 901) is None
    assert not limiter._ip_attempts

