"""Retention and deletion — project.md 20.4.

v2.0 held employee resumes with no retention policy and no way to remove a
candidate, which is not a defensible position for a tool on real HR data.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.config import load_settings
from app.models.store import Store
from app.schemas.evidence import ProfileRecord


def retention_months() -> int:
    return int((load_settings().get("privacy") or {}).get("retention_months", 12))


def retain_until(parsed_on: date | None = None) -> str:
    parsed_on = parsed_on or date.today()
    return (parsed_on + timedelta(days=30 * retention_months())).isoformat()


def due_for_review(store: Store, today: date | None = None) -> list[ProfileRecord]:
    """Profiles past their retention window, listed for a human to action."""
    today = today or date.today()
    cutoff = today - timedelta(days=30 * retention_months())
    out: list[ProfileRecord] = []
    with store.session() as session:
        from app.models.store import Profile

        rows = session.query(Profile).all()
        for row in rows:
            if not row.parsed_at:
                continue
            try:
                parsed = date.fromisoformat(row.parsed_at[:10])
            except ValueError:
                continue
            if parsed <= cutoff and row.data:
                out.append(ProfileRecord.model_validate_json(row.data))
    return out


def purge(store: Store, profile_id: str, reason: str, actor: str) -> None:
    store.delete_profile(profile_id, reason=reason, actor=actor)
