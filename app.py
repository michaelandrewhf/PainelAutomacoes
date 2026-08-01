import logging
import os
import traceback

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from automation_service import (
    bootstrap_automation_service,
    list_automations,
    start_automation,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


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
    status, automation = start_automation(automation_id)

    if status == "not_found":
        return jsonify({"error": "Automação não encontrada."}), 404

    if status == "already_running":
        return jsonify({"error": "Esta automação já está em execução."}), 409

    if status == "start_error":
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
