from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow


def light_palette() -> QPalette:
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#f4f7fb",
        QPalette.ColorRole.WindowText: "#25324a",
        QPalette.ColorRole.Base: "#ffffff",
        QPalette.ColorRole.AlternateBase: "#eef3fb",
        QPalette.ColorRole.ToolTipBase: "#26364d",
        QPalette.ColorRole.ToolTipText: "#ffffff",
        QPalette.ColorRole.Text: "#172033",
        QPalette.ColorRole.Button: "#eef3fb",
        QPalette.ColorRole.ButtonText: "#172033",
        QPalette.ColorRole.BrightText: "#ffffff",
        QPalette.ColorRole.Highlight: "#316bd6",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.PlaceholderText: "#7b8799",
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, color in colors.items():
            palette.setColor(group, role, QColor(color))
    for role, color in colors.items():
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(color))
    palette.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#94a0b2")
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.ButtonText,
        QColor("#94a0b2"),
    )
    return palette


def main() -> int:
    multiprocessing.freeze_support()
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName("DocxToMarkdown")
    app.setOrganizationName("DocxToMarkdown")
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
