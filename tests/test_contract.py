import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from deauville.api import create_app
from deauville.storage import JsonStorage


# E12 - The whole contract, tested
@pytest.fixture
def contract_file(tmp_path: Path) -> Path:
    path = tmp_path / "festival.json"
    source = Path(__file__).resolve().parents[1] / "data/festival.json"
    path.write_bytes(source.read_bytes())
    return path


@pytest.fixture
def client(contract_file: Path) -> Iterator[TestClient]:
    with TestClient(create_app(JsonStorage(contract_file))) as session:
        yield session


def show_body(**changes: object) -> dict:
    return {
        "kind": "solo",
        "title": "Contract show",
        "artist": "nora-lebrun",
        "venue": "le-kiosque",
        "start": "2027-06-13T08:00",
        "duration_minutes": 45,
        "min_age": 16,
        "description": "A test show.",
        **changes,
    }


def test_festival_venues_and_artists_match_contract(
    client: TestClient, contract_file: Path
) -> None:
    raw = json.loads(contract_file.read_text(encoding="utf-8"))
    assert client.get("/api/festival").json() == {
        "name": raw["name"],
        "first_day": "2027-06-10",
        "last_day": "2027-06-13",
        "days": ["2027-06-10", "2027-06-11", "2027-06-12", "2027-06-13"],
    }
    venues = client.get("/api/venues").json()
    assert len(venues) == 4
    assert [venue["name"] for venue in venues] == [
        venue["name"] for venue in raw["venues"]
    ]
    assert all(
        set(venue) == {"slug", "name", "capacity", "address"} for venue in venues
    )
    artists = client.get("/api/artists").json()
    assert len(artists) == 12
    assert [artist["slug"] for artist in artists] == sorted(
        artist["slug"] for artist in artists
    )
    assert artists[0]["name"] == "Élodie Marchal"
    assert all(
        set(artist) == {"slug", "name", "bio", "photo_url"} for artist in artists
    )


@pytest.mark.parametrize(
    "query, count",
    [
        ("", 23),
        ("?day=2027-06-11", 7),
        ("?venue=le-kiosque", 7),
        ("?day=2027-06-11&venue=le-kiosque", 3),
        ("?day=2027-06-10&venue=la-cabane", 0),
        ("?day=2030-01-01", 0),
    ],
)
def test_programme_filters_and_order(
    client: TestClient, query: str, count: int
) -> None:
    response = client.get("/api/programme" + query)
    assert response.status_code == 200
    shows = response.json()
    assert len(shows) == count
    assert [(show["start"], show["venue_name"]) for show in shows] == sorted(
        (show["start"], show["venue_name"]) for show in shows
    )
    if "day=2027-06-11" in query:
        assert shows[-1]["title"] == "After Hours"


def test_all_performance_views_have_correct_common_and_specific_fields(
    client: TestClient,
) -> None:
    common = {
        "id",
        "kind",
        "title",
        "venue",
        "venue_name",
        "start",
        "end",
        "duration_minutes",
        "festival_day",
        "description",
        "summary",
        "capacity",
        "artists",
    }
    specific = {
        "solo": {"artist", "min_age"},
        "lineup": {"host", "acts"},
        "workshop": {"teacher", "max_participants", "participants", "places_left"},
    }
    shows = client.get("/api/programme").json()
    for show in shows:
        assert set(show) == common | specific[show["kind"]]
        assert all(set(artist) == {"slug", "name"} for artist in show["artists"])
        assert datetime.fromisoformat(show["end"]) > datetime.fromisoformat(
            show["start"]
        )
        assert client.get(f"/api/performances/{show['id']}").json() == show


def test_artist_detail_includes_every_role_in_order(client: TestClient) -> None:
    detail = client.get("/api/artists/max-pellerin").json()
    assert detail["name"] == "Max Pellerin"
    assert [show["title"] for show in detail["performances"]] == [
        "Opening Gala",
        "Late Laughs",
        "Deauville Comedy Club",
        "Closing Gala",
    ]
    assert len(client.get("/api/artists/ines-moreau").json()["performances"]) == 4


@pytest.mark.parametrize(
    "path, message",
    [
        ("/api/artists/missing", "No artist"),
        ("/api/performances/missing", "No performance"),
        ("/api/programme?venue=missing", "No venue"),
    ],
)
def test_read_not_found_is_a_sentence(
    client: TestClient, path: str, message: str
) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert message in response.json()["detail"]


@pytest.mark.parametrize("path", ["/api/programme?day=June-11", "/api/now?at=Friday"])
def test_bad_query_shape_is_a_422_problem_list(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


def test_now_empty_and_next_three_behaviour(client: TestClient) -> None:
    assert client.get("/api/now").status_code == 200
    response = client.get("/api/now?at=2027-06-01T10:00").json()
    assert response["at"] == "2027-06-01T10:00"
    assert response["now_playing"] == [] and len(response["up_next"]) == 3
    response = client.get("/api/now?at=2027-07-01T10:00").json()
    assert response["now_playing"] == [] and response["up_next"] == []


def test_default_now_uses_festival_time_in_paris(client: TestClient) -> None:
    with patch("deauville.api.datetime") as clock:
        clock.now.return_value = datetime.fromisoformat("2027-06-12T01:30+02:00")
        response = client.get("/api/now")
    assert clock.now.call_args.args[0].key == "Europe/Paris"
    assert response.status_code == 200
    assert response.json()["at"] == "2027-06-12T01:30"
    assert response.json()["now_playing"][0]["title"] == "After Hours"


def test_put_same_slot_and_changed_venue_id_persist(
    client: TestClient, contract_file: Path
) -> None:
    response = client.post("/api/performances", json=show_body())
    assert response.status_code == 201
    original_id = response.json()["id"]
    response = client.put(
        f"/api/performances/{original_id}", json=show_body(title="Updated title")
    )
    assert response.status_code == 200
    assert response.json()["id"] == original_id
    response = client.put(
        f"/api/performances/{original_id}", json=show_body(venue="grand-casino")
    )
    assert response.status_code == 200
    new_id = response.json()["id"]
    assert new_id == "grand-casino-2027-06-13-0800"
    assert client.get(f"/api/performances/{original_id}").status_code == 404
    assert (
        TestClient(create_app(JsonStorage(contract_file)))
        .get(f"/api/performances/{new_id}")
        .status_code
        == 200
    )


def test_delete_twice_returns_204_then_404(client: TestClient) -> None:
    identifier = client.post("/api/performances", json=show_body()).json()["id"]
    response = client.delete(f"/api/performances/{identifier}")
    assert response.status_code == 204 and response.content == b""
    response = client.delete(f"/api/performances/{identifier}")
    assert response.status_code == 404 and "No performance" in response.json()["detail"]


@pytest.mark.parametrize("operation", ["add", "update", "cancel", "artist", "register"])
def test_every_write_handles_save_failure_without_changing_data(
    client: TestClient,
    contract_file: Path,
    operation: str,
) -> None:
    before = contract_file.read_bytes()
    with patch(
        "deauville.storage.os.replace", side_effect=PermissionError("Read only")
    ):
        if operation == "add":
            response = client.post("/api/performances", json=show_body())
        elif operation == "update":
            response = client.put(
                "/api/performances/le-kiosque-2027-06-13-1500", json=show_body()
            )
        elif operation == "cancel":
            response = client.delete("/api/performances/le-kiosque-2027-06-13-1500")
        elif operation == "artist":
            response = client.post("/api/artists", json={"name": "Unsaved artist"})
        else:
            response = client.post(
                "/api/performances/la-cabane-2027-06-12-1030/participants",
                json={"name": "Unsaved participant"},
            )
    assert response.status_code == 500
    assert isinstance(response.json()["detail"], str)
    assert contract_file.read_bytes() == before


def test_openapi_documents_every_contract_operation(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/festival": {"get"},
        "/api/venues": {"get"},
        "/api/artists": {"get", "post"},
        "/api/artists/{slug}": {"get"},
        "/api/programme": {"get"},
        "/api/now": {"get"},
        "/api/performances": {"post"},
        "/api/performances/{identifier}": {"get", "put", "delete"},
        "/api/performances/{identifier}/participants": {"post"},
    }
    assert {path: set(operations) for path, operations in paths.items()} == expected
