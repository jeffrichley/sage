"""Service layer for the Sage application."""

from typing import Protocol, TypeVar


T_co = TypeVar("T_co", covariant=True)


class SupportsClose(Protocol[T_co]):
    """Protocol describing resources that can be closed."""

    def close(self) -> None:
        """Release any acquired resources."""


__all__ = ["SupportsClose", "T_co"]

