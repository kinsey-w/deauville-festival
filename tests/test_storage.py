from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from deauville.api import create_app
from deauville.cli import run_command
from deauville.errors import StorageError
from deauville.models import Artist
from deauville.service import FestivalService
from deauville.storage import (
    FestivalStorage,
    JsonStorage,
    MemoryStorage,
    default_storage,
)

# E11 - A real package
SOURCE = Path(__file__).resolve().parents[1] / "data/festival.json"


@pytest.fixture(params=["json", "memory"])
def storage(request: pytest.FixtureRequest, tmp_path: Path) -> FestivalStorage:
    festival = JsonStorage(SOURCE).load()
    if request.param == "memory":
        return MemoryStorage(festival)
    storage = JsonStorage(tmp_path / "festival.json")
    storage.save(festival)
    return storage


def test_storage_interface_is_abstract() -> None:
    with pytest.raises(TypeError):
        FestivalStorage()


def test_service_works_with_either_storage(storage: FestivalStorage) -> None:
    service = FestivalService(storage)
    show = service.add(
        {
            "kind": "solo",
            "title": "Morning Coffee",
            "venue": "la-cabane",
            "artist": "karim-benali",
            "start": "2027-06-13T08:00",
            "duration_minutes": 30,
        }
    )
    assert len(storage.load().performances) == 24
    assert service.cancel(show.id) == "Morning Coffee"
    assert len(storage.load().performances) == 23


def test_loaded_festivals_are_independent(storage: FestivalStorage) -> None:
    first = storage.load()
    first.add_artist(Artist("Local only"))
    assert storage.load().find_artist("local-only") is None
    storage.save(first)
    assert storage.load().artist("local-only").name == "Local only"


def test_api_receives_storage_and_persists_changes(storage: FestivalStorage) -> None:
    client = TestClient(create_app(storage))
    assert client.get("/api/festival").status_code == 200
    assert client.post("/api/artists", json={"name": "Zoé Tanguy"}).status_code == 201
    assert (
        TestClient(create_app(storage)).get("/api/artists/zoe-tanguy").status_code
        == 200
    )
    assert client.get("/admin/").status_code == 200


def test_cli_receives_memory_storage(capsys: pytest.CaptureFixture[str]) -> None:
    storage = MemoryStorage(JsonStorage(SOURCE).load())
    run_command(["venues"], storage)
    assert "Total: 1130 seats" in capsys.readouterr().out


def test_cli_data_option_before_or_after_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "alternate.json"
    storage = JsonStorage(path)
    storage.save(JsonStorage(SOURCE).load())
    FestivalService(storage).add_artist(Artist("One more artist"))
    for args in [["--data", str(path)], ["venues", "--data", str(path)]]:
        run_command(args)
        output = capsys.readouterr().out
        assert "13 artists" in output or "Total: 1130 seats" in output


def test_serve_passes_selected_storage_to_the_app(tmp_path: Path) -> None:
    path = tmp_path / "alternate.json"
    with patch("uvicorn.run") as serve:
        run_command(["serve", "--data", str(path), "--port", "8123"])
    app = serve.call_args.args[0]
    assert serve.call_args.kwargs == {"host": "127.0.0.1", "port": 8123}
    assert TestClient(app).get("/api/festival").status_code == 500


def test_failed_memory_save_preserves_persisted_state() -> None:
    storage = MemoryStorage(JsonStorage(SOURCE).load())
    before = storage.load().to_saved()
    with (
        patch.object(storage, "save", side_effect=StorageError("Refused save")),
        pytest.raises(StorageError),
    ):
        FestivalService(storage).add_artist(Artist("Unsaved"))
    assert storage.load().to_saved() == before


def test_default_storage_seeds_a_new_directory_without_overwriting_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    storage = default_storage()
    seed_before = storage.seed.read_bytes()
    assert len(storage.load().performances) == 23
    assert not storage.path.exists()
    FestivalService(storage).add_artist(Artist("Local artist"))
    assert storage.path.exists()
    assert storage.load().artist("local-artist").name == "Local artist"
    assert storage.seed.read_bytes() == seed_before


def test_explicit_missing_data_file_is_not_replaced_by_seed(tmp_path: Path) -> None:
    path = tmp_path / "missing.json"
    with pytest.raises(StorageError):
        JsonStorage(path).load()
    assert not path.exists()
