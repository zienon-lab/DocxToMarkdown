from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class ConversionMode(str, Enum):
    SMART = "smart_sync"
    OVERWRITE = "overwrite"
    SKIP_EXISTING = "skip_existing"

    @property
    def label(self) -> str:
        return {
            self.SMART: "智能同步",
            self.OVERWRITE: "全部覆盖",
            self.SKIP_EXISTING: "仅转换不存在的文件",
        }[self]


class ConversionDirection(str, Enum):
    DOCX_TO_MARKDOWN = "docx_to_markdown"
    MARKDOWN_TO_DOCX = "markdown_to_docx"


@dataclass(slots=True)
class AppConfig:
    input_path: str = ""
    input_type: str = "file"
    direction: str = ConversionDirection.DOCX_TO_MARKDOWN.value
    output_path: str = ""
    recursive: bool = True
    mode: str = ConversionMode.SMART.value
    extract_media: bool = True
    preserve_structure: bool = True
    open_output: bool = True
    delete_records: bool = False
    language: str = "zh_CN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AppConfig":
        defaults = cls()
        valid_modes = {item.value for item in ConversionMode}
        valid_directions = {item.value for item in ConversionDirection}
        input_type = value.get("input_type", defaults.input_type)
        mode = value.get("mode", defaults.mode)
        direction = value.get("direction", defaults.direction)
        return cls(
            input_path=str(value.get("input_path", "")),
            input_type=input_type if input_type in {"file", "directory"} else "file",
            direction=(
                direction if direction in valid_directions else defaults.direction
            ),
            output_path=str(value.get("output_path", "")),
            recursive=bool(value.get("recursive", defaults.recursive)),
            mode=mode if mode in valid_modes else defaults.mode,
            extract_media=bool(value.get("extract_media", defaults.extract_media)),
            preserve_structure=bool(
                value.get("preserve_structure", defaults.preserve_structure)
            ),
            open_output=bool(value.get("open_output", defaults.open_output)),
            delete_records=bool(value.get("delete_records", defaults.delete_records)),
            language=(
                str(value.get("language", defaults.language))
                if str(value.get("language", defaults.language)) in {"zh_CN", "en_US"}
                else defaults.language
            ),
        )


@dataclass(slots=True)
class ConversionItem:
    source: Path
    output: Path
    relative_source: str
    source_hash: str
    should_convert: bool
    reason: str


@dataclass(slots=True)
class ScanResult:
    items: list[ConversionItem]
    input_path: Path
    output_path: Path

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def convert_count(self) -> int:
        return sum(item.should_convert for item in self.items)

    @property
    def skip_count(self) -> int:
        return self.total - self.convert_count


@dataclass(slots=True)
class ConversionSummary:
    total: int
    success: int = 0
    skipped: int = 0
    failed: int = 0
    cancelled: bool = False
    report_path: str = ""
    records_deleted: bool = False
    failures: list[tuple[str, str]] = field(default_factory=list)
