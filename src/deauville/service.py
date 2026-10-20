from deauville.models import Artist, Performance, Workshop
from deauville.storage import FestivalStorage, performance_from_data


# E11 - A real package
class FestivalService:
    """Apply a checked change to a fresh festival and persist it."""

    def __init__(self, storage: FestivalStorage) -> None:
        self.storage = storage

    def add(self, data: dict) -> Performance:
        festival = self.storage.load()
        show = performance_from_data(festival, data)
        festival.add(show)
        self.storage.save(festival)
        return show

    def update(self, identifier: str, data: dict) -> Performance:
        festival = self.storage.load()
        festival.performance(identifier)
        show = performance_from_data(festival, data)
        result = festival.update(identifier, show)
        self.storage.save(festival)
        return result

    def cancel(self, identifier: str) -> str:
        festival = self.storage.load()
        title = festival.cancel(identifier)
        self.storage.save(festival)
        return title

    def register(self, identifier: str, name: str) -> Workshop:
        festival = self.storage.load()
        show = festival.register(identifier, name)
        self.storage.save(festival)
        return show

    def add_artist(self, artist: Artist) -> Artist:
        festival = self.storage.load()
        festival.add_artist(artist)
        self.storage.save(festival)
        return artist
