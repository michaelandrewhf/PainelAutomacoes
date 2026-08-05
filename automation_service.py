import logging
from collections import deque
from datetime import UTC, datetime
from threading import Lock, Thread, local

from automation_registry import AUTOMATIONS
from database import (
    create_run,
    finish_interrupted_runs,
    finish_run,
    get_last_runs_by_automation,
    init_db,
)

logger = logging.getLogger(__name__)

GENERIC_AUTOMATION_ERROR = "A automação falhou. Verifique os logs do container."
MAX_LOG_LINES = 200

running_automations = set()
execution_logs = {}

running_lock = Lock()
logs_lock = Lock()
log_context = local()


class AutomationLogHandler(logging.Handler):
    def emit(self, record):
        automation_id = getattr(log_context, "automation_id", None)

        if automation_id is None or not record.name.startswith("automations."):
            return

        message = f"{datetime.now():%H:%M:%S} {record.getMessage()}"

        with logs_lock:
            execution_logs.setdefault(
                automation_id,
                deque(maxlen=MAX_LOG_LINES),
            ).append(message)


def install_log_handler():
    root_logger = logging.getLogger()

    if any(
        isinstance(handler, AutomationLogHandler) for handler in root_logger.handlers
    ):
        return

    handler = AutomationLogHandler()
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def utc_now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def format_duration(seconds):
    if seconds is None:
        return "—"

    minutes, seconds = divmod(round(seconds), 60)

    if minutes == 0:
        return f"{seconds} segundo{'s' if seconds != 1 else ''}"

    result = f"{minutes} minuto{'s' if minutes != 1 else ''}"

    if seconds:
        result += f" e {seconds} segundo{'s' if seconds != 1 else ''}"

    return result


def get_execution_logs(automation_id):
    with logs_lock:
        return list(execution_logs.get(automation_id, ()))


def automation_payload(automation_id, config, last_run=None):
    last_run = last_run or {}

    with running_lock:
        is_running = automation_id in running_automations

    duration = last_run.get("duration_seconds")

    return {
        "id": automation_id,
        "name": config["name"],
        "description": config["description"],
        "requires_file": bool(config.get("requires_file")),
        "status": ("running" if is_running else last_run.get("status", "never")),
        "last_started_at": last_run.get("started_at"),
        "last_finished_at": last_run.get("finished_at"),
        "duration_seconds": duration,
        "duration_label": format_duration(duration),
        "error_message": last_run.get("error_message"),
        "is_running": is_running,
        "execution_logs": get_execution_logs(automation_id),
    }


def list_automations():
    last_runs = get_last_runs_by_automation()

    return [
        automation_payload(
            automation_id,
            config,
            last_runs.get(automation_id),
        )
        for automation_id, config in AUTOMATIONS.items()
    ]


def execute_automation(automation_id, run_id, runner, runner_kwargs=None):
    status = "success"
    error_message = None
    log_context.automation_id = automation_id

    try:
        runner(**(runner_kwargs or {}))
    except Exception as exc:
        status = "error"
        error_message = (
            str(exc) if isinstance(exc, RuntimeError) else GENERIC_AUTOMATION_ERROR
        )
        logger.exception("Falha na automação %s", automation_id)
    finally:
        try:
            finish_run(
                run_id,
                utc_now_iso(),
                status,
                error_message,
            )
        except Exception:
            logger.exception(
                "Falha ao salvar status da automação %s",
                automation_id,
            )

        with running_lock:
            running_automations.discard(automation_id)

        del log_context.automation_id


def start_automation(automation_id, runner_kwargs=None):
    config = AUTOMATIONS.get(automation_id)

    if config is None:
        return "not_found", None

    with running_lock:
        if automation_id in running_automations:
            return "already_running", None

        running_automations.add(automation_id)

    with logs_lock:
        execution_logs[automation_id] = deque(maxlen=MAX_LOG_LINES)

    started_at = utc_now_iso()
    run_id = None

    try:
        run_id = create_run(automation_id, started_at)

        Thread(
            target=execute_automation,
            args=(
                automation_id,
                run_id,
                config["runner"],
                runner_kwargs,
            ),
            daemon=True,
        ).start()

    except Exception:
        with running_lock:
            running_automations.discard(automation_id)

        if run_id is not None:
            try:
                finish_run(
                    run_id,
                    utc_now_iso(),
                    "error",
                    "Não foi possível iniciar a automação.",
                )
            except Exception:
                logger.exception(
                    "Falha ao salvar erro de inicialização de %s",
                    automation_id,
                )

        logger.exception(
            "Falha ao iniciar automação %s",
            automation_id,
        )
        return "start_error", None

    return "started", automation_payload(
        automation_id,
        config,
        {
            "started_at": started_at,
            "status": "running",
        },
    )


def bootstrap_automation_service():
    install_log_handler()
    init_db()

    interrupted = finish_interrupted_runs(
        "Execução interrompida por reinicialização da aplicação."
    )

    if interrupted:
        logger.warning(
            "%s execução(ões) interrompida(s) marcada(s) como erro.",
            interrupted,
        )
