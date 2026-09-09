"""Saving and loading, with two interchangeable backends.

The terminal build writes JSON files atomically. The browser build stores the
same JSON in localStorage. Both satisfy the same three-method interface, so
nothing above this layer knows or cares which is in use.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from ..config import SAVE_SCHEMA
from ..exceptions import CorruptSaveError, SaveVersionError
from ..models.case import Detective, InvestigationState


class Storage(Protocol):
    def read(self, key: str) -> str | None: ...
    def write(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class FileStorage:
    """Atomic file storage: write to a temporary file, then replace."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def read(self, key: str) -> str | None:
        path = self._path(key)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CorruptSaveError(f"cannot read save {path}: {exc}") from exc

    def write(self, key: str, value: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        if path.exists():
            try:
                backup = path.with_suffix(".bak")
                backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            except OSError:
                pass
        fd, tmp = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError as exc:
            Path(tmp).unlink(missing_ok=True)
            raise CorruptSaveError(f"cannot write save {path}: {exc}") from exc

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def backup(self, key: str) -> str | None:
        path = self._path(key).with_suffix(".bak")
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None


class MemoryStorage:
    """Used by the tests, and by the browser build before localStorage is ready."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def read(self, key: str) -> str | None:
        return self.data.get(key)

    def write(self, key: str, value: str) -> None:
        self.data[key] = value

    def delete(self, key: str) -> None:
        self.data.pop(key, None)


class BrowserStorage:
    """localStorage, reached through the Pyodide JavaScript bridge."""

    def __init__(self, prefix: str = "detectivex:") -> None:
        from js import localStorage  # type: ignore[import-not-found]

        self._ls = localStorage
        self.prefix = prefix

    def read(self, key: str) -> str | None:
        value = self._ls.getItem(self.prefix + key)
        return None if value is None else str(value)

    def write(self, key: str, value: str) -> None:
        self._ls.setItem(self.prefix + key, value)

    def delete(self, key: str) -> None:
        self._ls.removeItem(self.prefix + key)


class SaveManager:
    """Turns game objects into stored JSON and back, and survives corruption."""

    PROFILE_KEY = "profile"
    PROGRESS_KEY = "progress"

    def __init__(self, storage: Storage) -> None:
        self.storage = storage

    # -- profile ---------------------------------------------------------
    def save_profile(self, detective: Detective) -> None:
        payload = {"schema": SAVE_SCHEMA, "detective": detective.to_dict()}
        self.storage.write(self.PROFILE_KEY, json.dumps(payload, indent=2))

    def load_profile(self) -> Detective | None:
        raw = self.storage.read(self.PROFILE_KEY)
        if raw is None:
            return None
        payload = self._parse(raw, self.PROFILE_KEY)
        return Detective.from_dict(payload["detective"])

    # -- in-progress case ------------------------------------------------
    def save_progress(self, state: InvestigationState) -> None:
        payload = {"schema": SAVE_SCHEMA, "state": state.to_dict()}
        self.storage.write(self.PROGRESS_KEY, json.dumps(payload, indent=2))

    def load_progress(self) -> InvestigationState | None:
        raw = self.storage.read(self.PROGRESS_KEY)
        if raw is None:
            return None
        payload = self._parse(raw, self.PROGRESS_KEY)
        return InvestigationState.from_dict(payload["state"])

    def clear_progress(self) -> None:
        self.storage.delete(self.PROGRESS_KEY)

    def has_progress(self) -> bool:
        return self.storage.read(self.PROGRESS_KEY) is not None

    # -- recovery --------------------------------------------------------
    def _parse(self, raw: str, key: str) -> dict:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CorruptSaveError(
                f"the {key} save is damaged and cannot be read (line {exc.lineno})"
            ) from exc
        if not isinstance(payload, dict):
            raise CorruptSaveError(f"the {key} save is not in the expected format")
        schema = payload.get("schema")
        if schema is None:
            raise CorruptSaveError(f"the {key} save has no version marker")
        if schema > SAVE_SCHEMA:
            raise SaveVersionError(
                f"this {key} save was written by a newer version of the game"
            )
        return payload

    def recover(self, key: str) -> bool:
        """Restore a damaged save from its backup, if one exists."""
        if not isinstance(self.storage, FileStorage):
            self.storage.delete(key)
            return False
        backup = self.storage.backup(key)
        if backup is None:
            self.storage.delete(key)
            return False
        try:
            self._parse(backup, key)
        except (CorruptSaveError, SaveVersionError):
            self.storage.delete(key)
            return False
        self.storage.write(key, backup)
        return True
