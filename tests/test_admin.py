from collections.abc import Iterator
from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from deauville import api
from deauville.errors import (
    ConflictError,
    InvalidValueError,
    NotFoundError,
    StorageError,
)
from deauville.models import Artist, Venue, Workshop
from deauville.service import FestivalService
from deauville.storage import JsonStorage

# E10 - The admin: writing through the API
SOURCE = Path(__file__).resolve().parents[1] / "data/festival.json"


@pytest.fixture
def data_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "festival.json"
    path.write_bytes(SOURCE.read_bytes())
    monkeypatch.setattr(api, "app", api.create_app(JsonStorage(path)))
    return path


@pytest.fixture
def client(data_file: Path) -> Iterator[TestClient]:
    with TestClient(api.app) as session:
        yield session


def solo_body(**changes: object) -> dict:
    return {
        "kind": "solo",
        "title": "Morning show",
        "venue": "le-kiosque",
        "start": "2027-06-13T11:00",
        "duration_minutes": 45,
        "artist": "nora-lebrun",
        "min_age": 0,
        **changes,
    }


def test_official_schedule_move_refuse_and_cancel_scenario(
    client: TestClient, data_file: Path
) -> None:
    created = client.post("/api/performances", json=solo_body())
    assert created.status_code == 201
    old_id = created.json()["id"]
    assert old_id == "le-kiosque-2027-06-13-1100"
    assert client.get(f"/api/performances/{old_id}").status_code == 200
    for body, message in [
        (solo_body(start="2027-06-13T11:30"), "Le Kiosque is busy"),
        (
            solo_body(venue="grand-casino", start="2027-06-13T12:00"),
            "Nora Lebrun is on stage",
        ),
    ]:
        before = data_file.read_bytes()
        response = client.post("/api/performances", json=body)
        assert response.status_code == 409 and message in response.json()["detail"]
        assert data_file.read_bytes() == before
    moved = client.put(
        f"/api/performances/{old_id}", json=solo_body(start="2027-06-13T12:00")
    )
    assert moved.status_code == 200
    new_id = moved.json()["id"]
    assert new_id == "le-kiosque-2027-06-13-1200"
    assert client.get(f"/api/performances/{old_id}").status_code == 404
    before = data_file.read_bytes()
    refused = client.put(
        f"/api/performances/{new_id}", json=solo_body(start="2027-06-13T15:00")
    )
    assert refused.status_code == 409
    assert data_file.read_bytes() == before
    assert (
        client.get(f"/api/performances/{new_id}").json()["start"] == "2027-06-13T12:00"
    )
    restarted = TestClient(api.app)
    assert restarted.get(f"/api/performances/{new_id}").status_code == 200
    deleted = client.delete(f"/api/performances/{new_id}")
    assert deleted.status_code == 204 and deleted.content == b""
    assert client.get(f"/api/performances/{new_id}").status_code == 404


def test_artist_creation_and_duplicate_slug(
    client: TestClient, data_file: Path
) -> None:
    response = client.post("/api/artists", json={"name": " Zoé Tanguy "})
    assert response.status_code == 201
    assert response.json() == {
        "slug": "zoe-tanguy",
        "name": "Zoé Tanguy",
        "bio": "",
        "photo_url": "",
    }
    before = data_file.read_bytes()
    response = client.post("/api/artists", json={"name": "zoe tanguy"})
    assert response.status_code == 409 and "already exists" in response.json()["detail"]
    assert data_file.read_bytes() == before
    assert JsonStorage(data_file).load().artist("zoe-tanguy").name == "Zoé Tanguy"


def test_registration_persists_and_rejects_duplicates_and_full_workshop(
    client: TestClient, data_file: Path
) -> None:
    identifier = "la-cabane-2027-06-12-1030"
    url = f"/api/performances/{identifier}/participants"
    response = client.post(url, json={"name": " New Participant "})
    assert response.status_code == 201
    assert response.json()["participants"][-1] == "New Participant"
    assert response.json()["places_left"] == 5
    before = data_file.read_bytes()
    response = client.post(url, json={"name": "new participant"})
    assert (
        response.status_code == 409
        and "already registered" in response.json()["detail"]
    )
    assert data_file.read_bytes() == before
    for index in range(5):
        assert (
            client.post(url, json={"name": f"Participant {index}"}).status_code == 201
        )
    before = data_file.read_bytes()
    response = client.post(url, json={"name": "One too many"})
    assert response.status_code == 409 and "full" in response.json()["detail"]
    assert data_file.read_bytes() == before
    assert JsonStorage(data_file).load().performance(identifier).places_left == 0


@pytest.mark.parametrize(
    "url, body",
    [
        ("/api/performances", {}),
        ("/api/performances", solo_body(kind="unknown")),
        ("/api/performances", solo_body(duration_minutes="45")),
        ("/api/performances", solo_body(duration_minutes=True)),
        ("/api/performances", solo_body(start="June 13")),
        ("/api/artists", {}),
        ("/api/artists", {"name": 123}),
        ("/api/performances/la-cabane-2027-06-12-1030/participants", {}),
    ],
)
def test_bad_body_shape_is_a_fastapi_422(
    client: TestClient, data_file: Path, url: str, body: dict
) -> None:
    before = data_file.read_bytes()
    response = client.post(url, json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert data_file.read_bytes() == before


@pytest.mark.parametrize(
    "body, status, message",
    [
        (solo_body(title=" "), 422, "non-empty"),
        (solo_body(duration_minutes=0), 422, "1 to 360"),
        (solo_body(min_age=19), 422, "0 to 18"),
        (solo_body(venue="unknown"), 404, "No venue"),
        (solo_body(artist="unknown"), 404, "No artist"),
        (solo_body(start="2027-06-14T08:00"), 409, "not a day"),
        (solo_body(start="2027-06-13T11:00+02:00"), 422, "local date and time"),
    ],
)
def test_domain_errors_have_correct_status_and_sentence(
    client: TestClient, data_file: Path, body: dict, status: int, message: str
) -> None:
    before = data_file.read_bytes()
    response = client.post("/api/performances", json=body)
    assert response.status_code == status
    assert message in response.json()["detail"]
    assert data_file.read_bytes() == before


def test_lineup_and_workshop_writes_use_subclass_rules(
    client: TestClient, data_file: Path
) -> None:
    lineup = {
        "kind": "lineup",
        "title": "Morning lineup",
        "venue": "le-kiosque",
        "start": "2027-06-13T08:00",
        "duration_minutes": 36,
        "host": "paul-kerbrat",
        "acts": ["nora-lebrun", "max-pellerin", "lea-fontaine"],
    }
    before = data_file.read_bytes()
    for changes in [
        {"acts": ["nora-lebrun"]},
        {"acts": ["nora-lebrun", "nora-lebrun"]},
        {"acts": ["paul-kerbrat", "nora-lebrun"]},
        {"duration_minutes": 35},
    ]:
        response = client.post("/api/performances", json={**lineup, **changes})
        assert response.status_code == 422
        assert data_file.read_bytes() == before
    assert client.post("/api/performances", json=lineup).status_code == 201
    workshop = {
        "kind": "workshop",
        "title": "Early workshop",
        "venue": "grand-casino",
        "start": "2027-06-13T08:00",
        "duration_minutes": 60,
        "teacher": "ines-moreau",
        "max_participants": 999,
    }
    response = client.post("/api/performances", json=workshop)
    assert response.status_code == 201 and response.json()["capacity"] == 650


def test_non_workshop_registration_and_unknown_ids(client: TestClient) -> None:
    response = client.post(
        "/api/performances/le-kiosque-2027-06-11-2330/participants",
        json={"name": "Alice"},
    )
    assert response.status_code == 422 and "not a workshop" in response.json()["detail"]
    assert client.delete("/api/performances/missing").status_code == 404
    assert client.put("/api/performances/missing", json=solo_body()).status_code == 404
    assert (
        client.post(
            "/api/performances/missing/participants", json={"name": "Alice"}
        ).status_code
        == 404
    )


def test_missing_damaged_and_invalid_data_files_return_500(
    client: TestClient, data_file: Path
) -> None:
    for damaged in ["{", "{}", "[]"]:
        data_file.write_text(damaged, encoding="utf-8")
        response = client.get("/api/festival")
        assert response.status_code == 500 and isinstance(
            response.json()["detail"], str
        )
    data_file.unlink()
    assert client.get("/api/festival").status_code == 500


def test_save_failure_returns_500_and_preserves_file(
    client: TestClient, data_file: Path
) -> None:
    before = data_file.read_bytes()
    with patch(
        "deauville.storage.os.replace",
        side_effect=PermissionError("Simulated failed save"),
    ):
        response = client.post("/api/performances", json=solo_body())
    assert response.status_code == 500
    assert data_file.read_bytes() == before


def test_admin_and_assets_are_served(client: TestClient) -> None:
    assert client.get("/admin/").status_code == 200
    assert "New performance" in client.get("/admin/").text
    assert client.get("/admin/admin.js").status_code == 200
    assert client.get("/admin/admin.css").status_code == 200


def test_frozen_objects_and_nested_collections_close_mutation_paths(
    data_file: Path,
) -> None:
    festival = JsonStorage(data_file).load()
    show = festival.performance("le-kiosque-2027-06-12-0100")
    workshop = festival.performance("la-cabane-2027-06-12-1030")
    for obj, field, value in [
        (show, "start", datetime.fromisoformat("2027-06-13T15:00")),
        (show.venue, "capacity", 9999),
        (show.host, "name", "Other"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(obj, field, value)
    for collection in [
        festival.performances,
        festival.venues,
        festival.artists,
        show.acts,
        workshop.participants,
    ]:
        with pytest.raises(AttributeError):
            collection.append("invalid")
    view = workshop.to_view()
    view["participants"].append("Only in the copy")
    assert "Only in the copy" not in workshop.participants


def test_refused_model_move_and_failed_save_leave_schedule_unchanged(
    data_file: Path,
) -> None:
    festival = JsonStorage(data_file).load()
    show = festival.performance("le-kiosque-2027-06-13-1500")
    new = replace(show, start=datetime.fromisoformat("2027-06-11T23:30"))
    before = festival.to_saved()
    file_before = data_file.read_bytes()
    with pytest.raises(ConflictError):
        FestivalService(JsonStorage(data_file)).update(show.id, new.to_saved())
    assert festival.to_saved() == before and data_file.read_bytes() == file_before
    new = replace(show, start=datetime.fromisoformat("2027-06-13T08:00"))
    with (
        patch(
            "deauville.storage.os.replace", side_effect=PermissionError("Save refused")
        ),
        pytest.raises(StorageError),
    ):
        FestivalService(JsonStorage(data_file)).update(show.id, new.to_saved())
    assert festival.to_saved() == before and data_file.read_bytes() == file_before


def test_forged_venue_capacity_cannot_bypass_real_capacity(data_file: Path) -> None:
    festival = JsonStorage(data_file).load()
    show = Workshop(
        title="Fake capacity",
        venue=Venue("La Cabane", 9999, "Fake"),
        start=datetime.fromisoformat("2027-06-13T08:00"),
        duration_minutes=60,
        teacher=festival.artist("ines-moreau"),
        max_participants=100,
        participants=[f"Person {index}" for index in range(41)],
    )
    with pytest.raises(ConflictError, match="only 40 places"):
        festival.add(show)


def test_error_family_distinguishes_missing_invalid_and_conflict(
    data_file: Path,
) -> None:
    festival = JsonStorage(data_file).load()
    with pytest.raises(NotFoundError):
        festival.artist("missing")
    with pytest.raises(InvalidValueError):
        Artist(" ")
    with pytest.raises(ConflictError):
        festival.add_artist(Artist("Nora Lebrun"))
