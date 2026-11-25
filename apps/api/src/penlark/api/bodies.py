"""Request bodies. Text from outside can carry a NUL character, which a Postgres text column refuses (an error page for the person): it is taken out before anything is stored."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


def strip_nul(value: Any) -> Any:
    """The same value with every NUL character removed from every text in it, however deeply it is nested. Nothing else is changed."""
    if isinstance(value, str):
        return value.replace("\x00", "") if "\x00" in value else value
    if isinstance(value, dict):
        return {strip_nul(k): strip_nul(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    return value


class Body(BaseModel):
    """The base of every request body that carries text."""

    @model_validator(mode="before")
    @classmethod
    def _no_nul(cls, data: Any) -> Any:
        return strip_nul(data)
