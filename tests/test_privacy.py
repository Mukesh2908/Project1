"""Privacy controls — project.md section 20, decision D12.

With no local model, masking and the provider allowlist are the only things
standing between an employee's resume and a third party. Both are tested rather
than assumed.
"""

from pathlib import Path

import pytest

from app.ai.provider import MockProvider, ProviderBlockedError, check_allowed
from app.services.pii_masker import contains_pii, mask, unmask

FIXTURES = Path(__file__).parent / "fixtures" / "resumes"

#: Names chosen to exercise the weakness that matters here: spaCy's small model
#: is poor on Indian names, and it was carrying the whole guarantee in v2.0.
NAMES = [
    "Rajesh Kumar Nair",
    "Priya Raghavan",
    "Sandeep Kulkarni",
    "Meera Iyer",
    "Vikram Desai",
    "Lakshmi Narayanan",
    "Arun Mehta",
    "Fatima Sheikh",
    "Joseph D'Souza",
    "Ananya Chatterjee",
]

TEMPLATE = """{name}
{email} | +91 {phone}
Address: {address}
Date of Birth: 12/04/1990   Gender: Male
Marital Status: Married
Nationality: Indian

PROFESSIONAL SUMMARY
{first} is a senior engineer with React experience.
"""


def build(name: str, index: int) -> str:
    first = name.split()[0]
    return TEMPLATE.format(
        name=name,
        first=first,
        email=f"{first.lower()}.{index}@example.com",
        phone=f"9{index:04d} {index:05d}",
        address=f"{index} Main Road, Bengaluru",
    )


# -- masking recall --------------------------------------------------------


@pytest.mark.parametrize("name", NAMES)
def test_every_name_is_masked(name: str):
    result = mask(build(name, NAMES.index(name)))
    for part in name.split():
        if len(part) > 2:
            assert part not in result.text, f"{part!r} survived masking"


@pytest.mark.parametrize("name", NAMES)
def test_no_contact_details_survive(name: str):
    result = mask(build(name, NAMES.index(name)))
    assert contains_pii(result.text) == []


@pytest.mark.parametrize("name", NAMES)
def test_sensitive_attributes_are_masked(name: str):
    """Gender, marital status and nationality must never reach a model."""
    result = mask(build(name, NAMES.index(name)))
    for value in ("Male", "Married", "Indian"):
        assert value not in result.text, f"{value!r} survived masking"


def test_masking_recall_meets_the_floor():
    """A hard floor, asserted across the whole fixture set."""
    total = leaked = 0
    for index, name in enumerate(NAMES):
        result = mask(build(name, index))
        for part in name.split():
            if len(part) <= 2:
                continue
            total += 1
            if part in result.text:
                leaked += 1
    recall = 1 - (leaked / total)
    assert recall == 1.0, f"Masking recall {recall:.1%} — every name token must be masked"


def test_real_fixtures_are_masked():
    for path in sorted(FIXTURES.glob("*.txt")):
        result = mask(path.read_text())
        assert contains_pii(result.text) == [], f"{path.name} leaked PII"


def test_pii_map_stays_local_and_can_restore_for_display():
    original = build("Priya Raghavan", 1)
    result = mask(original)
    assert result.pii_map["name"] == "Priya Raghavan"
    assert "Priya" in unmask(result.text, result.pii_map)


def test_college_names_are_stripped():
    text = "EDUCATION\nB.Tech, Computer Science, Anna University\n"
    assert "Anna University" not in mask(text).text


# -- provider allowlist ----------------------------------------------------


def test_dummy_mode_allows_fixtures_on_any_provider():
    check_allowed("groq/llama-3.3-70b-versatile")
    check_allowed("gemini/gemini-2.5-flash")


def test_dummy_mode_blocks_real_data_entirely():
    with pytest.raises(ProviderBlockedError, match="dummy_data_only"):
        check_allowed("groq/llama-3.3-70b-versatile", real_data=True)


def test_approved_cloud_allows_only_approved_providers():
    settings = {"privacy": {"mode": "approved_cloud", "approved_providers": ["openai"]}}
    check_allowed("openai/gpt-4o-mini", settings, real_data=True)
    with pytest.raises(ProviderBlockedError, match="not in privacy.approved_providers"):
        check_allowed("gemini/gemini-2.5-flash", settings, real_data=True)


def test_empty_allowlist_blocks_everything():
    settings = {"privacy": {"mode": "approved_cloud", "approved_providers": []}}
    with pytest.raises(ProviderBlockedError):
        check_allowed("openai/gpt-4o-mini", settings, real_data=True)


def test_unknown_privacy_mode_fails_closed():
    with pytest.raises(ProviderBlockedError, match="Unknown privacy mode"):
        check_allowed("openai/gpt-4o-mini", {"privacy": {"mode": "anything_goes"}})


def test_the_provider_enforces_the_allowlist_on_every_call():
    from app.schemas.jd import JDAnalysis

    provider = MockProvider()
    provider.register(JDAnalysis, JDAnalysis())
    with pytest.raises(ProviderBlockedError):
        provider.extract(JDAnalysis, "prompt", model="groq/x", real_data=True)


def test_mock_provider_refuses_unregistered_schemas():
    """A test must never silently fall through to a live model."""
    from app.ai.provider import ProviderUnavailableError
    from app.schemas.jd import JDAnalysis

    with pytest.raises(ProviderUnavailableError, match="no registered response"):
        MockProvider().extract(JDAnalysis, "prompt", model="mock/fixture")
