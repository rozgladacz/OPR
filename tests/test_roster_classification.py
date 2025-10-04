from app.routers import rosters
from app.services import costs


def _role_keys(passive_section: dict[str, int]) -> list[str]:
    return [
        key
        for key in passive_section.keys()
        if costs.ability_identifier(key) in costs.ROLE_SLUGS
    ]


def test_apply_classification_replaces_existing_role_flag() -> None:
    loadout = {"passive": {"wojownik": 1, "inne": 1}}
    classification = {"slug": "strzelec"}

    result = rosters._apply_classification_to_loadout(loadout, classification)

    assert result is loadout
    passive_section = result.get("passive", {})
    assert passive_section.get("inne") == 1
    assert passive_section.get("strzelec") == 1
    assert costs.ability_identifier("strzelec") in {
        costs.ability_identifier(key) for key in passive_section
    }
    assert all(
        costs.ability_identifier(key) != "wojownik"
        for key in passive_section
    )


def test_apply_classification_removes_role_flags_when_none() -> None:
    loadout = {"passive": {"wojownik": 1, "strzelec": 1, "inne": 1}}

    result = rosters._apply_classification_to_loadout(loadout, None)

    passive_section = result.get("passive", {})
    assert passive_section.get("inne") == 1
    assert not _role_keys(passive_section)


def test_apply_classification_keeps_single_role_entry() -> None:
    loadout = {"passive": {"Wojownik": 2, "inne": 1}}
    classification = {"slug": "wojownik"}

    result = rosters._apply_classification_to_loadout(loadout, classification)

    passive_section = result.get("passive", {})
    role_keys = _role_keys(passive_section)
    assert len(role_keys) == 1
    key = role_keys[0]
    assert costs.ability_identifier(key) == "wojownik"
    assert passive_section[key] == 1


def test_classification_respects_available_slugs() -> None:
    result = rosters._classification_from_totals(12, 12, {"strzelec"})

    assert result is not None
    assert result["slug"] == "strzelec"
