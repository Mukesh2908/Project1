"""Each adversarial resume in the corpus trips the flag it was written for.

project.md 23.2 says the fixture set is specified by the risk list in section
24. These assertions are what make that true rather than aspirational — a
fixture that quietly stops triggering its flag is a silent regression in the
red-flag engine.
"""

from pathlib import Path

import pytest

from app.ai.demo_provider import build_mock_provider
from app.services.profile_analyzer import ingest_file

RESUMES = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "resumes"


@pytest.fixture(scope="module")
def parsed():
    provider = build_mock_provider()
    return {
        path.stem: ingest_file(path, provider).profile for path in sorted(RESUMES.glob("*.txt"))
    }


def flags_of(profile) -> str:
    return " | ".join(profile.red_flags)


def test_keyword_stuffing_is_flagged_as_padding(parsed):
    assert "Padding" in flags_of(parsed["r18_keyword_stuffed"])


def test_undated_projects_are_flagged(parsed):
    assert "Undated" in flags_of(parsed["r19_undated"])


def test_undated_projects_leave_years_unknown_rather_than_zero(parsed):
    """An unknown year must stay unknown so skill proof drops the part and
    renormalises (project.md 10.2) instead of scoring it as zero."""
    profile = parsed["r19_undated"]
    card = profile.evidence_cards.get("Databricks")
    assert card is not None
    assert card.hands_on_years is None


def test_stale_experience_is_flagged(parsed):
    assert "Stale" in flags_of(parsed["r20_stale_react"])


def test_support_only_work_is_flagged_as_wrong_context(parsed):
    assert "Wrong context" in flags_of(parsed["r21_support_only"])


def test_support_only_work_is_depth_capped(parsed):
    """project.md 7.5: used only in test/support caps depth at L2."""
    profile = parsed["r21_support_only"]
    for skill in ("Java", "SQL"):
        card = profile.evidence_cards.get(skill)
        if card:
            assert card.max_depth <= 2, f"{skill} reached L{card.max_depth}"


def test_an_overstated_claim_is_caught(parsed):
    """8 years claimed, one project since 2023 evidenced.

    The extractor previously captured "React experience" as the skill name
    for "8 years of React experience" — the commonest phrasing there is — so
    this flag almost never fired in practice.
    """
    profile = parsed["r22_claim_gap"]
    assert profile.claimed_skill_years.get("React") == 8.0
    assert "Claim vs evidence" in flags_of(profile)


def test_the_keyword_stuffer_is_caught_claiming_unevidenced_react(parsed):
    profile = parsed["r18_keyword_stuffed"]
    assert profile.claimed_skill_years.get("React") == 6.0
    assert any("React" in f for f in profile.red_flags if f.startswith("Claim vs evidence"))


def test_an_honest_resume_is_not_flagged_for_claims(parsed):
    """The check must not fire on someone whose claim matches their evidence."""
    profile = parsed["r01_react_senior_strong"]
    assert not [f for f in profile.red_flags if f.startswith("Claim vs evidence")]


def test_repeated_bullets_are_flagged_as_copy_paste(parsed):
    assert "Copy-paste" in flags_of(parsed["r23_copy_paste"])


def test_a_resume_with_no_projects_is_excluded_not_scored(parsed):
    profile = parsed["r24_empty_ish"]
    assert profile.projects == []
    assert profile.status == "excluded"


def test_pii_is_masked_in_every_corpus_resume():
    """The corpus includes DOB, gender and marital status; none may survive."""
    from app.services.pii_masker import contains_pii, mask

    for path in sorted(RESUMES.glob("*.txt")):
        result = mask(path.read_text())
        assert contains_pii(result.text) == [], path.name
        for value in ("Male", "Married"):
            assert value not in result.text, f"{path.name} leaked {value}"
