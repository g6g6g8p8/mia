from fastapi import APIRouter, HTTPException
from typing import Annotated

from mia.app import AreaInput, Owner, audit
from mia.db import connect, transaction
from mia import knowledge

router = APIRouter()


@router.get("/api/areas")
def list_areas(owner: Annotated[dict, Owner]) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            """
            SELECT areas.*, COUNT(tasks.id) FILTER (WHERE tasks.status = 'open') AS open_tasks
            FROM areas LEFT JOIN tasks ON tasks.area_id = areas.id
            WHERE areas.owner_id = ?
            GROUP BY areas.id ORDER BY lower(areas.name)
            """,
            (owner["id"],),
        ).fetchall()
        return [dict(row) for row in rows]


@router.post("/api/areas", status_code=201)
def create_area(payload: AreaInput, owner: Annotated[dict, Owner]) -> dict:
    import uuid

    area_id, created = str(uuid.uuid4()), __import__('mia').app.iso()
    try:
        with transaction() as db:
            db.execute(
                "INSERT INTO areas(id, owner_id, name, description, color, created_at, updated_at) VALUES(?,?,?,?,?,?,?)",
                (area_id, owner["id"], payload.name, payload.description.strip(), payload.color, created, created),
            )
            audit(db, owner["id"], "area.created", "area", area_id)
    except Exception as exc:
        raise HTTPException(409, "Já existe uma área com esse nome") from exc
    with connect() as db:
        return dict(db.execute("SELECT * FROM areas WHERE id = ?", (area_id,)).fetchone())


@router.put('/api/areas/{area_id}')
def update_area(area_id: str, payload: AreaInput, owner: Annotated[dict, Owner]) -> dict:
    with transaction(immediate=True) as db:
        if not db.execute('SELECT 1 FROM areas WHERE id=? AND owner_id=?',(area_id,owner['id'])).fetchone():
            raise HTTPException(404, 'Área não encontrada')
        names = db.execute('SELECT name FROM areas WHERE owner_id=? AND id!=?',(owner['id'],area_id))
        if any(knowledge.normalized(row[0])==knowledge.normalized(payload.name) for row in names):
            raise HTTPException(409, 'Já existe uma área com esse nome')
        db.execute('UPDATE areas SET name=?,description=?,color=?,updated_at=? WHERE id=? AND owner_id=?',(payload.name,payload.description.strip(),payload.color,__import__('mia').app.iso(),area_id,owner['id']))
        audit(db,owner['id'],'area.updated','area',area_id)
        return dict(db.execute('SELECT * FROM areas WHERE id=?',(area_id,)).fetchone())
