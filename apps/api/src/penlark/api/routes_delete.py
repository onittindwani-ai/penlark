"""Taking things out for good. Owner only: it cannot be undone. The work is in `penlark/purge.py`."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from penlark import purge, service
from penlark.api.deps import db, get_ctx, owner
from penlark.api.types import PathId
from penlark.context import Ctx
from penlark.models import Author, Draft, Note, Performance, Sample

router = APIRouter(prefix="/api", tags=["delete"])


def _refusable(fn, *a):
    try:
        return fn(*a)
    except purge.Refused as exc:
        raise HTTPException(409, str(exc)) from exc


@router.delete("/notes/{note_id}", summary="Delete a note for good, with the ideas found only from it. Owner only. Says which drafts still quote it.")
def delete_note(note_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    row = s.get(Note, note_id)
    if row is None:
        raise HTTPException(404, "No such note.")
    return purge.delete_note(s, row, u["user"])


@router.delete("/samples/{sample_id}", summary="Delete a writing sample for good, with every voice profile version built after it was added, and build a new one. Owner only.")
def delete_sample(sample_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    row = s.get(Sample, sample_id)
    if row is None:
        raise HTTPException(404, "No such sample.")
    return purge.delete_sample(s, row, u["user"])


@router.delete("/drafts/{draft_id}", summary="Delete a draft for good, with its variants, calendar rows and exported file. A sent draft stays. Owner only.")
def delete_draft(draft_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    d = service.lock_draft(s, draft_id, ctx)
    if d is None:
        raise HTTPException(404, "No such draft.")
    return _refusable(purge.delete_draft, s, ctx, d, u["user"])


@router.delete("/authors/{author_id}", summary="Delete a voice for good, with its samples, profile versions and drafts. A voice with a sent draft stays. Owner only.")
def delete_author(author_id: PathId, s: Session = Depends(db, scope="function"), ctx: Ctx = Depends(get_ctx), u: dict = Depends(owner)):
    row = s.get(Author, author_id)
    if row is None:
        raise HTTPException(404, "No such voice.")
    return _refusable(purge.delete_author, s, ctx, row, u["user"])


@router.delete("/performance/{row_id}", summary="Delete one imported post number row. Owner only.")
def delete_performance_row(row_id: PathId, s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    if s.get(Performance, row_id) is None:
        raise HTTPException(404, "No such row.")
    return purge.delete_performance(s, [row_id], u["user"])


@router.delete("/performance", summary="Delete every imported post number row. Needs confirm=true. Owner only.")
def delete_all_performance(confirm: bool = Query(False), s: Session = Depends(db, scope="function"), u: dict = Depends(owner)):
    if not confirm:
        raise HTTPException(400, "Add confirm=true to delete every imported row.")
    return purge.delete_performance(s, None, u["user"])
