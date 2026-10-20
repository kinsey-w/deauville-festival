from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from deauville import api
from deauville.storage import JsonStorage


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    source = Path(__file__).resolve().parents[1] / "data/festival.json"
    path = tmp_path / "festival.json"
    path.write_bytes(source.read_bytes())
    with TestClient(api.create_app(JsonStorage(path))) as session:
        yield session


# E08 - The festival holds the rules, and tests prove it
@pytest.mark.parametrize(
    "moment, playing, upcoming",
    [
        (
            "2027-06-11T21:00",
            ["Tall Tales"],
            ["Straight Face", "Late Laughs", "After Hours"],
        ),
        (
            "2027-06-12T01:30",
            ["After Hours"],
            ["Stand-up Lab", "Brunch & Punchlines", "New Faces"],
        ),
    ],
)
def test_now_response_contains_complete_performances(
    client: TestClient, moment: str, playing: list[str], upcoming: list[str]
) -> None:
    result = client.get("/api/now", params={"at": moment}).json()
    assert result["at"] == moment
    assert [show["title"] for show in result["now_playing"]] == playing
    assert [show["title"] for show in result["up_next"]] == upcoming
    assert all("id" in show and "end" in show for show in result["up_next"])


def test_now_rejects_timezone_aware_input(client: TestClient) -> None:
    response = client.get("/api/now", params={"at": "2027-06-11T21:00+00:00"})
    assert response.status_code == 422
    assert "without a time zone" in response.json()["detail"]


def test_programme_and_artist_pages_keep_working(client: TestClient) -> None:
    assert len(client.get("/api/programme", params={"venue": "le-kiosque"}).json()) == 7
    assert len(client.get("/api/artists/max-pellerin").json()["performances"]) == 4
    assert (
        client.get("/api/performances/le-kiosque-2027-06-12-0100").json()[
            "festival_day"
        ]
        == "2027-06-11"
    )
