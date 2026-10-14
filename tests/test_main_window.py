from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QPushButton, QRadioButton

from app.i18n import tr
from app.main_window import MainWindow
from app.models import AppConfig, ConversionDirection


class MainWindowDirectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def make_window(self) -> MainWindow:
        with (
            patch("app.main_window.SettingsManager.load_language", return_value="zh_CN"),
            patch("app.main_window.SettingsManager.load", return_value=None),
            patch("app.main_window.find_pandoc", return_value=None),
        ):
            return MainWindow()

    def test_main_window_does_not_show_conversion_direction_controls(self) -> None:
        window = self.make_window()
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()

        direction_labels = {
            tr("zh_CN", "direction_docx_to_markdown"),
            tr("zh_CN", "direction_markdown_to_docx"),
        }
        visible_direction_radios = [
            radio.text()
            for radio in window.findChildren(QRadioButton)
            if radio.isVisibleTo(window) and radio.text() in direction_labels
        ]

        self.assertEqual(visible_direction_radios, [])

    def test_file_selection_dialog_defaults_to_current_direction_and_continues(self) -> None:
        window = self.make_window()
        self.addCleanup(window.close)
        window._apply_config(
            AppConfig(direction=ConversionDirection.MARKDOWN_TO_DOCX.value)
        )
        interaction: dict[str, object] = {}

        def continue_with_current_direction() -> None:
            try:
                dialog = QApplication.activeModalWidget()
                self.assertIsInstance(dialog, QDialog)
                selected = [
                    radio.property("direction")
                    for radio in dialog.findChildren(QRadioButton)
                    if radio.isChecked()
                ]
                interaction["selected"] = selected
                button = dialog.findChild(QPushButton, "continueButton")
                self.assertIsNotNone(button)
                button.click()
            except Exception as exc:  # pragma: no cover - reported below
                interaction["error"] = exc
                if isinstance(QApplication.activeModalWidget(), QDialog):
                    QApplication.activeModalWidget().reject()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(continue_with_current_direction)
        timer.start(0)
        with patch.object(
            QFileDialog,
            "getOpenFileName",
            return_value=("C:/docs/example.md", ""),
        ) as file_picker:
            window._select_file()
        timer.stop()

        if "error" in interaction:
            raise interaction["error"]  # type: ignore[misc]
        self.assertEqual(
            interaction.get("selected"),
            [ConversionDirection.MARKDOWN_TO_DOCX.value],
        )
        self.assertEqual(
            window._config().direction,
            ConversionDirection.MARKDOWN_TO_DOCX.value,
        )
        self.assertEqual(window.input_edit.text(), "C:/docs/example.md")
        self.assertIn("Markdown", file_picker.call_args.args[3])

    def test_cancel_direction_dialog_does_not_open_folder_picker(self) -> None:
        window = self.make_window()
        self.addCleanup(window.close)
        before = window._config().direction

        def cancel_direction_dialog() -> None:
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, QDialog):
                dialog.reject()

        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(cancel_direction_dialog)
        timer.start(0)
        with patch.object(
            QFileDialog, "getExistingDirectory", return_value=""
        ) as folder_picker:
            window._select_input_folder()
        timer.stop()

        self.assertEqual(window._config().direction, before)
        folder_picker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
