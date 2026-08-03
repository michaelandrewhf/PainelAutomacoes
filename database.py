import sqlite3
from datetime import UTC, datetime

from config import DATABASE_PATH


def get_connection():
    database_path = DATABASE_PATH
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_db():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS automation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                automation_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL CHECK (status IN ('running', 'success', 'error')),
                duration_seconds REAL,
                error_message TEXT
            )
            """)
        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_automation_runs_latest
            ON automation_runs (automation_id, id DESC)
            """)


def create_run(automation_id, started_at):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO automation_runs (automation_id, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (automation_id, started_at),
        )
        return cursor.lastrowid


def finish_run(run_id, finished_at, status, error_message=None):
    with get_connection() as connection:
        run = connection.execute(
            "SELECT started_at FROM automation_runs WHERE id = ?",
            (run_id,),
        ).fetchone()

        if run is None:
            return

        duration_seconds = calculate_duration_seconds(run["started_at"], finished_at)
        connection.execute(
            """
            UPDATE automation_runs
            SET finished_at = ?,
                status = ?,
                duration_seconds = ?,
                error_message = ?
            WHERE id = ?
            """,
            (finished_at, status, duration_seconds, error_message, run_id),
        )


def finish_interrupted_runs(error_message):
    finished_at = datetime.now(UTC).replace(microsecond=0).isoformat()

    with get_connection() as connection:
        running_runs = connection.execute(
            "SELECT id, started_at FROM automation_runs WHERE status = 'running'"
        ).fetchall()

        for run in running_runs:
            duration_seconds = calculate_duration_seconds(
                run["started_at"], finished_at
            )
            connection.execute(
                """
                UPDATE automation_runs
                SET finished_at = ?,
                    status = 'error',
                    duration_seconds = ?,
                    error_message = ?
                WHERE id = ?
                """,
                (finished_at, duration_seconds, error_message, run["id"]),
            )

        return len(running_runs)


def get_last_runs_by_automation():
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT ar.*
            FROM automation_runs ar
            INNER JOIN (
                SELECT automation_id, MAX(id) AS max_id
                FROM automation_runs
                GROUP BY automation_id
            ) latest
            ON latest.max_id = ar.id
            """).fetchall()

    return {row["automation_id"]: dict(row) for row in rows}


def calculate_duration_seconds(started_at, finished_at):
    started = datetime.fromisoformat(started_at)
    finished = datetime.fromisoformat(finished_at)
    return max(0, (finished - started).total_seconds())
