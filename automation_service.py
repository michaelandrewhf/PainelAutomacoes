import logging
import traceback
from datetime import UTC, datetime
from threading import Lock, Thread, get_ident

from automation_errors import PublicAutomationError
from automation_registry import AUTOMATIONS
from database import (
    create_run,
    finish_interrupted_runs,
    finish_run,
    get_last_runs_by_automation,
    init_db,
)
from upload_service import cleanup_stale_uploads


logger = logging.getLogger(__name__)
GENERIC_AUTOMATION_ERROR = "A automação falhou. Verifique os logs do container."

running_automations = set()
running_lock = Lock()
execution_logs = {}
log_threads = {}
logs_lock = Lock()
log_handler_installed = False


class AutomationLogHandler(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.ERROR:
            return

        if not (
            record.name == __name__
            or record.name.startswith("automations.")
        ):
            return

        thread_id = get_ident()
        with logs_lock:
            automation_id = log_threads.get(thread_id)
            if not automation_id:
                return

            message = record.getMessage()
            timestamp = datetime.now().strftime("%H:%M:%S")
            lines = execution_logs.setdefault(automation_id, [])
            lines.append(f"{timestamp} {message}")
            del lines[:-200]


def install_log_handler():
    global log_handler_installed
    if log_handler_installed:
        return

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        if handler.__class__.__name__ == "AutomationLogHandler":
            root_logger.removeHandler(handler)
    handler = AutomationLogHandler()
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)
    log_handler_installed = True


def reset_execution_logs(automation_id):
    with logs_lock:
        execution_logs[automation_id] = []


def get_execution_logs(automation_id):
    with logs_lock:
        return list(execution_logs.get(automation_id, []))


def is_automation_running(automation_id):
    with running_lock:
        return automation_id in running_automations


def register_log_thread(automation_id):
    with logs_lock:
        log_threads[get_ident()] = automation_id


def unregister_log_thread():
    with logs_lock:
        log_threads.pop(get_ident(), None)


def utc_now_iso():
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def format_traceback_locations(traceback_object):
    return "\n".join(
        f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}'
        for frame in traceback.extract_tb(traceback_object)
    )


def format_duration(seconds):
    if seconds is None:
        return "—"

    total_seconds = int(round(seconds))
    minutes, remaining_seconds = divmod(total_seconds, 60)

    if minutes == 0:
        unit = "segundo" if remaining_seconds == 1 else "segundos"
        return f"{remaining_seconds} {unit}"

    minute_unit = "minuto" if minutes == 1 else "minutos"
    second_unit = "segundo" if remaining_seconds == 1 else "segundos"
    return f"{minutes} {minute_unit} e {remaining_seconds} {second_unit}"


def get_automation(automation_id):
    return AUTOMATIONS.get(automation_id)


def automation_payload(automation_id, config, last_run):
    with running_lock:
        is_running = automation_id in running_automations

    if is_running:
        status = "running"
    elif last_run:
        status = last_run["status"]
    else:
        status = "never"

    return {
        "id": automation_id,
        "name": config["name"],
        "description": config["description"],
        "requires_file": bool(config.get("requires_file")),
        "status": status,
        "last_started_at": last_run["started_at"] if last_run else None,
        "last_finished_at": last_run["finished_at"] if last_run else None,
        "duration_seconds": last_run["duration_seconds"] if last_run else None,
        "duration_label": format_duration(last_run["duration_seconds"] if last_run else None),
        "error_message": last_run["error_message"] if last_run else None,
        "is_running": is_running,
        "execution_logs": get_execution_logs(automation_id),
    }


def list_automations():
    last_runs = get_last_runs_by_automation()
    return [
        automation_payload(automation_id, config, last_runs.get(automation_id))
        for automation_id, config in AUTOMATIONS.items()
    ]


def execute_automation(automation_id, run_id, runner, runner_kwargs=None, cleanup_callback=None):
    status = "success"
    error_message = None
    runner_kwargs = runner_kwargs or {}
    register_log_thread(automation_id)

    try:
        logger.info("Starting automation %s", automation_id)
        runner(**runner_kwargs)
        logger.info("Finished automation %s", automation_id)
    except Exception as exc:
        status = "error"
        error_message = (
            str(exc) if isinstance(exc, PublicAutomationError) else GENERIC_AUTOMATION_ERROR
        )
        logger.error(
            "Automation %s failed with %s.\n%s",
            automation_id,
            exc.__class__.__name__,
            format_traceback_locations(exc.__traceback__),
        )
    finally:
        if cleanup_callback:
            try:
                cleanup_callback()
            except Exception:
                logger.exception("Falha ao limpar recursos temporários da automação")
        try:
            finished_at = utc_now_iso()
            finish_run(run_id, finished_at, status, error_message)
        except Exception:
            logger.error(
                "Failed to persist final status for automation %s.\n%s",
                automation_id,
                traceback.format_exc(),
            )
            with running_lock:
                running_automations.discard(automation_id)
            unregister_log_thread()
            return

        with running_lock:
            running_automations.discard(automation_id)
        unregister_log_thread()


def start_automation(automation_id, runner_kwargs=None, cleanup_callback=None):
    config = get_automation(automation_id)
    if config is None:
        return "not_found", None

    with running_lock:
        if automation_id in running_automations:
            return "already_running", None

        running_automations.add(automation_id)
        reset_execution_logs(automation_id)
        started_at = utc_now_iso()
        run_id = None

        try:
            run_id = create_run(automation_id, started_at)
            thread = Thread(
                target=execute_automation,
                args=(automation_id, run_id, config["runner"], runner_kwargs, cleanup_callback),
                daemon=True,
            )
            thread.start()
        except Exception:
            running_automations.discard(automation_id)
            if run_id is not None:
                finish_run(
                    run_id,
                    utc_now_iso(),
                    "error",
                    "Não foi possível iniciar a automação.",
                )
            if cleanup_callback:
                cleanup_callback()
            logger.error("Failed to start automation run.\n%s", traceback.format_exc())
            return "start_error", None

    payload = automation_payload(
        automation_id,
        config,
        {
            "started_at": started_at,
            "finished_at": None,
            "duration_seconds": None,
            "error_message": None,
            "status": "running",
        },
    )
    return "started", payload


def bootstrap_automation_service():
    install_log_handler()
    init_db()
    cleanup_stale_uploads()
    interrupted = finish_interrupted_runs("Execução interrompida por reinicialização da aplicação.")
    if interrupted:
        logger.warning("Marked %s interrupted automation run(s) as error.", interrupted)
