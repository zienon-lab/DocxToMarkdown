from __future__ import annotations

import os
import base64
import subprocess
import tempfile
import time
import unittest
import zipfile
from pathlib import Path

from app.converter import (
    MANIFEST_NAME,
    REPORT_NAME,
    ConversionEngine,
    ConversionError,
    find_pandoc,
)
from app.models import AppConfig, ConversionDirection, ConversionMode
from app.settings_manager import SettingsManager


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def make_docx(path: Path, text: str = "Hello 世界") -> None:
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p><w:sectPr/></w:body>
</w:document>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", CONTENT_TYPES)
        package.writestr("_rels/.rels", ROOT_RELS)
        package.writestr("word/document.xml", document)


class CoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.input = self.root / "Word 输入"
        self.output = self.root / "Markdown 输出"
        self.input.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def config(self, **changes: object) -> AppConfig:
        values = AppConfig(
            input_path=str(self.input),
            input_type="directory",
            output_path=str(self.output),
            recursive=True,
            mode=ConversionMode.SMART.value,
            extract_media=True,
            preserve_structure=True,
            open_output=False,
        ).to_dict()
        values.update(changes)
        return AppConfig.from_dict(values)

    def test_recursive_scan_skips_word_temporary_files(self) -> None:
        make_docx(self.input / "一级.docx")
        make_docx(self.input / "子目录" / "二级 文档.docx")
        make_docx(self.input / "~$一级.docx")
        scan = ConversionEngine().scan(self.config())
        self.assertEqual(scan.total, 2)
        self.assertEqual(scan.convert_count, 2)
        outputs = {item.output.relative_to(self.output).as_posix() for item in scan.items}
        self.assertEqual(outputs, {"一级.md", "子目录/二级 文档.md"})

    def test_non_recursive_scan(self) -> None:
        make_docx(self.input / "root.docx")
        make_docx(self.input / "nested" / "child.docx")
        scan = ConversionEngine().scan(self.config(recursive=False))
        self.assertEqual([item.source.name for item in scan.items], ["root.docx"])

    def test_reverse_scan_detects_folder_without_input_type_choice(self) -> None:
        (self.input / "一级.md").write_text("# 一级", encoding="utf-8")
        nested = self.input / "子目录"
        nested.mkdir()
        (nested / "二级.markdown").write_text("# 二级", encoding="utf-8")
        (nested / "忽略.txt").write_text("ignore", encoding="utf-8")
        scan = ConversionEngine().scan(
            self.config(
                input_type="file",
                direction=ConversionDirection.MARKDOWN_TO_DOCX.value,
            )
        )
        outputs = {item.output.relative_to(self.output).as_posix() for item in scan.items}
        self.assertEqual(outputs, {"一级.docx", "子目录/二级.docx"})

    def test_flattened_duplicate_names_are_rejected(self) -> None:
        make_docx(self.input / "a" / "same.docx")
        make_docx(self.input / "b" / "same.docx")
        with self.assertRaisesRegex(ConversionError, "同名文件冲突"):
            ConversionEngine().scan(self.config(preserve_structure=False))

    def test_modes(self) -> None:
        source = self.input / "a.docx"
        make_docx(source)
        self.output.mkdir()
        destination = self.output / "a.md"
        destination.write_text("old", encoding="utf-8")
        future = time.time() + 5
        os.utime(destination, (future, future))

        smart = ConversionEngine().scan(self.config())
        self.assertEqual(smart.skip_count, 1)
        overwrite = ConversionEngine().scan(self.config(mode=ConversionMode.OVERWRITE.value))
        self.assertEqual(overwrite.convert_count, 1)
        skip = ConversionEngine().scan(self.config(mode=ConversionMode.SKIP_EXISTING.value))
        self.assertEqual(skip.skip_count, 1)

    def test_settings_round_trip(self) -> None:
        path = self.root / "settings" / "settings.json"
        manager = SettingsManager(path)
        expected = self.config(open_output=True, delete_records=True)
        manager.save(expected)
        actual = manager.load()
        self.assertIsNotNone(actual)
        self.assertEqual(actual.to_dict(), expected.to_dict())

    def test_old_settings_default_to_docx_to_markdown(self) -> None:
        config = AppConfig.from_dict({"input_path": "old.docx"})
        self.assertEqual(
            config.direction, ConversionDirection.DOCX_TO_MARKDOWN.value
        )

    def test_language_preference_and_english_errors(self) -> None:
        manager = SettingsManager(self.root / "settings" / "settings.json")
        manager.save_language("en_US")
        self.assertEqual(manager.load_language(), "en_US")
        config = self.config(input_path=str(self.root / "missing.docx"), language="en_US")
        with self.assertRaisesRegex(ConversionError, "not found"):
            ConversionEngine().scan(config)

    @unittest.skipUnless(find_pandoc(), "Pandoc is not installed")
    def test_real_pandoc_conversion_and_hash_sync(self) -> None:
        source = self.input / "中文 空格.docx"
        make_docx(source, "转换成功")
        config = self.config(extract_media=False)
        engine = ConversionEngine()
        first_scan = engine.scan(config)
        updates: list[str] = []
        summary = engine.run(
            config,
            first_scan,
            cancelled=lambda: False,
            progress=lambda current, total, item, message: updates.append(message),
        )
        self.assertEqual(summary.success, 1)
        markdown = self.output / "中文 空格.md"
        self.assertIn("转换成功", markdown.read_text(encoding="utf-8"))
        second_scan = engine.scan(config)
        self.assertEqual(second_scan.skip_count, 1)

    @unittest.skipUnless(find_pandoc(), "Pandoc is not installed")
    def test_real_markdown_to_docx_with_relative_image(self) -> None:
        image = self.input / "像素.png"
        image.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
        source = self.input / "反向转换.md"
        source.write_text(
            "# 反向转换成功\n\n![相对路径图片](像素.png)\n",
            encoding="utf-8",
        )
        config = self.config(
            input_path=str(source),
            input_type="directory",
            direction=ConversionDirection.MARKDOWN_TO_DOCX.value,
        )
        engine = ConversionEngine()
        summary = engine.run(
            config,
            engine.scan(config),
            cancelled=lambda: False,
            progress=lambda current, total, item, message: None,
        )
        self.assertEqual(summary.success, 1)
        destination = self.output / "反向转换.docx"
        self.assertTrue(destination.is_file())
        with zipfile.ZipFile(destination) as package:
            document_xml = package.read("word/document.xml").decode("utf-8")
            self.assertIn("反向转换成功", document_xml)
            self.assertTrue(
                any(name.startswith("word/media/") for name in package.namelist())
            )

    @unittest.skipUnless(find_pandoc(), "Pandoc is not installed")
    def test_real_image_extraction(self) -> None:
        image = self.root / "像素.png"
        image.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            )
        )
        source_markdown = self.root / "source.md"
        source_markdown.write_text("# 图片测试\n\n![示例](像素.png)\n", encoding="utf-8")
        source = self.input / "带图片.docx"
        subprocess.run(
            [str(find_pandoc()), str(source_markdown), "-o", str(source)],
            cwd=self.root,
            check=True,
            capture_output=True,
        )
        config = self.config(extract_media=True)
        engine = ConversionEngine()
        summary = engine.run(
            config,
            engine.scan(config),
            cancelled=lambda: False,
            progress=lambda current, total, item, message: None,
        )
        self.assertEqual(summary.success, 1)
        markdown = (self.output / "带图片.md").read_text(encoding="utf-8")
        self.assertIn("assets/带图片/", markdown)
        extracted = list((self.output / "assets" / "带图片").rglob("*.*"))
        self.assertTrue(extracted)

    @unittest.skipUnless(find_pandoc(), "Pandoc is not installed")
    def test_delete_generated_record_files(self) -> None:
        source = self.input / "只保留结果.docx"
        make_docx(source, "No record files")
        self.output.mkdir()
        (self.output / MANIFEST_NAME).write_text("{}", encoding="utf-8")
        (self.output / REPORT_NAME).write_text("old report", encoding="utf-8")
        config = self.config(extract_media=False, delete_records=True)
        engine = ConversionEngine()
        summary = engine.run(
            config,
            engine.scan(config),
            cancelled=lambda: False,
            progress=lambda current, total, item, message: None,
        )
        self.assertEqual(summary.success, 1)
        self.assertTrue(summary.records_deleted)
        self.assertEqual(summary.report_path, "")
        self.assertTrue((self.output / "只保留结果.md").is_file())
        self.assertFalse((self.output / MANIFEST_NAME).exists())
        self.assertFalse((self.output / REPORT_NAME).exists())


if __name__ == "__main__":
    unittest.main()
