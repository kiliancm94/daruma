import sqlite3
import uuid
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


class TaskRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        name: str,
        prompt: str,
        cron_expression: str | None = None,
        allowed_tools: str | None = None,
        enabled: bool = True,
    ) -> dict:
        task_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            """INSERT INTO tasks (id, name, prompt, cron_expression, allowed_tools, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (task_id, name, prompt, cron_expression, allowed_tools, int(enabled), now, now),
        )
        self.conn.commit()
        return _row_to_dict(self.get(task_id))

    def get(self, task_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return _row_to_dict(row)

    def get_by_name(self, name: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM tasks WHERE name = ?", (name,)).fetchone()
        return _row_to_dict(row)

    def list(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    _UPDATABLE_FIELDS = {"name", "prompt", "cron_expression", "allowed_tools", "enabled"}

    def update(self, task_id: str, **fields) -> dict | None:
        if not fields:
            return self.get(task_id)
        fields = {k: v for k, v in fields.items() if k in self._UPDATABLE_FIELDS}
        if "enabled" in fields and fields["enabled"] is not None:
            fields["enabled"] = int(fields["enabled"])
        updates = {k: v for k, v in fields.items() if v is not None}
        if not updates:
            return self.get(task_id)
        updates["updated_at"] = _now()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [task_id]
        self.conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", values)
        self.conn.commit()
        return self.get(task_id)

    def delete(self, task_id: str) -> bool:
        cursor = self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.conn.commit()
        return cursor.rowcount > 0


class RunRepo:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, task_id: str, trigger: str) -> dict:
        run_id = str(uuid.uuid4())
        now = _now()
        self.conn.execute(
            """INSERT INTO runs (id, task_id, trigger, status, started_at)
               VALUES (?, ?, ?, 'running', ?)""",
            (run_id, task_id, trigger, now),
        )
        self.conn.commit()
        return _row_to_dict(self.get(run_id))

    def get(self, run_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row_to_dict(row)

    def complete(
        self, run_id: str, status: str, stdout: str, stderr: str, exit_code: int
    ) -> dict | None:
        now = _now()
        run = self.get(run_id)
        if run is None:
            return None
        started = datetime.fromisoformat(run["started_at"])
        finished = datetime.fromisoformat(now)
        duration_ms = int((finished - started).total_seconds() * 1000)
        self.conn.execute(
            """UPDATE runs
               SET status = ?, finished_at = ?, duration_ms = ?,
                   stdout = ?, stderr = ?, exit_code = ?
               WHERE id = ?""",
            (status, now, duration_ms, stdout, stderr, exit_code, run_id),
        )
        self.conn.commit()
        return _row_to_dict(self.get(run_id))

    def last_run(self, task_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY started_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        return _row_to_dict(row)

    def list(self, task_id: str | None = None) -> list[dict]:
        if task_id:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE task_id = ? ORDER BY started_at DESC",
                (task_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs ORDER BY started_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]
