from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

import pytest

from deauville.models import Artist, Lineup, Performance, SoloShow, Venue, Workshop
from deauville.storage import JsonStorage, performance_from_data


# E09 - Three kinds of performances
@pytest.fixture
def common() -> dict:
    return {
        "title": "Test show",
        "venue": Venue("Grand Casino", 650, "Seafront"),
        "start": datetime.fromisoformat("2027-06-11T10:00"),
        "duration_minutes": 60,
    }


def test_base_class_is_abstract(common: dict) -> None:
    with pytest.raises(TypeError, match="abstract"):
        Performance(**common)


@pytest.mark.parametrize("age", [-1, 19, True, 1.5])
def test_solo_rejects_invalid_age(common: dict, age: float) -> None:
    with pytest.raises(ValueError, match="0 to 18"):
        SoloShow(**common, artist=Artist("Alice"), min_age=age)


@pytest.mark.parametrize("age", [0, 18])
def test_solo_age_boundaries_and_view(common: dict, age: float) -> None:
    show = SoloShow(**common, artist=Artist("Alice"), min_age=age)
    assert show.summary == "Alice"
    assert show.capacity == 650
    assert show.to_view()["artist"] == "alice"
    assert show.to_view()["min_age"] == age
    assert "host" not in show.to_view() and "teacher" not in show.to_view()


@pytest.mark.parametrize("acts", [[], [Artist("Alice")]])
def test_lineup_needs_two_acts(common: dict, acts: list[Artist]) -> None:
    with pytest.raises(ValueError, match="at least two"):
        Lineup(**common, host=Artist("Host"), acts=acts)


def test_lineup_rejects_duplicate_acts_by_slug(common: dict) -> None:
    with pytest.raises(ValueError, match="only once"):
        Lineup(**common, host=Artist("Host"), acts=[Artist("Élodie"), Artist("Elodie")])


def test_lineup_host_cannot_be_an_act(common: dict) -> None:
    with pytest.raises(ValueError, match="host cannot"):
        Lineup(
            **common, host=Artist("Élodie"), acts=[Artist("Elodie"), Artist("Alice")]
        )


@pytest.mark.parametrize("count, minimum", [(2, 23), (3, 36), (4, 49)])
def test_lineup_minimum_duration(common: dict, count: int, minimum: int) -> None:
    acts = [Artist(f"Act {index}") for index in range(count)]
    options = {**common, "duration_minutes": minimum - 1}
    with pytest.raises(ValueError, match=f"at least {minimum} minutes"):
        Lineup(**options, host=Artist("Host"), acts=acts)
    options["duration_minutes"] = minimum
    show = Lineup(**options, host=Artist("Host"), acts=acts)
    assert show.duration_minutes == minimum


def test_lineup_artists_roles_summary_and_fields(common: dict) -> None:
    host, alice, bob = Artist("Host"), Artist("Alice"), Artist("Bob")
    show = Lineup(**common, host=host, acts=[alice, bob])
    assert show.artists == [host, alice, bob]
    assert show.role_of(host) == "host"
    assert show.role_of(alice) == "act"
    assert show.role_of(Artist("Absent")) is None
    assert show.summary == "hosted by Host, with Alice, Bob"
    assert show.to_view()["host"] == "host"
    assert show.to_view()["acts"] == ["alice", "bob"]
    assert "min_age" not in show.to_view() and "participants" not in show.to_view()


@pytest.mark.parametrize("maximum", [0, -1, True, 1.5])
def test_workshop_requires_positive_whole_capacity(
    common: dict, maximum: float
) -> None:
    with pytest.raises(ValueError, match="at least one"):
        Workshop(**common, teacher=Artist("Teacher"), max_participants=maximum)


@pytest.mark.parametrize("maximum, capacity", [(1, 1), (12, 12), (999, 650)])
def test_workshop_capacity_is_limited_by_venue(
    common: dict, maximum: float, capacity: int
) -> None:
    show = Workshop(**common, teacher=Artist("Teacher"), max_participants=maximum)
    assert show.capacity == capacity
    assert show.places_left == capacity


def test_workshop_places_and_summary(common: dict) -> None:
    show = Workshop(
        **common,
        teacher=Artist("Inès Moreau"),
        max_participants=12,
        participants=[" Camille R. ", "Yanis B.", "Lou M."],
    )
    assert show.participants == ("Camille R.", "Yanis B.", "Lou M.")
    assert show.summary == "with Inès Moreau, 3/12 places taken"
    assert show.to_view()["places_left"] == 9
    assert show.to_view()["teacher"] == "ines-moreau"
    assert "acts" not in show.to_view() and "artist" not in show.to_view()


def test_workshop_rejects_duplicate_participants_ignoring_case(common: dict) -> None:
    with pytest.raises(ValueError, match="already registered"):
        Workshop(
            **common,
            teacher=Artist("Teacher"),
            max_participants=12,
            participants=["Camille R.", " camille r. "],
        )


def test_workshop_rejects_overbooking_the_venue(common: dict) -> None:
    options = {**common, "venue": Venue("Small room", 1, "Address")}
    with pytest.raises(ValueError, match="only 1 places"):
        Workshop(
            **options,
            teacher=Artist("Teacher"),
            max_participants=999,
            participants=["Alice", "Bob"],
        )


def test_full_workshop_has_no_places_left(common: dict) -> None:
    show = Workshop(
        **common, teacher=Artist("Teacher"), max_participants=1, participants=["Alice"]
    )
    assert show.places_left == 0


def test_real_data_uses_subclasses_and_expected_summaries() -> None:
    festival = JsonStorage(
        Path(__file__).resolve().parents[1] / "data/festival.json"
    ).load()
    lineup = festival.performance("le-kiosque-2027-06-12-0100")
    workshop = festival.performance("la-cabane-2027-06-11-1030")
    solo = festival.performance("grand-casino-2027-06-11-2030")
    assert isinstance(lineup, Lineup)
    assert isinstance(workshop, Workshop)
    assert isinstance(solo, SoloShow)
    assert lineup.summary == "hosted by Tom Vasseur, with Hugo Lemaire, Maya Choukri"
    assert workshop.summary == "with Inès Moreau, 3/12 places taken"
    assert solo.summary == "Léa Fontaine"


def test_loader_rejects_unknown_kind() -> None:
    festival = JsonStorage(
        Path(__file__).resolve().parents[1] / "data/festival.json"
    ).load()
    row = {**festival.performances[0].to_saved(), "kind": "unknown"}
    with pytest.raises(ValueError, match="Unknown performance kind"):
        performance_from_data(festival, row)


def test_all_kinds_round_trip_without_computed_fields(tmp_path: Path) -> None:
    festival = JsonStorage(
        Path(__file__).resolve().parents[1] / "data/festival.json"
    ).load()
    path = tmp_path / "festival.json"
    JsonStorage(path).save(festival)
    loaded = JsonStorage(path).load()
    assert [type(show) for show in loaded.performances] == [
        type(show) for show in festival.performances
    ]
    assert loaded.to_saved() == festival.to_saved()
    assert all(
        "end" not in row and "id" not in row
        for row in loaded.to_saved()["performances"]
    )


def test_festival_rechecks_subclass_rules_before_add(common: dict) -> None:
    festival = JsonStorage(
        Path(__file__).resolve().parents[1] / "data/festival.json"
    ).load()
    show = SoloShow(**common, artist=festival.artist("max-pellerin"))
    with pytest.raises(FrozenInstanceError):
        show.min_age = 19
    assert show.min_age == 0
