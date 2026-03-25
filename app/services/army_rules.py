from __future__ import annotations

from typing import Iterable

from .utils import (
    HIDDEN_TRAIT_SLUGS,
    passive_flags_to_payload,
    passive_payload_to_flags,
)


def parse_rules(text: str | None) -> list[dict]:
    """Return a sanitized list of passive rules stored for an army."""

    entries: list[dict] = []
    for item in passive_flags_to_payload(text):
        if not item:
            continue
        slug_text = str(item.get("slug") or "").strip()
        if not slug_text:
            continue
        if slug_text.casefold() in HIDDEN_TRAIT_SLUGS:
            continue
        label = item.get("label") or slug_text
        normalized_value: str | None = None
        raw_value = item.get("value")
        if raw_value is not None:
            value_text = str(raw_value).strip()
            if value_text:
                normalized_value = value_text
        entries.append(
            {
                "slug": slug_text,
                "value": normalized_value,
                "label": label,
                "base_label": label,
                "raw": label,
                "description": item.get("description") or "",
                # Army rules should not carry default/mandatory flags
                "is_default": True,
                "is_mandatory": False,
            }
        )
    return entries


def serialize_rules(items: Iterable[dict] | None) -> str:
    """Serialize a picker payload into the flags string stored on Army."""

    payload: list[dict] = []
    seen: set[tuple[str, str | None]] = set()
    if not items:
        return ""
    for item in items:
        if not isinstance(item, dict):
            continue
        slug_text = str(item.get("slug") or "").strip()
        if not slug_text:
            continue
        normalized_slug = slug_text.casefold()
        if normalized_slug in HIDDEN_TRAIT_SLUGS:
            continue
        value_data = item.get("value")
        normalized_value: str | None = None
        if value_data is not None:
            value_text = str(value_data).strip()
            if value_text:
                normalized_value = value_text
        key = (normalized_slug, normalized_value)
        if key in seen:
            continue
        seen.add(key)
        payload.append(
            {
                "slug": slug_text,
                "value": normalized_value,
                # Default/mandatory markers are not relevant for army rules
                "is_default": True,
                "is_mandatory": False,
            }
        )
    return passive_payload_to_flags(payload)
