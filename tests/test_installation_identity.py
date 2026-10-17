"""The native client must identify its destination before reusing a session."""
import concurrent.futures
import json
import uuid

import pytest

from mia import identity, operations
from test_app import client
from test_operations import managed


def test_public_identity_is_stable_before_and_after_owner_setup(client, monkeypatch):
    browser, directory = client
    monkeypatch.delenv("MIA_OPERATIONS_ROOT", raising=False)
    first = browser.get("/api/installation")
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    result = first.json()
    assert str(uuid.UUID(result["installation_id"])) == result["installation_id"]
    assert result["desktop_protocol"] == 1 and result["cookie_secure"] is False
    assert browser.get("/api/installation").json()["installation_id"] == result["installation_id"]
    assert set(json.loads((directory / "installation-identity.json").read_text())) == {"format", "installation_id"}
    assert (directory / "installation-identity.json").stat().st_mode & 0o077 == 0
    monkeypatch.setenv("MIA_COOKIE_SECURE", "true")
    secure = browser.get("/api/installation").json()
    assert secure["cookie_secure"] and secure["transport_policy"] == "https_required"
    assert secure["installation_id"] == result["installation_id"]


def test_concurrent_manual_identity_creation_has_one_result(tmp_path, monkeypatch):
    monkeypatch.setenv("MIA_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("MIA_OPERATIONS_ROOT", raising=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as workers:
        values = list(workers.map(lambda _: identity.installation_id(), range(24)))
    assert len(set(values)) == 1


def test_managed_identity_survives_data_destination_changes(managed, tmp_path, monkeypatch):
    configuration = operations._read(managed.root / "installation.json")
    assert str(uuid.UUID(configuration["installation_id"])) == configuration["installation_id"]
    monkeypatch.setenv("MIA_OPERATIONS_ROOT", str(managed.root))
    for name in ("data-before", "data-after"):
        directory = tmp_path / name
        directory.mkdir()
        monkeypatch.setenv("MIA_DATA_DIR", str(directory))
        assert identity.installation_id() == configuration["installation_id"]
        assert not (directory / "installation-identity.json").exists()


def test_manual_identity_refuses_link_without_reading_or_replacing_it(tmp_path, monkeypatch):
    monkeypatch.delenv("MIA_OPERATIONS_ROOT", raising=False)
    monkeypatch.setenv("MIA_DATA_DIR", str(tmp_path))
    target = tmp_path / "original.json"
    target.write_text('{"private":"synthetic material"}')
    path = tmp_path / "installation-identity.json"
    path.symlink_to(target)
    with pytest.raises(ValueError, match="links"):
        identity.installation_id()
    assert target.read_text() == '{"private":"synthetic material"}'
