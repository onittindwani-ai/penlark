"""Whole number ids that fit the database. A bigger number cannot name a row, and on Postgres it would be an error instead of "not found"."""

from __future__ import annotations

from typing import Annotated

from fastapi import Path, Query
from pydantic import Field

MAX_ID = 2**31 - 1
MAX_LIST = 500  # notes attached to one draft, or links from claims to notes

Id = Annotated[int, Field(ge=1, le=MAX_ID)]  # inside a request body
PathId = Annotated[int, Path(ge=1, le=MAX_ID)]  # inside the address
QueryId = Annotated[int, Query(ge=1, le=MAX_ID)]  # after the question mark
