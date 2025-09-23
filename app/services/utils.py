from __future__ import annotations

from typing import Sequence

from .. import models


def split_owned(items: Sequence, user: models.User | None):
    mine = []
    global_items = []
    others = []
    for item in items:
        owner_id = getattr(item, "owner_id", None)
        if user and owner_id == user.id:
            mine.append(item)
        elif owner_id is None:
            global_items.append(item)
        elif user and user.is_admin:
            others.append(item)
    return mine, global_items, others


def parse_flags(text: str | None) -> dict:
    if not text:
        return {}
    entries = [entry.strip() for entry in text.split(",") if entry.strip()]
    result = {}
    for entry in entries:
        if "=" in entry:
            key, value = entry.split("=", 1)
            result[key.strip()] = value.strip()
        else:
            result[entry] = True
    return result
