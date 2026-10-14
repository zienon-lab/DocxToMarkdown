from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

from app.i18n import tr
from app.models import (
    AppConfig,
    ConversionDirection,
    ConversionItem,
    ConversionMode,
    ConversionSummary,
    ScanResult,
)


MANIFEST_NAME = ".docx-to-markdown-sync.json"
REPORT_NAME = "conversion-report.csv"


class ConversionError(RuntimeError):
    """An expected, user-facing conversion error."""


def _norm_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_pandoc() -> Path | None:
    candidates: list[Path] = []
    override = os.environ.get("DOCX_TO_MARKDOWN_PANDOC")
    if override:
        candidates.append(Path(override))

    if getattr(sys, "frozen", False):
        bundle_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidates.append(bundle_dir / "tools" / "pandoc.exe")
        candidates.append(Path(sys.executable).resolve().parent / "tools" / "pandoc.exe")
    else:
        candidates.append(Path(__file__).resolve().parents[1] / "tools" / "pandoc.exe")

    located = shutil.which("pandoc")
    if located:
        candidates.append(Path(located))
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Pandoc" / "pandoc.exe")

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


class ConversionEngine:
    def __init__(self, pandoc_path: Path | None = None) -> None:
        self.pandoc_path = pandoc_path or find_pandoc()

    @staticmethod
    def validate_config(config: AppConfig, create_output: bool = False) -> tuple[Path, Path]:
        input_text = config.input_path.strip().strip('"')
        output_text = config.output_path.strip().strip('"')
        if not input_text:
            raise ConversionError(tr(config.language, "error_choose_input"))
        if not output_text:
            raise ConversionError(tr(config.language, "error_choose_output"))

        source = Path(input_text).expanduser()
        output = Path(output_text).expanduser()
        if not source.exists():
            raise ConversionError(tr(config.language, "error_input_missing", path=source))
        if not source.is_file() and not source.is_dir():
            raise ConversionError(tr(config.language, "error_expected_input"))
        if source.is_file():
            expected_suffixes = ConversionEngine._source_suffixes(config)
            if source.suffix.lower() not in expected_suffixes:
                raise ConversionError(
                    tr(
                        config.language,
                        "error_wrong_source_format",
                        format=ConversionEngine._source_format(config),
                    )
                )

        if output.exists() and not output.is_dir():
            raise ConversionError(tr(config.language, "error_output_is_file"))
        if create_output:
            try:
                output.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=output, prefix=".write-test-", delete=True):
                    pass
            except OSError as exc:
                raise ConversionError(
                    tr(config.language, "error_output_write", path=output, error=exc)
                ) from exc
        return source.resolve(), output.resolve()

    @staticmethod
    def collect_sources(config: AppConfig, source: Path) -> list[Path]:
        if source.is_file():
            return [source]
        iterator: Iterable[Path]
        iterator = source.rglob("*") if config.recursive else source.glob("*")
        files = [
            path.resolve()
            for path in iterator
            if path.is_file()
            and path.suffix.lower() in ConversionEngine._source_suffixes(config)
            and not (
                config.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
                and path.name.startswith("~$")
            )
        ]
        return sorted(files, key=lambda path: str(path).casefold())

    @staticmethod
    def _load_manifest(output: Path) -> dict[str, dict[str, str]]:
        path = output / MANIFEST_NAME
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            files = value.get("files", {}) if isinstance(value, dict) else {}
            return files if isinstance(files, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    @staticmethod
    def _output_for(config: AppConfig, source_root: Path, source: Path, output: Path) -> tuple[Path, str]:
        if source_root.is_file():
            relative = Path(source.name)
        else:
            relative = source.relative_to(source_root)
        output_relative = relative.with_suffix(ConversionEngine._output_suffix(config))
        if not config.preserve_structure:
            output_relative = Path(output_relative.name)
        return output / output_relative, relative.as_posix()

    def scan(self, config: AppConfig) -> ScanResult:
        source_root, output = self.validate_config(config, create_output=False)
        sources = self.collect_sources(config, source_root)
        manifest = self._load_manifest(output)
        items: list[ConversionItem] = []
        output_owners: dict[str, Path] = {}

        for source in sources:
            destination, relative_source = self._output_for(config, source_root, source, output)
            destination_key = _norm_key(destination)
            previous_owner = output_owners.get(destination_key)
            if previous_owner is not None:
                raise ConversionError(
                    tr(
                        config.language,
                        "error_duplicate",
                        first=previous_owner,
                        second=source,
                        name=destination.name,
                    )
                )
            output_owners[destination_key] = source

            source_hash = file_sha256(source) if config.mode == ConversionMode.SMART.value else ""
            if config.mode == ConversionMode.OVERWRITE.value:
                should_convert, reason = True, tr(config.language, "reason_overwrite")
            elif config.mode == ConversionMode.SKIP_EXISTING.value:
                should_convert = not destination.exists()
                reason = tr(
                    config.language,
                    "reason_target_missing" if should_convert else "reason_target_exists",
                )
            elif not destination.exists():
                should_convert, reason = True, tr(config.language, "reason_target_missing")
            else:
                record = manifest.get(_norm_key(source), {})
                old_hash = record.get("sha256", "") if isinstance(record, dict) else ""
                if old_hash:
                    should_convert = old_hash != source_hash
                    reason = tr(
                        config.language,
                        "reason_changed" if should_convert else "reason_unchanged",
                    )
                else:
                    try:
                        should_convert = source.stat().st_mtime_ns > destination.stat().st_mtime_ns
                    except OSError:
                        should_convert = True
                    reason = tr(
                        config.language,
                        "reason_source_newer" if should_convert else "reason_no_update",
                    )

            items.append(
                ConversionItem(
                    source=source,
                    output=destination,
                    relative_source=relative_source,
                    source_hash=source_hash,
                    should_convert=should_convert,
                    reason=reason,
                )
            )
        return ScanResult(items=items, input_path=source_root, output_path=output)

    def require_pandoc(self, language: str = "zh_CN") -> Path:
        if not self.pandoc_path or not self.pandoc_path.is_file():
            raise ConversionError(tr(language, "error_pandoc_missing"))
        return self.pandoc_path

    @staticmethod
    def _source_suffixes(config: AppConfig) -> set[str]:
        if config.direction == ConversionDirection.MARKDOWN_TO_DOCX.value:
            return {".md", ".markdown"}
        return {".docx"}

    @staticmethod
    def _source_format(config: AppConfig) -> str:
        if config.direction == ConversionDirection.MARKDOWN_TO_DOCX.value:
            return "Markdown"
        return "DOCX"

    @staticmethod
    def _output_format(config: AppConfig) -> str:
        if config.direction == ConversionDirection.MARKDOWN_TO_DOCX.value:
            return "DOCX"
        return "Markdown"

    @staticmethod
    def _output_suffix(config: AppConfig) -> str:
        if config.direction == ConversionDirection.MARKDOWN_TO_DOCX.value:
            return ".docx"
        return ".md"

    @staticmethod
    def _media_destination(item: ConversionItem) -> Path:
        return item.output.parent / "assets" / item.output.stem

    def convert_one(self, config: AppConfig, item: ConversionItem) -> None:
        pandoc = self.require_pandoc(config.language)
        item.output.parent.mkdir(parents=True, exist_ok=True)
        unique = uuid.uuid4().hex
        temporary_output = item.output.parent / (
            f".{item.output.stem}.{unique}.tmp{self._output_suffix(config)}"
        )
        staging_media: Path | None = None
        final_media: Path | None = None
        backup_media: Path | None = None

        if config.direction == ConversionDirection.MARKDOWN_TO_DOCX.value:
            command = [
                str(pandoc),
                str(item.source),
                "--from=gfm",
                "--to=docx",
                f"--output={temporary_output}",
                f"--resource-path={item.source.parent}",
            ]
        else:
            command = [
                str(pandoc),
                str(item.source),
                "--from=docx",
                "--to=gfm",
                f"--output={temporary_output.name}",
                "--wrap=none",
                "--markdown-headings=atx",
                "--track-changes=accept",
            ]
        if (
            config.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
            and config.extract_media
        ):
            staging_name = f".{item.output.stem}-{unique}"
            staging_media = item.output.parent / "assets" / staging_name
            final_media = self._media_destination(item)
            command.append(f"--extract-media=assets/{staging_name}")

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            result = subprocess.run(
                command,
                cwd=item.output.parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                creationflags=creationflags,
                check=False,
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or tr(config.language, "error_pandoc_unknown")).strip()
                raise ConversionError(detail)
            if not temporary_output.is_file():
                raise ConversionError(
                    tr(
                        config.language,
                        "error_no_output",
                        format=self._output_format(config),
                    )
                )

            if staging_media is not None and final_media is not None:
                markdown = temporary_output.read_text(encoding="utf-8")
                markdown = markdown.replace(
                    f"assets/{staging_media.name}/", f"assets/{final_media.name}/"
                )
                temporary_output.write_text(markdown, encoding="utf-8", newline="\n")
                final_media.parent.mkdir(parents=True, exist_ok=True)
                if final_media.exists():
                    backup_media = final_media.with_name(f".{final_media.name}.{unique}.bak")
                    final_media.rename(backup_media)
                if staging_media.exists():
                    staging_media.rename(final_media)

            os.replace(temporary_output, item.output)
            if backup_media is not None and backup_media.exists():
                shutil.rmtree(backup_media, ignore_errors=True)
        except (OSError, subprocess.SubprocessError, ConversionError) as exc:
            if backup_media is not None and backup_media.exists() and final_media is not None:
                if final_media.exists():
                    shutil.rmtree(final_media, ignore_errors=True)
                backup_media.rename(final_media)
            raise ConversionError(str(exc)) from exc
        finally:
            try:
                temporary_output.unlink(missing_ok=True)
            except OSError:
                pass
            if staging_media is not None and staging_media.exists():
                shutil.rmtree(staging_media, ignore_errors=True)

    @staticmethod
    def _save_manifest(output: Path, records: dict[str, dict[str, str]]) -> None:
        path = output / MANIFEST_NAME
        temporary = path.with_suffix(".tmp")
        payload = {"version": 1, "updated_at": datetime.now().isoformat(timespec="seconds"), "files": records}
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _write_report(output: Path, rows: list[list[str]], language: str) -> Path:
        report = output / REPORT_NAME
        with report.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                [
                    tr(language, "report_time"),
                    tr(language, "report_source"),
                    tr(language, "report_output"),
                    tr(language, "report_result"),
                    tr(language, "report_detail"),
                ]
            )
            writer.writerows(rows)
        return report

    def run(
        self,
        config: AppConfig,
        scan: ScanResult,
        cancelled: Callable[[], bool],
        progress: Callable[[int, int, ConversionItem, str], None],
    ) -> ConversionSummary:
        _, output = self.validate_config(config, create_output=True)
        if scan.convert_count:
            self.require_pandoc(config.language)
        records = self._load_manifest(output)
        summary = ConversionSummary(total=scan.total)
        report_rows: list[list[str]] = []

        for index, item in enumerate(scan.items, start=1):
            if cancelled():
                summary.cancelled = True
                break
            timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
            if not item.should_convert:
                summary.skipped += 1
                message = item.reason
                report_rows.append(
                    [timestamp, str(item.source), str(item.output), tr(config.language, "status_skipped"), message]
                )
                progress(
                    index,
                    scan.total,
                    item,
                    tr(config.language, "progress_skip", file=item.relative_source, reason=message),
                )
                if config.mode == ConversionMode.SMART.value and item.source_hash:
                    records[_norm_key(item.source)] = {
                        "sha256": item.source_hash,
                        "output": str(item.output),
                    }
                continue

            progress(
                index - 1,
                scan.total,
                item,
                tr(config.language, "progress_converting", file=item.relative_source),
            )
            try:
                self.convert_one(config, item)
                summary.success += 1
                message = item.reason
                report_rows.append(
                    [timestamp, str(item.source), str(item.output), tr(config.language, "status_success"), message]
                )
                if config.mode == ConversionMode.SMART.value:
                    digest = item.source_hash or file_sha256(item.source)
                    records[_norm_key(item.source)] = {"sha256": digest, "output": str(item.output)}
                progress(
                    index,
                    scan.total,
                    item,
                    tr(config.language, "progress_done", file=item.relative_source),
                )
            except Exception as exc:  # keep a bad document from stopping the batch
                summary.failed += 1
                detail = str(exc).strip() or exc.__class__.__name__
                summary.failures.append((str(item.source), detail))
                report_rows.append(
                    [timestamp, str(item.source), str(item.output), tr(config.language, "status_failed"), detail]
                )
                progress(
                    index,
                    scan.total,
                    item,
                    tr(config.language, "progress_failed", file=item.relative_source, reason=detail),
                )

        if config.delete_records:
            summary.records_deleted = True
            for record_path in (output / MANIFEST_NAME, output / REPORT_NAME):
                try:
                    record_path.unlink(missing_ok=True)
                except OSError as exc:
                    summary.failures.append(
                        (
                            str(record_path),
                            tr(config.language, "record_delete_failed", error=exc),
                        )
                    )
        else:
            try:
                self._save_manifest(output, records)
            except OSError as exc:
                summary.failures.append(
                    (str(output / MANIFEST_NAME), tr(config.language, "manifest_save_failed", error=exc))
                )
            try:
                summary.report_path = str(self._write_report(output, report_rows, config.language))
            except OSError as exc:
                summary.failures.append(
                    (str(output / REPORT_NAME), tr(config.language, "report_save_failed", error=exc))
                )
        return summary


def pandoc_version(pandoc: Path) -> str:
    try:
        result = subprocess.run(
            [str(pandoc), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.stdout.splitlines()[0] if result.returncode == 0 else pandoc.name
    except (OSError, subprocess.SubprocessError):
        return pandoc.name
