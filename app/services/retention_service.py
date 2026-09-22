"""Retention and deletion — project.md 20.4.

v2.0 held employee resumes with no retention policy and no way to remove a
candidate, which is not a defensible position for a tool on real HR data.

The date-math helpers (``retention_months``, ``retain_until``) live in
app/config.py, since they only need settings and app/models/store.py needs
them too — importing them from here would be circular. Re-exported below so
existing call sites are unaffected.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.config import retain_until, retention_months  # noqa: F401 (re-exported)
from app.models.store import Store
from app.schemas.evidence import ProfileRecord


def due_for_review(store: Store, today: date | None = None) -> list[ProfileRecord]:
    """Profiles past their retention window, listed for a human to action.

    Prefers each profile's own stored ``retain_until`` — set once, at parse
    time — over recomputing from the current setting, so a later change to
    retention_months does not retroactively flag profiles that were compliant
    when they were ingested. Rows from before this column was populated (or
    saved with an explicit ``retain_until=None``) fall back to the dynamic
    parsed_at-based cutoff.
    """
    today = today or date.today()
    fallback_cutoff = today - timedelta(days=30 * retention_months())
    out: list[ProfileRecord] = []
    with store.session() as session:
        from app.models.store import Profile

        rows = session.query(Profile).all()
        for row in rows:
            if not row.data:
                continue
            due = False
            if row.retain_until:
                try:
                    due = date.fromisoformat(row.retain_until[:10]) <= today
                except ValueError:
                    due = False
            elif row.parsed_at:
                try:
                    due = date.fromisoformat(row.parsed_at[:10]) <= fallback_cutoff
                except ValueError:
                    due = False
            if due:
                out.append(ProfileRecord.model_validate_json(row.data))
    return out


def purge(store: Store, profile_id: str, reason: str, actor: str) -> None:
    store.delete_profile(profile_id, reason=reason, actor=actor)
