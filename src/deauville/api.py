from datetime import date, datetime
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import Body, FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from deauville.errors import (
    ConflictError,
    FestivalError,
    InvalidValueError,
    NotFoundError,
    StorageError,
)
from deauville.festival import Festival
from deauville.models import Artist
from deauville.service import FestivalService
from deauville.storage import FestivalStorage, default_storage

# E10 - The admin: writing through the API
STATUS = {
    NotFoundError: 404,
    ConflictError: 409,
    InvalidValueError: 422,
    StorageError: 500,
}


class RequestBody(BaseModel):
    """Base schema that rejects unexpected request fields."""

    model_config = ConfigDict(extra="forbid")


class ArtistIn(RequestBody):
    """JSON fields accepted when creating an artist."""

    name: str
    bio: str = ""
    photo_url: str = ""


class ParticipantIn(RequestBody):
    """Name supplied for a workshop registration."""

    name: str


class PerformanceIn(RequestBody):
    """Common fields accepted when creating or replacing a performance."""

    title: str
    venue: str
    start: datetime
    duration_minutes: StrictInt
    description: str = ""


class SoloIn(PerformanceIn):
    """Solo request fields, selected by the solo discriminator."""

    kind: Literal["solo"]
    artist: str
    min_age: StrictInt = 0


class LineupIn(PerformanceIn):
    """Lineup request fields, including host and ordered acts."""

    kind: Literal["lineup"]
    host: str
    acts: list[str]


class WorkshopIn(PerformanceIn):
    """Workshop request fields and optional registrations."""

    kind: Literal["workshop"]
    teacher: str
    max_participants: StrictInt
    participants: list[str] = Field(default_factory=list)


PerformanceBody = Annotated[SoloIn | LineupIn | WorkshopIn, Body(discriminator="kind")]


def performance_body(body: PerformanceIn) -> dict:
    """Convert the validated request to the saved minute-precision representation."""

    if body.start.second or body.start.microsecond:
        raise InvalidValueError("Start time must use whole minutes.")
    return {**body.model_dump(), "start": body.start.isoformat(timespec="minutes")}


# E11 - A real package
def create_app(storage: FestivalStorage | None = None) -> FastAPI:
    """Build independent routes and saved operations around the supplied storage."""

    app = FastAPI(title="Deauville Festival du Rire")
    storage = storage if storage is not None else default_storage()
    service = FestivalService(storage)
    write_lock = RLock()
    root = Path(__file__).resolve().parent

    @app.exception_handler(FestivalError)
    def festival_error(request: Request, error: FestivalError) -> JSONResponse:
        """Translate a domain error into the JSON status required by API.md."""

        return JSONResponse(
            status_code=STATUS.get(type(error), 422), content={"detail": str(error)}
        )

    def read_festival() -> Festival:
        return storage.load()

    @app.get("/api/festival")
    def festival_info() -> dict:
        return read_festival().to_view()

    @app.get("/api/venues")
    def list_venues() -> list[dict]:
        return [venue.to_view() for venue in read_festival().venues]

    @app.get("/api/artists")
    def list_artists() -> list[dict]:
        artists = read_festival().artists
        return [artist.to_view() for artist in artists]

    @app.get("/api/programme")
    def list_programme(day: date | None = None, venue: str | None = None) -> list[dict]:
        festival = read_festival()
        return [performance.to_view() for performance in festival.programme(day, venue)]

    @app.get("/api/performances/{identifier}")
    def read_performance(identifier: str) -> dict:
        return read_festival().performance(identifier).to_view()

    @app.get("/api/artists/{slug}")
    def read_artist(slug: str) -> dict:
        festival = read_festival()
        artist = festival.artist(slug)
        return {
            **artist.to_view(),
            "performances": [
                performance.to_view()
                for performance, role in festival.artist_performances(slug)
            ],
        }

    @app.get("/api/now")
    def read_now(at: datetime | None = None) -> dict:
        moment = (
            at
            if at is not None
            else datetime.now(ZoneInfo("Europe/Paris")).replace(tzinfo=None)
        )
        if moment.tzinfo is not None:
            raise InvalidValueError("Use local festival time without a time zone.")
        festival = read_festival()
        return {
            "at": moment.isoformat(timespec="minutes"),
            "now_playing": [
                performance.to_view() for performance in festival.on_stage(moment)
            ],
            "up_next": [
                performance.to_view() for performance in festival.up_next(moment)
            ],
        }

    @app.post("/api/artists", status_code=201)
    def create_artist(body: ArtistIn) -> dict:
        with write_lock:
            return service.add_artist(Artist(**body.model_dump())).to_view()

    @app.post("/api/performances", status_code=201)
    def create_performance(body: PerformanceBody) -> dict:
        with write_lock:
            return service.add(performance_body(body)).to_view()

    @app.put("/api/performances/{identifier}")
    def update_performance(identifier: str, body: PerformanceBody) -> dict:
        with write_lock:
            return service.update(identifier, performance_body(body)).to_view()

    @app.delete("/api/performances/{identifier}", status_code=204)
    def delete_performance(identifier: str) -> Response:
        with write_lock:
            service.cancel(identifier)
            return Response(status_code=204)

    @app.post("/api/performances/{identifier}/participants", status_code=201)
    def register_participant(identifier: str, body: ParticipantIn) -> dict:
        with write_lock:
            return service.register(identifier, body.name).to_view()

    app.mount("/admin", StaticFiles(directory=root / "web" / "admin", html=True))
    app.mount("/", StaticFiles(directory=root / "web" / "public", html=True))
    return app


app = create_app()
