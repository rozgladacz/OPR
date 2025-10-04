from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence
import re
import unicodedata

@dataclass(frozen=True)
class AbilityDefinition:
    slug: str
    name: str
    type: str
    description: str
    value_label: str | None = None
    value_type: str | None = None  # "number" or "text"
    value_choices: Sequence[str] | None = None

    def display_name(self) -> str:
        if self.value_label:
            if self.slug in {"aura", "rozkaz"}:
                return f"{self.name}: {self.value_label}"
            return f"{self.name}({self.value_label})"
        return self.name


ABILITY_DEFINITIONS: List[AbilityDefinition] = [
    # Passive abilities
    AbilityDefinition(
        slug="bohater",
        name="Bohater",
        type="passive",
        description=(
            "Może być dołączony do dowolnego oddziału. Może wykonywać testy przegrupowania za cały odział, "
            "ale musi korzystać z jej obrony dopóki wszystkie inne modele nie zostaną zabite. Podczas sprawdzania "
            "zdolności i rozmiaru traktowany jest jakby miał wytrzymałość mniejszą o 3, do minimum 1."
        ),
    ),
    AbilityDefinition(
        slug="zasadzka",
        name="Zasadzka",
        type="passive",
        description=(
            "Odział można odłożyć przed rozstawieniem. Na początku każdej rundy (poza pierwszą) można rozstawić go w dowolnym "
            "miejscu w odległości ponad 9” od jednostek wroga. W tej rundzie nie może kontrolować punktów. Gracze na zmianę "
            "rozmieszczają jednostki zasadzki, zaczynając od gracza, który dokonuje aktywacji jako następny."
        ),
    ),
    AbilityDefinition(
        slug="zwiadowca",
        name="Zwiadowca",
        type="passive",
        description=(
            "Można go odłożyć przed rozstawieniem. Rozstawia się po rozstawieniu wszystkich pozostałych jednostek, w odległości "
            "do 12” od normalnie dozwolonej pozycji. Gracze na zmianę rozmieszczają jednostki zwiadowcy, zaczynając od gracza, "
            "który dokonuje aktywacji jako następny."
        ),
    ),
    AbilityDefinition(
        slug="szybki",
        name="Szybki",
        type="passive",
        description="Porusza się o +2”.",
    ),
    AbilityDefinition(
        slug="wolny",
        name="Wolny",
        type="passive",
        description="Porusza się o -2”.",
    ),
    AbilityDefinition(
        slug="harcownik",
        name="Harcownik",
        type="passive",
        description="Po ataku możesz się ruszyć o 2”.",
    ),
    AbilityDefinition(
        slug="nieruchomy",
        name="Nieruchomy",
        type="passive",
        description="Po rozstawieniu nie może się przemieszczać.",
    ),
    AbilityDefinition(
        slug="zwinny",
        name="Zwinny",
        type="passive",
        description="Ignoruje trudny teren.",
    ),
    AbilityDefinition(
        slug="niezgrabny",
        name="Niezgrabny",
        type="passive",
        description="Na trudnym i niebezpiecznym terenie wykonuje dodatkowy test trudnego terenu.",
    ),
    AbilityDefinition(
        slug="latajacy",
        name="Latający",
        type="passive",
        description="Ignoruje teren i jednostki podczas ruchu.",
    ),
    AbilityDefinition(
        slug="samolot",
        name="Samolot",
        type="passive",
        description=(
            "Jest latający. Podczas ruchu musi przemieścić się dodatkowe 30” w jednej linii. Nie może być przyszpilony, "
            "nie może kontrolować punktów, szarżować, ani być celem szarży. Nie blokuje ruchu ani widzenia innych jednostek. "
            "Jednostki strzelające do niego mają -12” zasięgu i -1 do trafienia."
        ),
    ),
    AbilityDefinition(
        slug="strach",
        name="Strach",
        type="passive",
        description="Ten model liczy się jako ten, który zadał +X ran podczas sprawdzania, kto wygrał walkę wręcz.",
        value_label="X",
        value_type="number",
    ),
    AbilityDefinition(
        slug="nieustraszony",
        name="Nieustraszony",
        type="passive",
        description="Wykonuje jeden test przegrupowania mniej.",
    ),
    AbilityDefinition(
        slug="stracency",
        name="Straceńcy",
        type="passive",
        description="Po nieudanym teście przegrupowania wykonaj test trudnego terenu zamiast normalnych konsekwencji.",
    ),
    AbilityDefinition(
        slug="furia",
        name="Furia",
        type="passive",
        description="Podczas szarży naturalne 6 dają dodatkowe zwykłe trafienie.",
    ),
    AbilityDefinition(
        slug="nieustepliwy",
        name="Nieustępliwy",
        type="passive",
        description="Jeżeli model się nie poruszył naturalne 6 dają dodatkowe zwykłe trafienie.",
    ),
    AbilityDefinition(
        slug="kontra",
        name="Kontra",
        type="passive",
        description="Może wykonać kontratak przed szarżującym odziałem, a ten ignoruje swoją zdolność Impet.",
    ),
    AbilityDefinition(
        slug="regeneracja",
        name="Regeneracja",
        type="passive",
        description="Podczas obrony, za każdą naturalną 6 możesz zignorować następną ranę przydzieloną podczas tego ataku.",
    ),
    AbilityDefinition(
        slug="delikatny",
        name="Delikatny",
        type="passive",
        description="Podczas testów obrony naturalna 6 nie oznacza automatycznego sukcesu.",
    ),
    AbilityDefinition(
        slug="niewrazliwy",
        name="Niewrażliwy",
        type="passive",
        description="Podczas testów obrony naturalna 5 daje automatyczny sukces.",
    ),
    AbilityDefinition(
        slug="maskowanie",
        name="Maskowanie",
        type="passive",
        description="Atakujący ma -1 do rzutów na trafienie, gdy jest dalej niż 6\".",
    ),
    AbilityDefinition(
        slug="tarcza",
        name="Tarcza",
        type="passive",
        description="Zawsze ma osłonę.",
    ),
    AbilityDefinition(
        slug="okopany",
        name="Okopany",
        type="passive",
        description="Jego premia za osłonę wzrasta do +2.",
    ),
    AbilityDefinition(
        slug="transport",
        name="Transport",
        type="passive",
        description=(
            "Odziały o maksymalnej sumarycznej wytrzymałości X mogą być do niego przypisane. Mogą być w nich modele o wytrzymałości "
            "do 3. Gdy aktywujesz taki odział, możesz zamiast ruchu rozstawić go tak, aby każdy jego model był do 3” od transportera. "
            "Przestaje być przypisany i może wykonać akcję. Jeżeli nie zostanie rozstawiony, nie robi nic podczas swojej aktywacji. "
            "Jeżeli transporter zostanie zniszczony, przed jego zdjęciem każdy odział do niego przypisany zostaje rozstawiony jak wyżej, "
            "zostaje przyszpilony i wykonuje test jakości. W przypadku porażki zostaje wyczerpany i wykonuje test trudnego terenu. "
            "Odział który spełnia warunki rozstawienia z transportera, jako akcję możesz zostać zdjęty z planszy i do niego przypisany."
        ),
        value_label="X",
        value_type="number",
    ),
    AbilityDefinition(
        slug="masywny",
        name="Masywny",
        type="passive",
        description=(
            "Są na nim wydzielone elementy o własnej wytrzymałości, które mogą zostać zniszczone wraz z przypisanymi do nich zdolnościami i "
            "bronią. Wytrzymałość modelu jest równa początkowej sumie wytrzymałości jego elementów. Podczas przydzielania ran każdy element "
            "traktowany jak jest jak osobny model, choć rany ponad maksimum nie przepadają. Nie może dołączyć do oddziału."
        ),
    ),
    AbilityDefinition(
        slug="straznik",
        name="Strażnik",
        type="passive",
        description="Gdy wrogi odział zakończy ruch, możesz przerwać aby zaatakować. Następnie ten odział zostaje wyczerpany.",
    ),
    AbilityDefinition(
        slug="dobrze_strzela",
        name="Dobrze strzela",
        type="passive",
        description="Atakuje na dystans z jakością 4.",
    ),
    AbilityDefinition(
        slug="zle_strzela",
        name="Źle strzela",
        type="passive",
        description="Atakuje na dystans z jakością 5.",
    ),
    # Active abilities
    AbilityDefinition(
        slug="mag",
        name="Mag",
        type="active",
        description=(
            "Otrzymuje X żetonów mocy na początku każdej rundy, do maksymalnie 6. Magowie w oddziale współdzielą żetony. "
            "Wydaj tyle żetonów, ile wynosi koszt czaru i rzuć kością. Przy wyniku 4+ rozstrzygnij jego efekt. Jedna próba na czar na aktywację. "
            "Magowie znajdujący się w odległości do 18” i widzący maga mogą jednocześnie przed rzutem wydać dowolną liczbę żetonów mocy, "
            "aby dać +/-1 do rzutu za każdy żeton."
        ),
        value_label="X",
        value_type="number",
    ),
    AbilityDefinition(
        slug="przekaznik",
        name="Przekaźnik",
        type="active",
        description="Raz na rundę, gdy Mag w zasięgu 12” rzuca czar, może go rzucić z twojej pozycji z +1 do rzutu.",
    ),
    AbilityDefinition(
        slug="latanie",
        name="Łatanie",
        type="active",
        description="Oddział w zasięgu 2” odrzuca k3 znaczniki ran.",
    ),
    AbilityDefinition(
        slug="rozkaz",
        name="Rozkaz",
        type="active",
        description="Raz na rundę możesz przerwać, aby odział w zasięgu 12” od teraz do końca aktywacji (nie)miał zdolność X.",
        value_label="Zdolność",
        value_type="text",
    ),
    # Aura abilities
    AbilityDefinition(
        slug="aura",
        name="Aura",
        type="aura",
        description="Przydziel oddziałom w zasięgu wybraną zdolność. Wariant o zasięgu 12” jest dwukrotnie silniejszy.",
        value_label="Zdolność",
        value_type="text",
    ),
    AbilityDefinition(
        slug="radio",
        name="Radio",
        type="aura",
        description="Jeżeli model w twoim oddziale wydaje rozkaz, może wybrać oddział odległy o 24” który też ma radio.",
    ),
    # Weapon abilities
    AbilityDefinition(
        slug="rozprysk",
        name="Rozprysk",
        type="weapon",
        description="Przed wykonaniem testów obrony liczba trafień jest mnożona przez X, ale nie więcej, niż jest modeli w atakowanym oddziale.",
        value_label="X",
        value_type="number",
        value_choices=("2", "3", "6"),
    ),
    AbilityDefinition(
        slug="zabojczy",
        name="Zabójczy",
        type="weapon",
        description="Zamiast jednej przydziel jednocześnie X ran.",
        value_label="X",
        value_type="number",
        value_choices=("2", "3", "6"),
    ),
    AbilityDefinition(
        slug="niebezposredni",
        name="Niebezpośredni",
        type="weapon",
        description="Nie wymaga linii wzroku.",
    ),
    AbilityDefinition(
        slug="ciezki",
        name="Ciężki",
        type="weapon",
        description="-1 do ataku, jeżeli atakujący się poruszył.",
    ),
    AbilityDefinition(
        slug="impet",
        name="Impet",
        type="weapon",
        description="+1 do trafienia i +1 do AP podczas szarży.",
    ),
    AbilityDefinition(
        slug="namierzanie",
        name="Namierzanie",
        type="weapon",
        description="Ignoruje osłonę i negatywne modyfikatory do rzutów na trafienie i do zasięgu.",
    ),
    AbilityDefinition(
        slug="zuzywalny",
        name="Zużywalny",
        type="weapon",
        description="Można użyć tylko raz na grę.",
    ),
    AbilityDefinition(
        slug="niezawodny",
        name="Niezawodny",
        type="weapon",
        description="Atakuje z jakością 2+.",
    ),
    AbilityDefinition(
        slug="rozrywajacy",
        name="Rozrywający",
        type="weapon",
        description="Naturalne 6 na trafienie dają dodatkowe normalne trafienie.",
    ),
    AbilityDefinition(
        slug="precyzyjny",
        name="Precyzyjny",
        type="weapon",
        description="Atakujący rozdziela rany.",
    ),
    AbilityDefinition(
        slug="zracy",
        name="Żrący",
        type="weapon",
        description="W testach obrony nie ma automatycznych sukcesów.",
    ),
    AbilityDefinition(
        slug="szturmowa",
        name="Szturmowa",
        type="weapon",
        description="Można nią wykonywać ataki wręcz.",
    ),
    AbilityDefinition(
        slug="bez_oslon",
        name="Bez osłon",
        type="weapon",
        description="Ignoruje osłonę.",
    ),
    AbilityDefinition(
        slug="bez_regeneracji",
        name="Bez regeneracji",
        type="weapon",
        description="Ignoruje regenerację.",
    ),
    AbilityDefinition(
        slug="podkrecenie",
        name="Podkręcenie",
        type="weapon",
        description="Raz na grę może być użyta dodatkowy raz.",
    ),
]


def all_definitions() -> Sequence[AbilityDefinition]:
    return ABILITY_DEFINITIONS


def definitions_by_type(ability_type: str) -> List[AbilityDefinition]:
    return [ability for ability in ABILITY_DEFINITIONS if ability.type == ability_type]


def find_definition(slug: str) -> AbilityDefinition | None:
    for ability in ABILITY_DEFINITIONS:
        if ability.slug == slug:
            return ability
    return None


def display_with_value(definition: AbilityDefinition, value: str | None) -> str:
    if definition.slug == "rozkaz":
        value_text = (value or "").strip()
        ability_slug = slug_for_name(value_text) or value_text
        ability_def = find_definition(ability_slug) if ability_slug else None
        ability_label = ability_def.name if ability_def else value_text
        return f"{definition.name}: {ability_label}" if ability_label else definition.display_name()
    if definition.slug == "aura":
        value_text = (value or "").strip()
        ability_ref = ""
        aura_range = ""
        if value_text:
            parts = value_text.split("|", 1)
            if len(parts) == 2:
                ability_ref = parts[0].strip()
                aura_range = parts[1].strip()
            else:
                ability_ref = value_text
        ability_slug = slug_for_name(ability_ref) or ability_ref
        ability_def = find_definition(ability_slug) if ability_slug else None
        ability_label = ability_def.name if ability_def else ability_ref
        range_text = aura_range.strip() if aura_range else ""
        normalized_range = range_text.replace("\"", "").replace("”", "").strip()
        is_long_range = normalized_range == "12"
        prefix = f"{definition.name}(12\")" if is_long_range else definition.name
        if ability_label:
            return f"{prefix}: {ability_label}"
        return definition.display_name() if not is_long_range else f"{prefix}: {definition.value_label or ''}".rstrip(": ")
    if not definition.value_label:
        return definition.name if not value else f"{definition.name} {value}".strip()
    value_text = (value or '').strip()
    if not value_text:
        return definition.display_name()
    return f"{definition.name}({value_text})"


def description_with_value(definition: AbilityDefinition, value: str | None) -> str:
    if not definition or not definition.description:
        return ""

    description = definition.description
    value_text = (value or "").strip()

    if not value_text:
        return description

    if definition.slug == "rozkaz":
        ability_slug = slug_for_name(value_text) or value_text
        ability_def = find_definition(ability_slug) if ability_slug else None
        ability_label = ability_def.name if ability_def else value_text
        ability_description = ability_def.description if ability_def else ""
        replaced = description.replace("X", ability_label)
        parts = [replaced]
        if ability_description:
            parts.append(ability_description)
        return " ".join(part.strip() for part in parts if part).strip()

    if definition.slug == "aura":
        ability_ref = ""
        range_ref = ""
        parts = value_text.split("|", 1)
        if len(parts) == 2:
            ability_ref, range_ref = parts[0].strip(), parts[1].strip()
        else:
            ability_ref = value_text
        ability_slug = slug_for_name(ability_ref) or ability_ref
        ability_def = find_definition(ability_slug) if ability_slug else None
        ability_label = ability_def.name if ability_def else ability_ref
        ability_description = ability_def.description if ability_def else ""
        range_clean = range_ref.replace("\"", "").replace("”", "").strip()
        summary: list[str] = [description]
        if ability_label:
            summary.append(f"Wybrana zdolność: {ability_label}.")
        if ability_description:
            summary.append(ability_description)
        if range_clean:
            summary.append(f"Zasięg: {range_clean}\".")
        return " ".join(part.strip() for part in summary if part).strip()

    return description.replace("X", value_text)


def to_dict(definition: AbilityDefinition) -> dict:
    return {
        "slug": definition.slug,
        "name": definition.name,
        "display_name": definition.display_name(),
        "type": definition.type,
        "description": definition.description,
        "value_label": definition.value_label,
        "value_type": definition.value_type,
        "requires_value": definition.value_label is not None,
        "value_choices": list(definition.value_choices) if definition.value_choices else [],
    }


def iter_definitions(slugs: Iterable[str]) -> List[AbilityDefinition]:
    found: List[AbilityDefinition] = []
    for slug in slugs:
        definition = find_definition(slug)
        if definition:
            found.append(definition)
    return found


def _ascii_letters(value: str) -> str:
    result: list[str] = []
    for char in value:
        if unicodedata.combining(char):
            continue
        if ord(char) < 128:
            result.append(char)
            continue
        name = unicodedata.name(char, "")
        if "LETTER" in name:
            base = name.split("LETTER", 1)[1].strip()
            if " WITH " in base:
                base = base.split(" WITH ", 1)[0].strip()
            if " SIGN" in base:
                base = base.split(" SIGN", 1)[0].strip()
            if " DIGRAPH" in base:
                base = base.split(" DIGRAPH", 1)[0].strip()
            tokens = base.split()
            if len(tokens) > 1 and len(tokens[-1]) == 1:
                base = tokens[-1]
            else:
                base = base.replace(" ", "")
            if not base:
                continue
            if "SMALL" in name:
                result.append(base.lower())
            else:
                result.append(base.upper())
        # Ignore characters without a useful letter mapping.
    return "".join(result)


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    value = unicodedata.normalize("NFKD", str(text))
    value = _ascii_letters(value)
    value = value.replace("-", " ").replace("_", " ")
    value = re.sub(r"\s+", " ", value.strip())
    return value.casefold()


def slug_for_name(text: str | None) -> str | None:
    if not text:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    for definition in ABILITY_DEFINITIONS:
        if normalized in {
            _normalize(definition.slug),
            _normalize(definition.name),
            _normalize(definition.display_name()),
        }:
            return definition.slug
    return None
