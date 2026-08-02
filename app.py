import logging
import os
import traceback
from datetime import timedelta
from functools import partial

from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from auth import (
    authenticate_session,
    check_login_attempt,
    csrf_error_response,
    csrf_token_from_request,
    get_csrf_token,
    is_authenticated,
    login_required,
    validate_auth_config,
    validate_csrf_token,
)
from automation_service import (
    bootstrap_automation_service,
    is_automation_running,
    list_automations,
    start_automation,
)
from config import (
    MAX_UPLOAD_SIZE_BYTES,
    SECRET_KEY,
    SESSION_COOKIE_SECURE,
    SESSION_LIFETIME_HOURS,
    TRUST_PROXY,
)
from upload_service import UploadValidationError, cleanup_upload, prepare_xlsx_upload


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
if TRUST_PROXY:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

validate_auth_config()
app.config["SECRET_KEY"] = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_BYTES
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=SESSION_LIFETIME_HOURS)


def is_same_origin():
    expected_origin = request.host_url.rstrip("/")
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")

    if origin and origin.rstrip("/") != expected_origin:
        return False

    if referer and not referer.startswith(request.host_url):
        return False

    return True


@app.before_request
def reject_cross_origin_posts():
    if request.method == "POST" and request.path.startswith("/api/automations/"):
        if not is_same_origin():
            return jsonify({"error": "Origem da requisição não permitida."}), 403


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' https://cdn.tailwindcss.com 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'",
    )
    return response


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    if isinstance(error, HTTPException):
        if request.path.startswith("/api/"):
            if error.code == 413:
                return jsonify({"error": "Arquivo acima do limite permitido."}), 413
            return jsonify({"error": error.description}), error.code

        return error

    logger.error("Unhandled request error.\n%s", traceback.format_exc())

    if request.path.startswith("/api/"):
        return jsonify({"error": "Erro interno inesperado."}), 500

    return "Erro interno inesperado.", 500


@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        automations=list_automations(),
        csrf_token=get_csrf_token(),
    )


@app.get("/login")
def login():
    if is_authenticated():
        return redirect(url_for("index"))
    return render_template("login.html", csrf_token=get_csrf_token(), error_message=None)


@app.post("/login")
def login_post():
    if not validate_csrf_token(csrf_token_from_request()):
        return csrf_error_response()

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    if not username or not password:
        return (
            render_template(
                "login.html",
                csrf_token=get_csrf_token(),
                error_message="Informe o usuário e a senha.",
            ),
            400,
        )

    login_status = check_login_attempt(username, password)
    if login_status == "blocked":
        return (
            render_template(
                "login.html",
                csrf_token=get_csrf_token(),
                error_message="Muitas tentativas. Aguarde alguns minutos e tente novamente.",
            ),
            429,
        )

    if login_status != "valid":
        return (
            render_template(
                "login.html",
                csrf_token=get_csrf_token(),
                error_message="Usuário ou senha inválidos.",
            ),
            401,
        )

    authenticate_session()
    return redirect(url_for("index"))


@app.post("/logout")
@login_required
def logout():
    if not validate_csrf_token(csrf_token_from_request()):
        return csrf_error_response()

    session.clear()
    return redirect(url_for("login"))


@app.get("/api/automations")
@login_required
def api_automations():
    return jsonify({"automations": list_automations()}), 200


@app.post("/api/automations/<automation_id>/run")
@login_required
def run_automation(automation_id):
    if not validate_csrf_token(csrf_token_from_request()):
        return csrf_error_response()

    prepared_upload = None
    runner_kwargs = None
    cleanup_callback = None

    if automation_id == "drive-update":
        if is_automation_running(automation_id):
            return jsonify({"error": "A automação de atualização do Drive já está em execução."}), 409

        try:
            prepared_upload = prepare_xlsx_upload(request.files.get("file"))
        except UploadValidationError as error:
            logger.info(
                "Upload da automação do Drive rejeitado: %s",
                str(error),
            )
            return jsonify({"error": str(error)}), error.status_code

        runner_kwargs = {"input_file": prepared_upload.input_file}

        cleanup_callback = partial(cleanup_upload, prepared_upload)

    status, automation = start_automation(
        automation_id,
        runner_kwargs=runner_kwargs,
        cleanup_callback=cleanup_callback,
    )

    if status == "not_found":
        if prepared_upload:
            cleanup_upload(prepared_upload)
        return jsonify({"error": "Automação não encontrada."}), 404

    if status == "already_running":
        if prepared_upload:
            cleanup_upload(prepared_upload)
        if automation_id == "drive-update":
            return jsonify({"error": "A automação de atualização do Drive já está em execução."}), 409
        return jsonify({"error": "Esta automação já está em execução."}), 409

    if status == "start_error":
        if prepared_upload:
            cleanup_upload(prepared_upload)
        return jsonify({"error": "Não foi possível iniciar a automação."}), 500

    return (
        jsonify(
            {
                "message": "Automação iniciada.",
                "automation": automation,
            }
        ),
        202,
    )


bootstrap_automation_service()


if __name__ == "__main__":
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))
    app.run(host=host, port=port)
