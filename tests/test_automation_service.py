import importlib
import os
from io import BytesIO
from pathlib import Path
import sys
import tempfile
from threading import Event
import time
import unittest

from openpyxl import Workbook


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DRIVE_REQUIRED_COLUMNS = [
    "SERVICO",
    "AGENDAMENTO",
    "CTDTDATAAGENDA",
    "CTNOMESLOT",
    "LOCALIDADE",
    "PROTOCOLO",
    "CTDTSOLICITACAO",
    "CLIENTE",
    "ENDERECO",
    "BAIRRO",
]


def make_xlsx(headers=None, rows=None):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers or DRIVE_REQUIRED_COLUMNS)
    for row in rows or [
        [
            "IMPLANTACAO DADOS",
            "NÃO AGENDADO",
            "2026-08-01",
            "08:00",
            "PAULINIA",
            "12345",
            "2026-07-31",
            "Cliente",
            "Rua Teste",
            "Centro",
        ]
    ]:
        worksheet.append(row)

    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    buffer.seek(0)
    return buffer


def reload_project_modules(database_path):
    os.environ["DATABASE_PATH"] = str(database_path)
    os.environ["UPLOAD_TEMP_DIR"] = str(database_path.parent / "uploads")
    os.environ["MAX_UPLOAD_SIZE_MB"] = "20"
    for module_name in [
        "app",
        "automation_service",
        "automation_registry",
        "database",
        "config",
        "upload_service",
        "automations.drive.runner",
        "automations.drive.sheets_client",
        "automations.drive.spreadsheet_reader",
    ]:
        sys.modules.pop(module_name, None)

    import automation_service

    return importlib.reload(automation_service)


class AutomationServiceTests(unittest.TestCase):
    def test_cpfl_runner_is_registered(self):
        for module_name in ["automation_registry"]:
            sys.modules.pop(module_name, None)

        from automation_registry import AUTOMATIONS
        from automations.works_cpfl.runner import run

        self.assertIs(AUTOMATIONS["cpfl-works"]["runner"], run)

    def test_cpfl_runner_exposes_run_function(self):
        from automations.works_cpfl import runner

        self.assertTrue(callable(runner.run))

    def test_drive_runner_is_registered_and_requires_file(self):
        for module_name in ["automation_registry"]:
            sys.modules.pop(module_name, None)

        from automation_registry import AUTOMATIONS
        from automations.drive.runner import run

        self.assertIs(AUTOMATIONS["drive-update"]["runner"], run)
        self.assertTrue(AUTOMATIONS["drive-update"]["requires_file"])

    def test_duplicate_execution_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = reload_project_modules(Path(tmpdir) / "automations.db")
            service.bootstrap_automation_service()

            def slow_runner():
                time.sleep(0.2)

            service.AUTOMATIONS["cpfl-works"]["runner"] = slow_runner

            status, _ = service.start_automation("cpfl-works")
            duplicate_status, _ = service.start_automation("cpfl-works")

            self.assertEqual(status, "started")
            self.assertEqual(duplicate_status, "already_running")
            time.sleep(0.4)

    def test_success_and_error_status_are_persisted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = reload_project_modules(Path(tmpdir) / "automations.db")
            service.bootstrap_automation_service()

            ok_run = service.create_run("ok", service.utc_now_iso())
            service.execute_automation("ok", ok_run, lambda: None)

            def failing_runner():
                raise RuntimeError("internal provider path /tmp/secret/token.json")

            error_run = service.create_run("error", service.utc_now_iso())
            service.execute_automation("error", error_run, failing_runner)

            runs = service.get_last_runs_by_automation()
            self.assertEqual(runs["ok"]["status"], "success")
            self.assertEqual(runs["error"]["status"], "error")
            self.assertEqual(
                runs["error"]["error_message"],
                service.GENERIC_AUTOMATION_ERROR,
            )

    def test_execution_logs_are_captured_for_running_thread(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = reload_project_modules(Path(tmpdir) / "automations.db")
            service.bootstrap_automation_service()

            run_id = service.create_run("logs", service.utc_now_iso())
            logger = service.logging.getLogger("automations.works_cpfl.test")

            def runner():
                logger.info("etapa de teste executada")

            service.execute_automation("logs", run_id, runner)
            logs = service.get_execution_logs("logs")

            self.assertTrue(any("etapa de teste executada" in line for line in logs))

    def test_api_route_dispatches_cpfl_runner(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["DATABASE_PATH"] = str(Path(tmpdir) / "automations.db")
            for module_name in [
                "app",
                "automation_service",
                "automation_registry",
                "database",
                "config",
            ]:
                sys.modules.pop(module_name, None)

            import app
            import automation_service

            calls = []

            def runner():
                calls.append("cpfl")

            automation_service.AUTOMATIONS["cpfl-works"]["runner"] = runner

            response = app.app.test_client().post("/api/automations/cpfl-works/run")
            self.assertEqual(response.status_code, 202)

            for _ in range(20):
                if calls:
                    break
                time.sleep(0.05)

            for _ in range(20):
                if "cpfl-works" not in automation_service.running_automations:
                    break
                time.sleep(0.05)

            self.assertEqual(calls, ["cpfl"])

    def test_drive_upload_is_required(self):
        app, _ = self.load_app_with_temp_database()

        response = app.app.test_client().post("/api/automations/drive-update/run")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Selecione um arquivo .xlsx", response.get_json()["error"])

    def test_drive_upload_rejects_invalid_extensions(self):
        app, _ = self.load_app_with_temp_database()
        client = app.app.test_client()

        csv_response = client.post(
            "/api/automations/drive-update/run",
            data={"file": (BytesIO(b"a,b\n1,2\n"), "dados.csv")},
            content_type="multipart/form-data",
        )
        xls_response = client.post(
            "/api/automations/drive-update/run",
            data={"file": (BytesIO(b"fake"), "dados.xls")},
            content_type="multipart/form-data",
        )

        self.assertEqual(csv_response.status_code, 400)
        self.assertEqual(xls_response.status_code, 400)

    def test_drive_upload_rejects_fake_xlsx(self):
        app, _ = self.load_app_with_temp_database()

        response = app.app.test_client().post(
            "/api/automations/drive-update/run",
            data={"file": (BytesIO(b"not a workbook"), "dados.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("não é uma planilha .xlsx válida", response.get_json()["error"])

    def test_drive_upload_rejects_missing_required_columns(self):
        app, _ = self.load_app_with_temp_database()

        response = app.app.test_client().post(
            "/api/automations/drive-update/run",
            data={"file": (make_xlsx(headers=["COLUNA"], rows=[["valor"]]), "dados.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("colunas obrigatórias", response.get_json()["error"])

    def test_drive_valid_xlsx_dispatches_runner_with_uploaded_file_and_cleans_temp(self):
        app, service = self.load_app_with_temp_database()
        calls = []

        def runner(input_file):
            input_file = Path(input_file)
            calls.append((input_file.name, input_file.exists()))

        service.AUTOMATIONS["drive-update"]["runner"] = runner
        response = app.app.test_client().post(
            "/api/automations/drive-update/run",
            data={"file": (make_xlsx(), "backlog.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 202)
        self.wait_for_automation(service, "drive-update")

        self.assertEqual(calls, [("input.xlsx", True)])
        self.assertEqual(list(service.cleanup_stale_uploads.__globals__["UPLOAD_TEMP_DIR"].iterdir()), [])

    def test_drive_duplicate_execution_is_blocked_and_rejected_upload_is_not_kept(self):
        app, service = self.load_app_with_temp_database()
        started = Event()
        release = Event()

        def runner(input_file):
            started.set()
            release.wait(2)

        service.AUTOMATIONS["drive-update"]["runner"] = runner
        client = app.app.test_client()

        first_response = client.post(
            "/api/automations/drive-update/run",
            data={"file": (make_xlsx(), "primeiro.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(first_response.status_code, 202)
        self.assertTrue(started.wait(1))

        second_response = client.post(
            "/api/automations/drive-update/run",
            data={"file": (make_xlsx(), "segundo.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(second_response.status_code, 409)
        release.set()
        self.wait_for_automation(service, "drive-update")
        self.assertEqual(list(service.cleanup_stale_uploads.__globals__["UPLOAD_TEMP_DIR"].iterdir()), [])

    def test_drive_temporary_upload_is_removed_after_runner_error(self):
        app, service = self.load_app_with_temp_database()

        def runner(input_file):
            raise RuntimeError("erro controlado")

        service.AUTOMATIONS["drive-update"]["runner"] = runner
        response = app.app.test_client().post(
            "/api/automations/drive-update/run",
            data={"file": (make_xlsx(), "backlog.xlsx")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 202)
        self.wait_for_automation(service, "drive-update")
        self.assertEqual(list(service.cleanup_stale_uploads.__globals__["UPLOAD_TEMP_DIR"].iterdir()), [])

        runs = service.get_last_runs_by_automation()
        self.assertEqual(runs["drive-update"]["status"], "error")
        payload = service.list_automations()
        drive_payload = next(item for item in payload if item["id"] == "drive-update")
        self.assertFalse(any("File " in line for line in drive_payload["execution_logs"]))

    def test_drive_upload_size_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            service = reload_project_modules(Path(tmpdir) / "automations.db")
            import upload_service

            upload_service.MAX_UPLOAD_SIZE_BYTES = 10
            from werkzeug.datastructures import FileStorage

            file_storage = FileStorage(
                stream=make_xlsx(),
                filename="backlog.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            with self.assertRaises(upload_service.UploadValidationError) as context:
                upload_service.prepare_xlsx_upload(file_storage)

            self.assertEqual(context.exception.status_code, 413)

    def test_drive_upload_spreadsheet_row_limit_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            reload_project_modules(Path(tmpdir) / "automations.db")
            import upload_service
            from werkzeug.datastructures import FileStorage

            upload_service.MAX_SPREADSHEET_ROWS = 1
            rows = [
                [
                    "IMPLANTACAO DADOS",
                    "NÃO AGENDADO",
                    "2026-08-01",
                    "08:00",
                    "PAULINIA",
                    "12345",
                    "2026-07-31",
                    "Cliente",
                    "Rua Teste",
                    "Centro",
                ],
                [
                    "IMPLANTACAO DADOS",
                    "NÃO AGENDADO",
                    "2026-08-02",
                    "09:00",
                    "PAULINIA",
                    "12346",
                    "2026-07-31",
                    "Cliente",
                    "Rua Teste",
                    "Centro",
                ],
            ]
            file_storage = FileStorage(
                stream=make_xlsx(rows=rows),
                filename="backlog.xlsx",
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

            with self.assertRaises(upload_service.UploadValidationError) as context:
                upload_service.prepare_xlsx_upload(file_storage)

            self.assertEqual(context.exception.status_code, 422)
            self.assertIn("limite de linhas", str(context.exception))

    def load_app_with_temp_database(self):
        self.addCleanup(self.cleanup_loaded_modules)
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        database_path = Path(self.tempdir.name) / "automations.db"
        os.environ["DATABASE_PATH"] = str(database_path)
        os.environ["UPLOAD_TEMP_DIR"] = str(database_path.parent / "uploads")
        os.environ["MAX_UPLOAD_SIZE_MB"] = "20"

        for module_name in [
            "app",
            "automation_service",
            "automation_registry",
            "database",
            "config",
            "upload_service",
            "automations.drive.runner",
            "automations.drive.sheets_client",
            "automations.drive.spreadsheet_reader",
        ]:
            sys.modules.pop(module_name, None)

        import app
        import automation_service

        return app, automation_service

    def cleanup_loaded_modules(self):
        for module_name in [
            "app",
            "automation_service",
            "automation_registry",
            "database",
            "config",
            "upload_service",
        ]:
            sys.modules.pop(module_name, None)

    def wait_for_automation(self, service, automation_id):
        for _ in range(60):
            if automation_id not in service.running_automations:
                return
            time.sleep(0.05)
        self.fail(f"Automation {automation_id} did not finish")

    def test_removed_scraping_and_url_shortener_references(self):
        forbidden_terms = [
            "Beautiful" + "Soup",
            "b" + "s4",
            "tiny" + "url",
            "Tiny" + "URL",
            "TINY" + "_TOKEN",
        ]
        checked_files = [
            path
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
            and "tests" not in path.parts
            and path.name != ".env"
            and path.name != "README.md"
            and path.name != "uv.lock"
        ]

        content = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in checked_files
        )

        for term in forbidden_terms:
            self.assertNotIn(term, content)

    def test_missing_cpfl_config_reports_clear_error(self):
        from automations.works_cpfl.services.environment_validator import (
            EnvironmentValidationError,
            EnvironmentValidator,
        )

        with self.assertRaises(EnvironmentValidationError) as context:
            EnvironmentValidator(environ={}).validate()

        report = context.exception.report.render()
        self.assertIn("GOOGLE_CREDENTIALS_FILE ausente", report)
        self.assertIn("SEND_NUMBERS ausente", report)


if __name__ == "__main__":
    unittest.main()
