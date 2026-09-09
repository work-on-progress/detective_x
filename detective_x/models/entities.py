"""The objects a single investigation is made of."""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import EvidenceType


@dataclass
class Evidence:
    """One clue. Reliability scales how much its weight counts."""

    id: str
    name: str
    description: str
    type: EvidenceType
    reliability: int
    weight: int = 0
    implicates: str | None = None
    is_red_herring: bool = False
    cleared_by: str | None = None
    requires: list[str] = field(default_factory=list)
    unlocks: list[str] = field(default_factory=list)
    matches: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not 0 <= self.reliability <= 100:
            raise ValueError(f"{self.id}: reliability {self.reliability} outside 0-100")
        if self.weight < 0:
            raise ValueError(f"{self.id}: weight cannot be negative")

    @property
    def is_confirmed(self) -> bool:
        return self.reliability >= 90

    @property
    def comparable(self) -> bool:
        """Trace evidence can be matched against a belonging. Most clues cannot."""
        return bool(self.matches) or "comparable" in self.tags

    @property
    def effective_weight(self) -> int:
        return round(self.weight * self.reliability / 100)

    def __str__(self) -> str:
        return f"{self.name} ({self.reliability}% reliable)"

    @classmethod
    def from_dict(cls, raw: dict) -> "Evidence":
        return cls(
            id=raw["id"],
            name=raw["name"],
            description=raw.get("description", ""),
            type=EvidenceType.parse(raw["type"]),
            reliability=int(raw["reliability"]),
            weight=int(raw.get("weight", 0)),
            implicates=raw.get("implicates"),
            is_red_herring=bool(raw.get("is_red_herring", False)),
            cleared_by=raw.get("cleared_by"),
            requires=list(raw.get("requires", [])),
            unlocks=list(raw.get("unlocks", [])),
            matches=list(raw.get("matches", [])),
            tags=list(raw.get("tags", [])),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "type": self.type.value,
            "reliability": self.reliability,
            "weight": self.weight,
            "implicates": self.implicates,
            "is_red_herring": self.is_red_herring,
            "cleared_by": self.cleared_by,
            "comparable": self.comparable,
            "tags": self.tags,
        }


@dataclass
class Statement:
    """One suspect's answer on one shared topic key."""

    topic: str
    claim: str
    question: str
    text: str
    unlocked_by: str | None = None
    is_lie: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "Statement":
        return cls(
            topic=raw["topic"],
            claim=raw["claim"],
            question=raw["question"],
            text=raw["text"],
            unlocked_by=raw.get("unlocked_by"),
            is_lie=bool(raw.get("is_lie", False)),
        )


@dataclass
class Suspect:
    id: str
    name: str
    age: int
    occupation: str
    relation: str
    motive: str
    base_suspicion: int
    belongings: list[str] = field(default_factory=list)
    statements: list[Statement] = field(default_factory=list)
    portrait: str = ""

    def statement_on(self, topic: str) -> Statement | None:
        return next((s for s in self.statements if s.topic == topic), None)

    def available_statements(self, found: set[str]) -> list[Statement]:
        return [
            s for s in self.statements
            if s.unlocked_by is None or s.unlocked_by in found
        ]

    @classmethod
    def from_dict(cls, raw: dict) -> "Suspect":
        return cls(
            id=raw["id"],
            name=raw["name"],
            age=int(raw.get("age", 0)),
            occupation=raw.get("occupation", ""),
            relation=raw.get("relation", ""),
            motive=raw.get("motive", ""),
            base_suspicion=int(raw.get("base_suspicion", 0)),
            belongings=list(raw.get("belongings", [])),
            statements=[Statement.from_dict(s) for s in raw.get("statements", [])],
            portrait=raw.get("portrait", ""),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "age": self.age,
            "occupation": self.occupation,
            "relation": self.relation,
            "motive": self.motive,
            "belongings": self.belongings,
        }


@dataclass
class Searchable:
    id: str
    label: str
    yields: list[str] = field(default_factory=list)
    flavour: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "Searchable":
        return cls(
            id=raw["id"],
            label=raw["label"],
            yields=list(raw.get("yields", [])),
            flavour=raw.get("flavour", ""),
        )


@dataclass
class Location:
    id: str
    name: str
    icon: str
    description: str
    searchables: list[Searchable] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "Location":
        return cls(
            id=raw["id"],
            name=raw["name"],
            icon=raw.get("icon", "[ ]"),
            description=raw.get("description", ""),
            searchables=[Searchable.from_dict(s) for s in raw.get("searchables", [])],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
        }


@dataclass
class TimelineEvent:
    time: str
    text: str
    hidden: bool = False
    revealed_by: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "TimelineEvent":
        return cls(
            time=raw["time"],
            text=raw["text"],
            hidden=bool(raw.get("hidden", False)),
            revealed_by=raw.get("revealed_by"),
        )

    def is_visible(self, found: set[str]) -> bool:
        if not self.hidden:
            return True
        return self.revealed_by is not None and self.revealed_by in found
