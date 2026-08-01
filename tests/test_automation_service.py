import importlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def reload_project_modules(database_path):
    os.environ["DATABASE_PATH"] = str(database_path)
    for module_name in [
        "app",
        "automation_service",
        "automation_registry",
        "database",
        "config",
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
