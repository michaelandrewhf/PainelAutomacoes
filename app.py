import logging
import os
import traceback

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from automation_service import (
    bootstrap_automation_service,
    is_automation_running,
    list_automations,
    start_automation,
)
from config import MAX_UPLOAD_SIZE_BYTES
from upload_service import UploadValidationError, cleanup_upload, prepare_xlsx_upload


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_SIZE_BYTES


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
def index():
    return render_template("index.html", automations=list_automations())


@app.get("/api/automations")
def api_automations():
    return jsonify({"automations": list_automations()}), 200


@app.post("/api/automations/<automation_id>/run")
def run_automation(automation_id):
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

        def cleanup_prepared_upload():
            cleanup_upload(prepared_upload)

        cleanup_callback = cleanup_prepared_upload

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
