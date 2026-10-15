from fastapi import APIRouter, HTTPException
from typing import Annotated, Literal

from mia.app import TaskInput, TaskPatch, Owner, audit, get_task as _placeholder_get_task
from mia.db import connect, transaction
from mia import knowledge, harness, personalization
from zoneinfo import ZoneInfo
from datetime import datetime

router = APIRouter()


@router.get("/api/tasks")
def list_tasks(owner: Annotated[dict, Owner], status: Literal["open", "done", "all"] = "open", area_id: str | None = None) -> list[dict]:
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
def create_task(payload: TaskInput, owner: Annotated[dict, Owner]) -> dict:
    import uuid

    task_id, created = str(uuid.uuid4()), __import__('mia').app.iso()
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
def update_task(task_id: str, payload: TaskPatch, owner: Annotated[dict, Owner]) -> dict:
    updated = __import__('mia').app.iso()
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
def today(owner: Annotated[dict, Owner]) -> dict:
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
    }


@router.get("/api/search")
def search(q: str, owner: Annotated[dict, Owner]) -> dict:
    query = q.strip()
    if len(query) < 2:
        return {"query": query, "results": []}
    escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
    pattern = f"%{escaped}%"
    with connect() as db:
        tasks = db.execute(
            """
            SELECT tasks.id, tasks.title, tasks.notes, tasks.status, tasks.due_date,
                   areas.name AS area_name, 'task' AS type
            FROM tasks LEFT JOIN areas ON areas.id = tasks.area_id
            WHERE tasks.owner_id = ? AND (tasks.title LIKE ? ESCAPE '!' OR tasks.notes LIKE ? ESCAPE '!')
            ORDER BY tasks.updated_at DESC LIMIT 30
            """,
            (owner["id"], pattern, pattern),
        ).fetchall()
        areas = db.execute(
            """
            SELECT id, name AS title, description AS notes, NULL AS status, NULL AS due_date,
                   name AS area_name, 'area' AS type
            FROM areas
            WHERE owner_id = ? AND (name LIKE ? ESCAPE '!' OR description LIKE ? ESCAPE '!')
            ORDER BY updated_at DESC LIMIT 20
            """,
            (owner["id"], pattern, pattern),
        ).fetchall()
    documents=[{'id':r['id'],'title':r['title'],'notes':r['content'],'type':'document','area_name':None,'due_date':None} for r in knowledge.retrieve(owner,None,query,10)]
    return {"query": query, "results": [dict(row) for row in [*tasks, *areas]]+documents}


@router.get("/api/export")
def export_data(owner: Annotated[dict, Owner]):
    with connect() as db:
        areas = [dict(row) for row in db.execute("SELECT * FROM areas WHERE owner_id = ? ORDER BY name", (owner["id"],))]
        tasks = [dict(row) for row in db.execute("SELECT * FROM tasks WHERE owner_id = ? ORDER BY created_at", (owner["id"],))]
        documents = [dict(row) for row in db.execute("SELECT * FROM documents WHERE owner_id=?",(owner['id'],))]
        profile = db.execute("SELECT goal,completed FROM onboarding WHERE owner_id=?",(owner['id'],)).fetchone()
    payload = {
        "format": "mia-export",
        "version": 1,
        "exported_at": __import__('mia').app.iso(),
        "owner": {"name": owner["name"], "email": owner["email"], "timezone": owner["timezone"]},
        "areas": areas,
        "tasks": tasks,
        "runs": harness.list_runs(owner, all_runs=True),
        "documents": documents,
        "onboarding": dict(profile) if profile else None,
        "personal_context": personalization.get_state(owner),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("mia-export.json", json.dumps(payload, ensure_ascii=False, indent=2))
        archive.writestr("README.txt", "Mia export v1. Keep this file private.\n")
    buffer.seek(0)
    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="mia-export.zip"'},
    )
