from pydantic import BaseModel, Field


class WeaponForm(BaseModel):
    name: str = Field(..., max_length=120)
    range: str = Field(..., max_length=50)
    attacks: float = Field(1.0, ge=0)
    ap: int = Field(0)
    tags: str | None = None
    notes: str | None = None


class ArmyForm(BaseModel):
    name: str = Field(..., max_length=120)
    ruleset_id: int


class UnitForm(BaseModel):
    name: str
    quality: int
    defense: int
    toughness: int
    default_weapon_id: int | None = None
    flags: str | None = None


class RosterForm(BaseModel):
    name: str
    army_id: int
    points_limit: int | None = None
