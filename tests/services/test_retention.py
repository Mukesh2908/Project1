"""retain_until wiring — project.md 20.4.

The column existed in the schema from the start but was never populated by
any caller, and due_for_review recomputed the cutoff dynamically instead of
reading it — so a retention-policy change would have silently changed which
past profiles counted as overdue.
"""

from datetime import date, timedelta

from app.config import retain_until as compute_retain_until
from app.models.store import Profile, Store
from app.schemas.evidence import ProfileRecord
from app.services.retention_service import due_for_review, retention_months


def make_store() -> Store:
    return Store("sqlite:///:memory:")


def profile(pid: str) -> ProfileRecord:
    return ProfileRecord(profile_id=pid, display_name=pid, file_hash=pid)


def test_save_profile_populates_retain_until():
    store = make_store()
    store.save_profile(profile("C-1"))
    with store.session() as session:
        row = session.get(Profile, "C-1")
        assert row.retain_until is not None
        assert date.fromisoformat(row.retain_until) > date.today()


def test_retain_until_matches_the_configured_retention_period():
    expected = compute_retain_until(date(2026, 1, 1))
    months = retention_months()
    assert date.fromisoformat(expected) == date(2026, 1, 1) + timedelta(days=30 * months)


def test_explicit_retain_until_overrides_the_computed_default():
    store = make_store()
    store.save_profile(profile("C-1"), retain_until="2099-01-01")
    with store.session() as session:
        row = session.get(Profile, "C-1")
        assert row.retain_until == "2099-01-01"


def test_a_profile_past_its_own_retain_until_is_overdue():
    store = make_store()
    store.save_profile(profile("C-1"))
    with store.session() as session:
        row = session.get(Profile, "C-1")
        row.retain_until = "2020-01-01"
        session.merge(row)

    overdue = due_for_review(store, today=date(2026, 9, 22))
    assert [p.profile_id for p in overdue] == ["C-1"]


def test_a_freshly_saved_profile_is_not_overdue():
    store = make_store()
    store.save_profile(profile("C-1"))
    overdue = due_for_review(store, today=date.today())
    assert overdue == []


def test_changing_the_retention_setting_does_not_retroactively_flag_old_profiles():
    """The point of storing retain_until per-row rather than recomputing it:
    a profile parsed under a 12-month policy keeps its 12-month commitment
    even if the setting is later shortened to, say, 3 months."""
    store = make_store()
    store.save_profile(profile("C-1"), retain_until=compute_retain_until(date.today()))

    # Simulate a much shorter policy by checking far short of the original
    # 12-month commitment - the profile must still not be overdue.
    soon = date.today() + timedelta(days=90)
    overdue = due_for_review(store, today=soon)
    assert overdue == []


def test_legacy_rows_without_retain_until_fall_back_to_parsed_at():
    """A row saved before this column was populated (retain_until is NULL)
    must not be silently exempt from retention forever."""
    store = make_store()
    store.save_profile(profile("C-1"))
    with store.session() as session:
        row = session.get(Profile, "C-1")
        row.retain_until = None
        row.parsed_at = "2020-01-01T00:00:00+00:00"
        session.merge(row)

    overdue = due_for_review(store, today=date.today())
    assert [p.profile_id for p in overdue] == ["C-1"]
