from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.models import AppConfig
from app.i18n import DEFAULT_LANGUAGE, normalize_language


APP_NAME = "DocxToMarkdown"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


class SettingsManager:
    def __init__(self, settings_path: Path | None = None) -> None:
        self.path = settings_path or app_data_dir() / "settings.json"

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> AppConfig | None:
        if not self.exists():
            return None
        try:
            value: Any = json.loads(self.path.read_text(encoding="utf-8"))
            return AppConfig.from_dict(value) if isinstance(value, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @property
    def preferences_path(self) -> Path:
        return self.path.with_name("preferences.json")

    def load_language(self) -> str:
        try:
            value: Any = json.loads(self.preferences_path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                return normalize_language(str(value.get("language", DEFAULT_LANGUAGE)))
        except (OSError, ValueError, TypeError):
            pass
        return DEFAULT_LANGUAGE

    def save_language(self, language: str) -> None:
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"language": normalize_language(language)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.preferences_path)
