# E10 - The admin: writing through the API
class FestivalError(ValueError):
    """Base class for errors that can be explained to a festival organiser."""


class NotFoundError(FestivalError):
    """An artist, venue or performance does not exist."""


class ConflictError(FestivalError):
    """The requested change conflicts with the festival or its schedule."""


class InvalidValueError(FestivalError):
    """A name, duration or other supplied value is invalid."""


class StorageError(FestivalError):
    """The festival file could not be read or saved."""
