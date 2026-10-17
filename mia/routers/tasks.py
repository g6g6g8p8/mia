from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo
from fastapi import APIRouter, HTTPException
from ..db import connect, transaction
from ..security import iso
from .. import experience

from ..http_dependencies import Owner, audit

from ..http_schemas import TaskInput, TaskPatch


router = APIRouter()


@router.get("/api/tasks")
def list_tasks(owner: Owner, status: Literal["open", "done", "all"] = "open", area_id: str | None = None) -> list[dict]:
    filters, values = ["tasks.owner_id = ?"], [owner["id"]]
    if status != "all":
        filters.append("tasks.status = ?")
        values.append(status)
    if area_id:
        filters.append("tasks.area_id = ?")
        values.append(area_id)
    with connect() as db:
        rows = db.execute(
            f"""
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE {' AND '.join(filters)}
            ORDER BY tasks.status, tasks.due_date IS NULL, tasks.due_date, tasks.priority DESC, tasks.created_at DESC
            """,
            values,
        ).fetchall()
        return [dict(row) for row in rows]


@router.post("/api/tasks", status_code=201)
def create_task(payload: TaskInput, owner: Owner) -> dict:
    task_id, created = str(uuid.uuid4()), iso()
    with transaction() as db:
        if payload.area_id:
            area = db.execute("SELECT 1 FROM areas WHERE id = ? AND owner_id = ?", (payload.area_id, owner["id"])).fetchone()
            if not area:
                raise HTTPException(404, "Área não encontrada")
        db.execute(
            """
            INSERT INTO tasks(id, owner_id, area_id, title, notes, due_date, priority, status, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,'open',?,?)
            """,
            (task_id, owner["id"], payload.area_id, payload.title, payload.notes.strip(), payload.due_date.isoformat() if payload.due_date else None, payload.priority, created, created),
        )
        audit(db, owner["id"], "task.created", "task", task_id)
    return get_task(task_id, owner)


def get_task(task_id: str, owner: dict) -> dict:
    with connect() as db:
        row = db.execute(
            """
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.id = ? AND tasks.owner_id = ?
            """,
            (task_id, owner["id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Tarefa não encontrada")
        return dict(row)


@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskPatch, owner: Owner) -> dict:
    updated = iso()
    with transaction() as db:
        exists = db.execute("SELECT status FROM tasks WHERE id = ? AND owner_id = ?", (task_id, owner["id"])).fetchone()
        if not exists:
            raise HTTPException(404, "Tarefa não encontrada")
        completed = updated if payload.status == "done" else None
        db.execute(
            "UPDATE tasks SET status = ?, completed_at = ?, updated_at = ? WHERE id = ? AND owner_id = ?",
            (payload.status, completed, updated, task_id, owner["id"]),
        )
        audit(db, owner["id"], f"task.{payload.status}", "task", task_id)
    return get_task(task_id, owner)


@router.get("/api/today")
def today(owner: Owner) -> dict:
    today_iso = datetime.now(ZoneInfo(owner["timezone"])).date().isoformat()
    with connect() as db:
        areas = db.execute(
            """
            SELECT areas.id, areas.name, areas.description, areas.color,
                   COUNT(tasks.id) FILTER (WHERE tasks.status = 'open') AS open_tasks
            FROM areas LEFT JOIN tasks ON tasks.area_id = areas.id
            WHERE areas.owner_id = ?
            GROUP BY areas.id ORDER BY lower(areas.name)
            """,
            (owner["id"],),
        ).fetchall()
        tasks = db.execute(
            """
            SELECT tasks.*, areas.name AS area_name, areas.color AS area_color
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.owner_id = ? AND tasks.status = 'open'
            ORDER BY
              CASE WHEN tasks.due_date IS NOT NULL AND tasks.due_date < ? THEN 0
                   WHEN tasks.due_date = ? THEN 1 ELSE 2 END,
              tasks.priority DESC, tasks.due_date IS NULL, tasks.due_date, tasks.created_at
            LIMIT 12
            """,
            (owner["id"], today_iso, today_iso),
        ).fetchall()
        overdue = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE owner_id = ? AND status = 'open' AND due_date < ?",
            (owner["id"], today_iso),
        ).fetchone()[0]
        due_today = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE owner_id = ? AND status = 'open' AND due_date = ?",
            (owner["id"], today_iso),
        ).fetchone()[0]
    return {
        "date": today_iso,
        "owner": owner,
        "overdue": overdue,
        "due_today": due_today,
        "areas": [dict(row) for row in areas],
        "tasks": [dict(row) for row in tasks],
        "focus": experience.focus(owner),
    }
