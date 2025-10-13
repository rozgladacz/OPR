from pathlib import Path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import models
from app.routers import armies
from app.services import costs, utils


def _role_slugs_from_flags(flags: str | None) -> set[str]:
    result: set[str] = set()
    for entry in utils.passive_flags_to_payload(flags):
        slug = entry.get("slug")
        identifier = costs.ability_identifier(slug) if slug else None
        if identifier in costs.ROLE_SLUGS:
            result.add(identifier)
    return result


def test_apply_unit_form_data_infers_shooter_classification() -> None:
    weapon = models.Weapon(
        id=1,
        name="Rifle",
        range='24"',
        attacks=1.0,
        ap=0,
        tags=None,
        armory_id=1,
    )
    unit = models.Unit(
        name="Marksmen",
        quality=4,
        defense=4,
        toughness=6,
        army_id=1,
    )

    armies._apply_unit_form_data(
        unit,
        name=unit.name,
        quality=unit.quality,
        defense=unit.defense,
        toughness=unit.toughness,
        passive_items=[],
        active_items=[],
        aura_items=[],
        weapon_entries=[(weapon, True, 1)],
        db=None,  # type: ignore[arg-type]
    )

    assert _role_slugs_from_flags(unit.flags) == {"strzelec"}


def test_apply_unit_form_data_defaults_to_warrior_when_unspecified() -> None:
    unit = models.Unit(
        name="Infantry",
        quality=4,
        defense=4,
        toughness=6,
        army_id=1,
    )

    armies._apply_unit_form_data(
        unit,
        name=unit.name,
        quality=unit.quality,
        defense=unit.defense,
        toughness=unit.toughness,
        passive_items=[],
        active_items=[],
        aura_items=[],
        weapon_entries=[],
        db=None,  # type: ignore[arg-type]
    )

    assert _role_slugs_from_flags(unit.flags) == {"wojownik"}


def test_apply_unit_form_data_preserves_existing_role_classification() -> None:
    existing_flags = utils.passive_payload_to_flags(
        [
            {"slug": "strzelec", "is_default": True},
        ]
    )
    unit = models.Unit(
        name="Veterans",
        quality=4,
        defense=4,
        toughness=6,
        army_id=1,
        flags=existing_flags,
    )

    melee_weapon = models.Weapon(
        id=2,
        name="Blades",
        range="",
        attacks=3.0,
        ap=2,
        tags=None,
        armory_id=1,
    )

    armies._apply_unit_form_data(
        unit,
        name=unit.name,
        quality=unit.quality,
        defense=unit.defense,
        toughness=unit.toughness,
        passive_items=[],
        active_items=[],
        aura_items=[],
        weapon_entries=[(melee_weapon, True, 1)],
        db=None,  # type: ignore[arg-type]
    )

    assert _role_slugs_from_flags(unit.flags) == {"strzelec"}


def test_passive_payload_handles_mandatory_flag() -> None:
    flags = utils.passive_payload_to_flags(
        [
            {"slug": "bohater", "is_default": False, "is_mandatory": True},
        ]
    )

    assert flags == "bohater!"

    payload = utils.passive_flags_to_payload(flags)

    assert payload and payload[0]["slug"].casefold() == "bohater"
    assert payload[0]["is_default"] is True
    assert payload[0]["is_mandatory"] is True


def test_apply_unit_form_data_keeps_optional_trait_optional() -> None:
    unit = models.Unit(
        name="Champion",
        quality=2,
        defense=2,
        toughness=4,
        army_id=1,
    )

    armies._apply_unit_form_data(
        unit,
        name=unit.name,
        quality=unit.quality,
        defense=unit.defense,
        toughness=unit.toughness,
        passive_items=[{"slug": "bohater", "is_default": False, "is_mandatory": False}],
        active_items=[],
        aura_items=[],
        weapon_entries=[],
        db=None,  # type: ignore[arg-type]
    )

    payload = utils.passive_flags_to_payload(unit.flags)

    assert payload and payload[0]["slug"] == "bohater"
    assert payload[0]["is_default"] is False
    assert payload[0]["is_mandatory"] is False
