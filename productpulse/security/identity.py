import unicodedata


class EmailIdentityError(ValueError):
    pass


def normalize_email(email: str) -> tuple[str, str]:
    display = email.strip(" \t\n\r\v\f")
    display = unicodedata.normalize("NFC", display)
    if len(display) > 320 or display.count("@") != 1:
        raise EmailIdentityError("Email address is invalid")
    local, domain = display.rsplit("@", 1)
    if not local or not domain or any(ch.isspace() for ch in display):
        raise EmailIdentityError("Email address is invalid")
    try:
        ascii_domain = domain.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise EmailIdentityError("Email address is invalid") from error
    if not ascii_domain or len(ascii_domain) > 253 or "." not in ascii_domain:
        raise EmailIdentityError("Email address is invalid")
    if any(not label or len(label) > 63 or label.startswith("-") or label.endswith("-") for label in ascii_domain.split(".")):
        raise EmailIdentityError("Email address is invalid")
    if any(ch in local for ch in "<>(),;:\\[]\"") or local.startswith(".") or local.endswith(".") or ".." in local:
        raise EmailIdentityError("Email address is invalid")
    normalized = f"{local}@{ascii_domain}".casefold()
    if len(normalized) > 320:
        raise EmailIdentityError("Email address is invalid")
    return display, normalized

