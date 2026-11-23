"""One-time protected command to provision the first ProductPulse Admin."""

import getpass
import sys

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from productpulse.api_common import safe_audit
from productpulse.database import create_database_engine
from productpulse.models import User
from productpulse.security.identity import EmailIdentityError, normalize_email
from productpulse.security.passwords import PasswordPolicyError, hash_password
from productpulse.security.sessions import utc_text
from productpulse.settings import SettingsError, get_settings


def provision_first_admin(email_input: str, password: str, confirmation: str) -> None:
    if password != confirmation:
        raise ValueError("The password entries did not match")
    try:
        email, email_normalized = normalize_email(email_input)
        password_hash = hash_password(password)
    except EmailIdentityError as error:
        raise ValueError("Enter a valid email address") from error
    except PasswordPolicyError as error:
        raise ValueError(str(error)) from error

    settings = get_settings()
    engine = create_database_engine(settings)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            db.execute(text("BEGIN IMMEDIATE"))
            admin_count = db.scalar(select(func.count()).select_from(User).where(User.role == "ADMIN")) or 0
            if admin_count:
                db.rollback()
                raise RuntimeError("An Admin already exists; first-Admin setup is closed")
            now = utc_text()
            admin = User(
                user_id="usr_first_admin",
                email=email,
                email_normalized=email_normalized,
                password_hash=password_hash,
                role="ADMIN",
                status="ACTIVE",
                must_change_password=False,
                created_at=now,
                updated_at=now,
                deactivated_at=None,
            )
            db.add(admin)
            safe_audit(
                db,
                action="ACCOUNT_CREATED",
                resource_type="USER",
                resource_id=admin.user_id,
                actor_user_id=None,
                after={"role": "ADMIN", "status": "ACTIVE", "credential_change_required": False},
            )
            db.commit()
    except IntegrityError as error:
        raise RuntimeError("First-Admin setup could not be completed") from error
    finally:
        engine.dispose()


def main() -> int:
    try:
        email = input("First Admin email: ")
        password = getpass.getpass("Initial Admin password: ")
        confirmation = getpass.getpass("Confirm initial Admin password: ")
        provision_first_admin(email, password, confirmation)
    except (ValueError, RuntimeError, SettingsError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("First-Admin setup cancelled.", file=sys.stderr)
        return 1
    print("First Admin provisioned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

