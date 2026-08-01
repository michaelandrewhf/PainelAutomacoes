from functools import wraps
from hmac import compare_digest
import secrets
from threading import Lock
import time

from flask import jsonify, redirect, request, session, url_for

from config import (
    AUTH_PASSWORD,
    AUTH_USER,
    LOGIN_RATE_LIMIT_ATTEMPTS,
    LOGIN_RATE_LIMIT_BLOCK_SECONDS,
    LOGIN_RATE_LIMIT_WINDOW_SECONDS,
    SECRET_KEY,
)


CSRF_SESSION_KEY = "csrf_token"
LOGIN_ATTEMPTS = {}
LOGIN_ATTEMPTS_LOCK = Lock()


class AuthConfigurationError(RuntimeError):
    pass


def validate_auth_config() -> None:
    required = {
        "USER_APP": AUTH_USER,
        "PASSWORD": AUTH_PASSWORD,
        "SECRET_KEY": SECRET_KEY,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise AuthConfigurationError(
            f"Variável de ambiente {missing[0]} não configurada."
        )

    if len(SECRET_KEY) < 32:
        raise AuthConfigurationError(
            "Variável de ambiente SECRET_KEY deve ter pelo menos 32 caracteres."
        )

    if compare_digest(SECRET_KEY, AUTH_PASSWORD):
        raise AuthConfigurationError(
            "SECRET_KEY e PASSWORD devem possuir valores diferentes."
        )


def is_authenticated() -> bool:
    return session.get("authenticated") is True


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if is_authenticated():
            return view(*args, **kwargs)

        if request.path.startswith("/api/"):
            return jsonify({"error": "Autenticação necessária."}), 401

        return redirect(url_for("login"))

    return wrapped_view


def validate_credentials(username: str, password: str) -> bool:
    submitted_user = str(username).strip()
    submitted_password = str(password)
    return compare_digest(submitted_user, AUTH_USER) and compare_digest(
        submitted_password,
        AUTH_PASSWORD,
    )


def check_login_attempt(username: str, password: str, ip_address: str | None = None) -> str:
    ip_address = ip_address or client_ip()
    now = time.time()

    with LOGIN_ATTEMPTS_LOCK:
        state = LOGIN_ATTEMPTS.get(ip_address)
        if state and state.get("blocked_until", 0) > now:
            return "blocked"

        if state and now - state.get("window_start", now) > LOGIN_RATE_LIMIT_WINDOW_SECONDS:
            state = None
            LOGIN_ATTEMPTS.pop(ip_address, None)

        if validate_credentials(username, password):
            LOGIN_ATTEMPTS.pop(ip_address, None)
            return "valid"

        if not state:
            state = {"window_start": now, "attempts": 0, "blocked_until": 0}

        state["attempts"] += 1
        if state["attempts"] >= LOGIN_RATE_LIMIT_ATTEMPTS:
            state["blocked_until"] = now + LOGIN_RATE_LIMIT_BLOCK_SECONDS

        LOGIN_ATTEMPTS[ip_address] = state
        return "invalid"


def authenticate_session() -> None:
    session.clear()
    session["authenticated"] = True
    session.permanent = True
    get_csrf_token()


def get_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(token: str | None) -> bool:
    expected_token = session.get(CSRF_SESSION_KEY)
    if not expected_token or not token:
        return False
    return compare_digest(str(token), str(expected_token))


def csrf_token_from_request() -> str:
    return request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")


def csrf_error_response():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Token CSRF inválido."}), 400
    return "Token CSRF inválido.", 400


def client_ip() -> str:
    return request.remote_addr or "unknown"


def is_login_rate_limited(ip_address: str | None = None) -> bool:
    ip_address = ip_address or client_ip()
    now = time.time()
    with LOGIN_ATTEMPTS_LOCK:
        state = LOGIN_ATTEMPTS.get(ip_address)
        if not state:
            return False

        if state.get("blocked_until", 0) > now:
            return True

        if now - state.get("window_start", now) > LOGIN_RATE_LIMIT_WINDOW_SECONDS:
            LOGIN_ATTEMPTS.pop(ip_address, None)

        return False


def record_failed_login(ip_address: str | None = None) -> None:
    ip_address = ip_address or client_ip()
    now = time.time()
    with LOGIN_ATTEMPTS_LOCK:
        state = LOGIN_ATTEMPTS.get(ip_address)
        if not state or now - state["window_start"] > LOGIN_RATE_LIMIT_WINDOW_SECONDS:
            state = {"window_start": now, "attempts": 0, "blocked_until": 0}

        state["attempts"] += 1
        if state["attempts"] >= LOGIN_RATE_LIMIT_ATTEMPTS:
            state["blocked_until"] = now + LOGIN_RATE_LIMIT_BLOCK_SECONDS

        LOGIN_ATTEMPTS[ip_address] = state


def clear_failed_logins(ip_address: str | None = None) -> None:
    with LOGIN_ATTEMPTS_LOCK:
        LOGIN_ATTEMPTS.pop(ip_address or client_ip(), None)
