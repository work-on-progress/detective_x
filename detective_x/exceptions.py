"""Every error this program raises descends from DetectiveXError."""

from __future__ import annotations


class DetectiveXError(Exception):
    """Base class for all Detective X errors."""


class CaseDataError(DetectiveXError):
    """A case file is missing, unreadable, or structurally invalid."""


class CorruptSaveError(DetectiveXError):
    """The save file exists but cannot be understood."""


class SaveVersionError(DetectiveXError):
    """The save file was written by an incompatible version."""


class UnknownScoreAction(DetectiveXError):
    """A scoring action that is not in the score table."""


class InvalidChoice(DetectiveXError):
    """The player selected something the current screen cannot accept."""


class CaseLocked(DetectiveXError):
    """The player has not earned enough XP to open this case."""
