from collections import defaultdict, deque
import base64
import hashlib
import hmac
import secrets
import threading
import time


class PreLoginTokens:
    def __init__(self) -> None:
        self._signing_key = secrets.token_bytes(32)

    def issue(self) -> str:
        issued_at = str(int(time.time()))
        nonce = secrets.token_urlsafe(32)
        message = f"{issued_at}.{nonce}"
        signature = base64.urlsafe_b64encode(hmac.new(self._signing_key, message.encode("ascii"), hashlib.sha256).digest()).rstrip(b"=").decode("ascii")
        return f"{message}.{signature}"

    def valid(self, token: str) -> bool:
        try:
            issued_at_text, nonce, supplied_signature = token.split(".", 2)
            issued_at = int(issued_at_text)
            message = f"{issued_at_text}.{nonce}"
            expected = base64.urlsafe_b64encode(
                hmac.new(self._signing_key, message.encode("ascii"), hashlib.sha256).digest()
            ).rstrip(b"=").decode("ascii")
        except (AttributeError, UnicodeError, ValueError):
            return False
        age = int(time.time()) - issued_at
        return 0 <= age <= 600 and hmac.compare_digest(expected, supplied_signature)


class LoginThrottle:
    WINDOW_SECONDS = 900
    ACCOUNT_FAILURE_LIMIT = 10
    IP_ATTEMPT_LIMIT = 60

    def __init__(self) -> None:
        self._account_failures: dict[str, deque[float]] = defaultdict(deque)
        self._account_cooldowns: dict[str, float] = {}
        self._ip_attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    @staticmethod
    def _key(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()

    def check(self, candidate: str, source_ip: str, now: float | None = None) -> int | None:
        point = time.monotonic() if now is None else now
        account_key = self._key(candidate)
        ip_key = self._key(source_ip)
        with self._lock:
            self._prune_all(point)
            cooldown_until = self._account_cooldowns.get(account_key, 0.0)
            if cooldown_until > point:
                return max(1, int(cooldown_until - point))
            attempts = self._ip_attempts.get(ip_key)
            if attempts is not None:
                self._prune(attempts, point)
            if attempts and len(attempts) >= self.IP_ATTEMPT_LIMIT:
                return max(1, int(attempts[0] + self.WINDOW_SECONDS - point))
            return None

    def record_attempt(self, candidate: str, source_ip: str, *, failed: bool, now: float | None = None) -> None:
        point = time.monotonic() if now is None else now
        account_key = self._key(candidate)
        ip_key = self._key(source_ip)
        with self._lock:
            self._prune_all(point)
            ip_attempts = self._ip_attempts[ip_key]
            self._prune(ip_attempts, point)
            ip_attempts.append(point)
            failures = self._account_failures[account_key]
            self._prune(failures, point)
            if failed:
                failures.append(point)
                if len(failures) >= self.ACCOUNT_FAILURE_LIMIT:
                    self._account_cooldowns[account_key] = point + self.WINDOW_SECONDS
            else:
                failures.clear()
                self._account_cooldowns.pop(account_key, None)

    @staticmethod
    def _prune(values: deque[float], now: float) -> None:
        cutoff = now - LoginThrottle.WINDOW_SECONDS
        while values and values[0] <= cutoff:
            values.popleft()

    def _prune_all(self, now: float) -> None:
        for key in list(self._account_failures):
            values = self._account_failures[key]
            self._prune(values, now)
            if not values:
                self._account_failures.pop(key, None)
        for key in list(self._ip_attempts):
            values = self._ip_attempts[key]
            self._prune(values, now)
            if not values:
                self._ip_attempts.pop(key, None)
        for key, expiry in list(self._account_cooldowns.items()):
            if expiry <= now:
                self._account_cooldowns.pop(key, None)

