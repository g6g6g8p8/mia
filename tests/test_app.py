from __future__ import annotations

import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MIA_DATA_DIR", str(tmp_path))
    import mia.app as mia_app

    with TestClient(mia_app.app) as test_client:
        yield test_client, tmp_path


def setup_payload():
    return {
        "name": "Pessoa Piloto",
        "email": "piloto@example.test",
        "timezone": "America/Sao_Paulo",
        "password": "senha-forte-123",
        "area_name": "Projetos",
        "area_description": "Entregas em andamento",
    }


def test_complete_local_flow_and_export(client):
    browser, _ = client
    assert browser.get("/api/status").json()["configured"] is False

    setup = browser.post("/api/setup", json=setup_payload())
    assert setup.status_code == 201
    assert browser.get("/api/status").json()["configured"] is True

    areas = browser.get("/api/areas").json()
    assert len(areas) == 1
    assert areas[0]["name"] == "Projetos"

    task = browser.post(
        "/api/tasks",
        json={
            "title": "Validar primeira entrega",
            "notes": "Checar instalação e busca",
            "area_id": areas[0]["id"],
            "due_date": "2030-01-02",
            "priority": 3,
        },
    )
    assert task.status_code == 201
    task_data = task.json()

    today = browser.get("/api/today").json()
    assert [item["title"] for item in today["tasks"]] == ["Validar primeira entrega"]

    search = browser.get("/api/search", params={"q": "instalação"}).json()
    assert search["results"][0]["id"] == task_data["id"]

    done = browser.patch(f"/api/tasks/{task_data['id']}", json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"
    assert browser.get("/api/tasks").json() == []

    exported = browser.get("/api/export")
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        payload = json.loads(archive.read("mia-export.json"))
    assert payload["format"] == "mia-export"
    assert payload["areas"][0]["name"] == "Projetos"
    assert payload["tasks"][0]["status"] == "done"
    assert "password_hash" not in json.dumps(payload)


def test_authentication_and_setup_are_server_enforced(client):
    browser, _ = client
    setup = browser.post("/api/setup", json=setup_payload())
    assert setup.status_code == 201
    assert browser.post("/api/setup", json=setup_payload()).status_code == 409

    anonymous = TestClient(browser.app)
    assert anonymous.get("/api/today").status_code == 401
    assert anonymous.post("/api/login", json={"password": "errada"}).status_code == 401
    assert anonymous.post("/api/login", json={"password": "senha-forte-123"}).status_code == 200
    assert anonymous.get("/api/today").status_code == 200

    wrong_origin = anonymous.post(
        "/api/areas",
        json={"name": "Bloqueada", "description": "", "color": "slate"},
        headers={"Origin": "https://evil.example"},
    )
    assert wrong_origin.status_code == 403


def test_setup_rejects_invalid_timezone(client):
    browser, _ = client
    payload = setup_payload()
    payload["timezone"] = "Nowhere/Invalid"
    assert browser.post("/api/setup", json=payload).status_code == 422


def test_data_survives_new_app_instance(client, monkeypatch):
    browser, data_dir = client
    assert browser.post("/api/setup", json=setup_payload()).status_code == 201
    area_id = browser.get("/api/areas").json()[0]["id"]
    assert browser.post("/api/tasks", json={"title": "Persistir", "area_id": area_id}).status_code == 201

    monkeypatch.setenv("MIA_DATA_DIR", str(data_dir))
    with TestClient(browser.app) as restarted:
        assert restarted.post("/api/login", json={"password": "senha-forte-123"}).status_code == 200
        tasks = restarted.get("/api/tasks").json()
        assert [task["title"] for task in tasks] == ["Persistir"]


def test_database_has_no_default_or_fixture_content(client):
    _, data_dir = client
    with sqlite3.connect(data_dir / "mia.db") as db:
        assert db.execute("SELECT COUNT(*) FROM owner").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM areas").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0

