"""Fixed value sets used across the whole game."""

from __future__ import annotations

from enum import Enum, IntEnum, auto


class Difficulty(Enum):
    EASY = "Easy"
    MEDIUM = "Medium"
    HARD = "Hard"
    EXPERT = "Expert"

    @property
    def hint_count(self) -> int:
        return {"Easy": 5, "Medium": 3, "Hard": 2, "Expert": 1}[self.value]

    @property
    def shows_suspicion_meter(self) -> bool:
        return self is not Difficulty.EXPERT

    @property
    def xp_multiplier(self) -> float:
        return {"Easy": 0.7, "Medium": 1.0, "Hard": 1.4, "Expert": 2.0}[self.value]

    @property
    def unlock_xp(self) -> int:
        return {"Easy": 0, "Medium": 0, "Hard": 300, "Expert": 900}[self.value]

    @classmethod
    def parse(cls, raw: str) -> "Difficulty":
        for member in cls:
            if member.value.lower() == str(raw).strip().lower():
                return member
        raise ValueError(f"unknown difficulty: {raw!r}")


class EvidenceType(Enum):
    PHYSICAL = "Physical"
    DIGITAL = "Digital"
    TESTIMONY = "Testimony"
    DOCUMENT = "Document"
    CIRCUMSTANTIAL = "Circumstantial"

    @classmethod
    def parse(cls, raw: str) -> "EvidenceType":
        key = str(raw).strip().upper()
        for member in cls:
            if member.name == key or member.value.upper() == key:
                return member
        raise ValueError(f"unknown evidence type: {raw!r}")


class CaseStatus(Enum):
    LOCKED = auto()
    AVAILABLE = auto()
    IN_PROGRESS = auto()
    SOLVED = auto()
    FAILED = auto()


class Rank(IntEnum):
    ROOKIE = 0
    INVESTIGATOR = 500
    SENIOR_INVESTIGATOR = 1200
    LEAD_DETECTIVE = 2400
    CHIEF_INSPECTOR = 4200
    MASTER_DETECTIVE = 6500

    @classmethod
    def from_xp(cls, xp: int) -> "Rank":
        earned = [r for r in cls if xp >= r.value]
        return max(earned, key=lambda r: r.value) if earned else cls.ROOKIE

    @property
    def title(self) -> str:
        return self.name.replace("_", " ").title()

    @property
    def next_rank(self) -> "Rank | None":
        higher = [r for r in Rank if r.value > self.value]
        return min(higher, key=lambda r: r.value) if higher else None
