import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# E08 - The festival holds the rules, and tests prove it
ROOT = Path(__file__).resolve().parents[1]


def command(
    folder: Path, args: list[str], answers: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "main.py"), *args],
        cwd=folder,
        input=answers,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=10,
        check=False,
    )


@pytest.fixture
def project_data(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "data/festival.json").write_bytes(
        (ROOT / "data/festival.json").read_bytes()
    )
    return tmp_path


def test_cli_add_save_and_cancel(project_data: Path) -> None:
    path = project_data / "data/festival.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    result = command(
        project_data,
        ["add"],
        "Morning Coffee\nkarim-benali\nla-cabane\n2027-06-13T08:00\n30\n",
    )
    assert result.returncode == 0
    assert "Added: la-cabane-2027-06-13-0800" in result.stdout
    assert (
        command(project_data, ["programme", "2027-06-13"]).stdout.splitlines()[1]
        == "08:00-08:30 | La Cabane | Morning Coffee (solo)"
    )
    result = command(project_data, ["cancel", "la-cabane-2027-06-13-0800"])
    assert result.returncode == 0
    assert result.stdout.strip() == "Cancelled: Morning Coffee"
    assert json.loads(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize(
    "args, answers, message",
    [
        (["programme", "June-11"], None, "is not a day"),
        (
            ["add"],
            "Too Late\nkarim-benali\nle-kiosque\n2027-06-12T02:15\n30\n",
            "busy with After Hours",
        ),
        (["cancel", "missing"], None, "No performance"),
    ],
)
def test_cli_errors_leave_file_unchanged(
    project_data: Path, args: list[str], answers: str | None, message: str
) -> None:
    path = project_data / "data/festival.json"
    original = path.read_bytes()
    result = command(project_data, args, answers)
    assert result.returncode == 1
    assert "Error:" in result.stdout and message in result.stdout
    assert not result.stderr
    assert path.read_bytes() == original
