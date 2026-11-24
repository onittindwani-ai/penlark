from __future__ import annotations

from datetime import date, datetime


def iso(v: datetime | date | None) -> str | None:
    return v.isoformat() if v else None


def draft_dict(d, variants=None) -> dict:
    out = {"id": d.id, "author_id": d.author_id, "idea_id": d.idea_id, "kind": d.kind, "title": d.title, "text": d.text, "status": d.status, "source_note_ids": d.source_note_ids, "claim_links": d.claim_links,
           "approval_id": d.approval_id, "created_by": d.created_by, "created_at": iso(d.created_at), "updated_at": iso(d.updated_at)}
    if variants is not None:
        out["variants"] = [{"id": v.id, "label": v.label, "text": v.text, "note": v.note} for v in variants]
    return out
