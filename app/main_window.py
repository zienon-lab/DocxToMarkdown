from __future__ import annotations

import html
from pathlib import Path

from PySide6.QtCore import QEvent, QSignalBlocker, QThread, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDragEnterEvent, QDropEvent, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.converter import ConversionEngine, ConversionError, find_pandoc, pandoc_version
from app.i18n import tr
from app.models import (
    AppConfig,
    ConversionDirection,
    ConversionMode,
    ConversionSummary,
    ScanResult,
)
from app.settings_manager import SettingsManager
from app.worker import ConversionWorker


APP_STYLE = """
QMainWindow { background: #f4f7fb; }
QWidget { color: #25324a; font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 12px; }
QFrame#header { background: #2457c5; border-radius: 10px; }
QLabel#title { color: white; font-size: 19px; font-weight: 700; }
QLabel#subtitle { color: #dbe7ff; font-size: 11px; }
QLabel#languageLabel { color: white; font-weight: 600; }
QComboBox { background: white; color: #172033; border: 1px solid #cbd6e6; border-radius: 5px; padding: 4px 8px; min-width: 82px; }
QComboBox QAbstractItemView { background: white; color: #172033; selection-background-color: #316bd6; selection-color: white; }
QGroupBox { background: white; border: 1px solid #dce4f1; border-radius: 8px; margin-top: 11px; padding: 9px 9px 8px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #315486; }
QLineEdit, QTextEdit { background: #fbfcff; color: #172033; border: 1px solid #cbd6e6; border-radius: 5px; padding: 5px; selection-background-color: #316bd6; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #316bd6; }
QPushButton { color: #172033; background: #eef3fb; border: 1px solid #c8d5e8; border-radius: 5px; padding: 5px 10px; }
QPushButton:hover { background: #e1eafb; border-color: #8eabd4; }
QPushButton:pressed { background: #d4e1f5; }
QPushButton:disabled { color: #94a0b2; background: #f1f3f6; border-color: #dde2e9; }
QPushButton#primary { color: white; background: #316bd6; border-color: #316bd6; font-weight: 600; padding: 7px 14px; }
QPushButton#primary:hover { background: #245cc3; }
QPushButton#sync { color: white; background: #168464; border-color: #168464; font-weight: 600; padding: 7px 14px; }
QPushButton#sync:hover { background: #0f7356; }
QPushButton#cancel { color: #ae3c3c; background: #fff5f5; border-color: #ebc3c3; }
QProgressBar { border: 1px solid #d0d9e7; border-radius: 6px; background: #edf1f7; text-align: center; min-height: 18px; }
QProgressBar::chunk { background: #3b74db; border-radius: 5px; }
QRadioButton, QCheckBox { color: #25324a; spacing: 7px; }
QCheckBox:disabled { color: #9aa5b5; }
QCheckBox::indicator:disabled { background-color: #edf0f4; border: 1px solid #aeb8c5; border-radius: 2px; }
QLabel#statusPill { color: #28543f; background: #e9f7f0; border-radius: 8px; padding: 5px 9px; }
QFrame#helpBar { background: #eaf1fc; border: 1px solid #cbdaf0; border-radius: 6px; }
QLabel#helpIcon { color: #2457c5; font-weight: 700; font-size: 14px; }
QLabel#helpText { color: #27496f; }
QToolTip { color: #ffffff; background-color: #26364d; border: 1px solid #4f6380; padding: 5px; }
QMessageBox { background-color: #ffffff; }
QMessageBox QLabel { color: #111827; background-color: transparent; font-size: 12px; }
QMessageBox QPushButton { color: #111827; background-color: #eef3fb; border: 1px solid #9eb1cc; min-width: 68px; }
QMessageBox QPushButton:hover { color: #ffffff; background-color: #316bd6; border-color: #316bd6; }
"""


def create_app_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#2457c5"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(3, 3, 58, 58, 13, 13)
    painter.setPen(QColor("white"))
    font = QFont("Segoe UI", 20, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "M↓")
    painter.end()
    return QIcon(pixmap)


class ConversionDirectionDialog(QDialog):
    def __init__(self, language: str, current_direction: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr(language, "conversion_direction"))

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr(language, "direction_prompt")))

        self.docx_to_markdown_radio = QRadioButton(
            tr(language, "direction_docx_to_markdown")
        )
        self.docx_to_markdown_radio.setProperty(
            "direction", ConversionDirection.DOCX_TO_MARKDOWN.value
        )
        self.markdown_to_docx_radio = QRadioButton(
            tr(language, "direction_markdown_to_docx")
        )
        self.markdown_to_docx_radio.setProperty(
            "direction", ConversionDirection.MARKDOWN_TO_DOCX.value
        )
        self.markdown_to_docx_radio.setChecked(
            current_direction == ConversionDirection.MARKDOWN_TO_DOCX.value
        )
        self.docx_to_markdown_radio.setChecked(
            current_direction != ConversionDirection.MARKDOWN_TO_DOCX.value
        )
        layout.addWidget(self.docx_to_markdown_radio)
        layout.addWidget(self.markdown_to_docx_radio)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        continue_button = buttons.addButton(
            tr(language, "button_continue"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        continue_button.setObjectName("continueButton")
        continue_button.setDefault(True)
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText(tr(language, "button_cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_direction(self) -> str:
        if self.markdown_to_docx_radio.isChecked():
            return ConversionDirection.MARKDOWN_TO_DOCX.value
        return ConversionDirection.DOCX_TO_MARKDOWN.value


class MainWindow(QMainWindow):
    cancel_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.settings_manager = SettingsManager()
        self.language = self.settings_manager.load_language()
        self.engine = ConversionEngine()
        self._thread: QThread | None = None
        self._worker: ConversionWorker | None = None
        self._running = False
        self._close_after_cancel = False
        self.direction = ConversionDirection.DOCX_TO_MARKDOWN.value

        self.setWindowIcon(create_app_icon())
        self.setAcceptDrops(True)
        self._build_ui()
        self.setStyleSheet(APP_STYLE)
        self._fit_to_desktop()
        self._connect_signals()
        self._install_context_help()
        self._apply_language(initial=True)
        self._load_settings_on_startup()
        self._update_pandoc_status()

    def _fit_to_desktop(self) -> None:
        screen = QApplication.primaryScreen()
        if screen is None:
            self.setMinimumSize(620, 480)
            self.resize(730, 560)
            return
        available = screen.availableGeometry()
        minimum_width = min(660, max(540, available.width() - 32))
        minimum_height = min(500, max(440, available.height() - 32))
        self.setMinimumSize(minimum_width, minimum_height)
        self.resize(min(740, available.width() - 20), min(560, available.height() - 20))

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 10, 12, 9)
        root.setSpacing(7)

        header = QFrame(objectName="header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(15, 9, 13, 9)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(1)
        self.title_label = QLabel(objectName="title")
        self.subtitle_label = QLabel(objectName="subtitle")
        title_layout.addWidget(self.title_label)
        title_layout.addWidget(self.subtitle_label)
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        self.language_label = QLabel(objectName="languageLabel")
        self.language_combo = QComboBox()
        self.language_combo.addItem("中文", "zh_CN")
        self.language_combo.addItem("English", "en_US")
        header_layout.addWidget(self.language_label)
        header_layout.addWidget(self.language_combo)
        root.addWidget(header)

        self.paths_group = QGroupBox()
        paths_layout = QGridLayout(self.paths_group)
        paths_layout.setContentsMargins(10, 10, 10, 8)
        paths_layout.setHorizontalSpacing(9)
        paths_layout.setVerticalSpacing(6)
        self.input_edit = QLineEdit()
        self.select_file_button = QPushButton()
        self.select_folder_button = QPushButton()
        self.input_path_label = QLabel()
        paths_layout.addWidget(self.input_path_label, 0, 0)
        paths_layout.addWidget(self.input_edit, 0, 1)
        paths_layout.addWidget(self.select_file_button, 0, 2)
        paths_layout.addWidget(self.select_folder_button, 0, 3)
        self.output_edit = QLineEdit()
        self.select_output_button = QPushButton()
        self.output_path_label = QLabel()
        paths_layout.addWidget(self.output_path_label, 1, 0)
        paths_layout.addWidget(self.output_edit, 1, 1, 1, 2)
        paths_layout.addWidget(self.select_output_button, 1, 3)
        paths_layout.setColumnStretch(1, 1)
        root.addWidget(self.paths_group)

        self.conversion_group = QGroupBox()
        settings_layout = QVBoxLayout(self.conversion_group)
        settings_layout.setContentsMargins(10, 10, 10, 8)
        settings_layout.setSpacing(6)
        mode_row = QHBoxLayout()
        self.conversion_mode_label = QLabel()
        mode_row.addWidget(self.conversion_mode_label)
        self.smart_radio = QRadioButton()
        self.overwrite_radio = QRadioButton()
        self.skip_radio = QRadioButton()
        self.smart_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        for radio in (self.smart_radio, self.overwrite_radio, self.skip_radio):
            self.mode_group.addButton(radio)
            mode_row.addWidget(radio)
        mode_row.addStretch()
        settings_layout.addLayout(mode_row)
        checks = QGridLayout()
        checks.setHorizontalSpacing(14)
        checks.setVerticalSpacing(3)
        self.recursive_check = QCheckBox()
        self.preserve_check = QCheckBox()
        self.media_check = QCheckBox()
        self.open_check = QCheckBox()
        self.delete_records_check = QCheckBox()
        for check in (self.recursive_check, self.preserve_check, self.media_check):
            check.setChecked(True)
        self.open_check.setChecked(False)
        self.delete_records_check.setChecked(False)
        checks.addWidget(self.recursive_check, 0, 0)
        checks.addWidget(self.preserve_check, 0, 1)
        checks.addWidget(self.media_check, 0, 2)
        checks.addWidget(self.open_check, 1, 0)
        checks.setColumnStretch(1, 1)
        checks.addWidget(
            self.delete_records_check,
            1,
            2,
            alignment=Qt.AlignmentFlag.AlignRight,
        )
        settings_layout.addLayout(checks)
        root.addWidget(self.conversion_group)

        actions = QHBoxLayout()
        self.scan_button = QPushButton()
        self.save_button = QPushButton()
        self.convert_button = QPushButton(objectName="primary")
        self.sync_button = QPushButton(objectName="sync")
        self.cancel_button = QPushButton(objectName="cancel")
        self.cancel_button.setEnabled(False)
        actions.addWidget(self.scan_button)
        actions.addWidget(self.save_button)
        actions.addStretch()
        actions.addWidget(self.cancel_button)
        actions.addWidget(self.convert_button)
        actions.addWidget(self.sync_button)
        root.addLayout(actions)

        self.status_group = QGroupBox()
        status_layout = QVBoxLayout(self.status_group)
        status_layout.setContentsMargins(10, 10, 10, 8)
        status_layout.setSpacing(5)
        status_top = QHBoxLayout()
        self.status_line_label = QLabel()
        self.status_line_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.pandoc_label = QLabel(objectName="statusPill")
        status_top.addWidget(self.status_line_label)
        status_top.addStretch()
        status_top.addWidget(self.pandoc_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMinimumHeight(90)
        status_layout.addLayout(status_top)
        status_layout.addWidget(self.progress_bar)
        status_layout.addWidget(self.log_edit, 1)
        root.addWidget(self.status_group, 1)

        self.help_bar = QFrame(objectName="helpBar")
        footer = QHBoxLayout(self.help_bar)
        footer.setContentsMargins(8, 4, 8, 4)
        footer.setSpacing(7)
        help_icon = QLabel("?", objectName="helpIcon")
        self.help_label = QLabel(objectName="helpText")
        self.help_label.setWordWrap(True)
        self.help_label.setMaximumHeight(36)
        footer.addWidget(help_icon)
        footer.addWidget(self.help_label, 1)
        self.version_label = QLabel()
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        footer.addWidget(self.version_label)
        root.addWidget(self.help_bar)
        self.setCentralWidget(central)

    def _connect_signals(self) -> None:
        self.select_file_button.clicked.connect(self._select_file)
        self.select_folder_button.clicked.connect(self._select_input_folder)
        self.select_output_button.clicked.connect(self._select_output_folder)
        self.input_edit.textChanged.connect(self._on_input_path_changed)
        self.scan_button.clicked.connect(self._scan_clicked)
        self.save_button.clicked.connect(self._save_settings)
        self.convert_button.clicked.connect(self._convert_clicked)
        self.sync_button.clicked.connect(self._sync_clicked)
        self.cancel_button.clicked.connect(self._cancel_task)
        self.language_combo.currentIndexChanged.connect(self._language_changed)

    def _t(self, key: str, **values: object) -> str:
        return tr(self.language, key, **values)

    def _source_format(self) -> str:
        return (
            "DOCX"
            if self.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
            else "Markdown"
        )

    def _apply_language(self, initial: bool = False) -> None:
        self.setWindowTitle(self._t("app_title"))
        self.title_label.setText(self._t("app_title"))
        self.subtitle_label.setText(self._t("subtitle"))
        self.language_label.setText(self._t("language"))
        with QSignalBlocker(self.language_combo):
            self.language_combo.setItemText(0, self._t("chinese"))
            self.language_combo.setItemText(1, self._t("english"))
            index = self.language_combo.findData(self.language)
            self.language_combo.setCurrentIndex(max(index, 0))

        self.paths_group.setTitle(self._t("files_group"))
        self.input_path_label.setText(self._t("input_path"))
        self.output_path_label.setText(self._t("output_path"))
        self.select_file_button.setText(self._t("choose_file"))
        self.select_folder_button.setText(self._t("choose_folder"))
        self.select_output_button.setText(self._t("choose_folder"))
        self.conversion_group.setTitle(self._t("settings_group"))
        self.conversion_mode_label.setText(self._t("conversion_mode"))
        self.smart_radio.setText(self._t("mode_smart_sync"))
        self.overwrite_radio.setText(self._t("mode_overwrite"))
        self.skip_radio.setText(self._t("mode_skip_existing"))
        self.recursive_check.setText(self._t("recursive"))
        self.preserve_check.setText(self._t("preserve_structure"))
        self.media_check.setText(self._t("extract_media"))
        self.open_check.setText(self._t("open_output"))
        self.delete_records_check.setText(self._t("delete_records"))
        self.scan_button.setText(self._t("scan_files"))
        self.save_button.setText(self._t("save_sync"))
        self.sync_button.setText(self._t("one_click_sync"))
        self.cancel_button.setText(self._t("cancel_task"))
        self.status_group.setTitle(self._t("status_group"))
        self.log_edit.setPlaceholderText(self._t("log_placeholder"))
        self.version_label.setText(self._t("version", version=__version__))
        self._on_direction_changed()
        self._on_input_path_changed()
        self._refresh_context_help()
        if not self._running:
            self.status_line_label.setText(self._t("ready"))
        if not initial:
            self._update_pandoc_status()
            self.log_edit.clear()
            if self.settings_manager.exists():
                self._append_log(self._t("loaded_settings"))

    def _language_changed(self, index: int) -> None:
        language = self.language_combo.itemData(index)
        if not language or language == self.language:
            return
        self.language = str(language)
        try:
            self.settings_manager.save_language(self.language)
        except OSError:
            pass
        self._apply_language()

    def _install_context_help(self) -> None:
        self._help_widgets = {
            self.language_combo: "help_language",
            self.input_edit: "help_input_path",
            self.select_file_button: "help_select_file",
            self.select_folder_button: "help_select_input_folder",
            self.output_edit: "help_output_path",
            self.select_output_button: "help_select_output",
            self.smart_radio: "help_smart",
            self.overwrite_radio: "help_overwrite",
            self.skip_radio: "help_skip",
            self.recursive_check: "help_recursive",
            self.preserve_check: "help_preserve",
            self.media_check: "help_media",
            self.open_check: "help_open_output",
            self.delete_records_check: "help_delete_records",
            self.scan_button: "help_scan",
            self.save_button: "help_save",
            self.convert_button: "help_convert",
            self.sync_button: "help_sync",
            self.cancel_button: "help_cancel",
            self.log_edit: "help_log",
        }
        for widget in self._help_widgets:
            widget.installEventFilter(self)

    def _refresh_context_help(self) -> None:
        for widget, key in getattr(self, "_help_widgets", {}).items():
            widget.setToolTip(self._t(key))
        self.help_label.setText(self._t("help_default"))

    def eventFilter(self, watched: object, event: QEvent) -> bool:
        key = getattr(self, "_help_widgets", {}).get(watched)
        if key:
            if event.type() in {QEvent.Type.Enter, QEvent.Type.FocusIn}:
                self.help_label.setText(self._t(key))
            elif event.type() in {QEvent.Type.Leave, QEvent.Type.FocusOut}:
                self.help_label.setText(self._t("help_default"))
        return super().eventFilter(watched, event)

    def _message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
        default: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok,
    ) -> QMessageBox.StandardButton:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        box.setDefaultButton(default)
        labels = {
            QMessageBox.StandardButton.Ok: "button_ok",
            QMessageBox.StandardButton.Yes: "button_yes",
            QMessageBox.StandardButton.No: "button_no",
            QMessageBox.StandardButton.Cancel: "button_cancel",
        }
        for button, key in labels.items():
            target = box.button(button)
            if target is not None:
                target.setText(self._t(key))
        return QMessageBox.StandardButton(box.exec())

    def _update_pandoc_status(self) -> None:
        pandoc = find_pandoc()
        self.engine.pandoc_path = pandoc
        if pandoc:
            self.pandoc_label.setText(f"✓ {pandoc_version(pandoc)}")
            self.pandoc_label.setToolTip(str(pandoc))
        else:
            self.pandoc_label.setText(self._t("pandoc_missing_short"))
            self.pandoc_label.setStyleSheet("color:#8a4b19;background:#fff2df;")

    def _load_settings_on_startup(self) -> None:
        config = self.settings_manager.load()
        if config:
            self._apply_config(config)
            self._append_log(self._t("loaded_settings"))

    def _apply_config(self, config: AppConfig) -> None:
        self.direction = config.direction
        self.input_edit.setText(config.input_path)
        self.output_edit.setText(config.output_path)
        self.recursive_check.setChecked(config.recursive)
        self.smart_radio.setChecked(config.mode == ConversionMode.SMART.value)
        self.overwrite_radio.setChecked(config.mode == ConversionMode.OVERWRITE.value)
        self.skip_radio.setChecked(config.mode == ConversionMode.SKIP_EXISTING.value)
        self.media_check.setChecked(config.extract_media)
        self.preserve_check.setChecked(config.preserve_structure)
        self.open_check.setChecked(config.open_output)
        self.delete_records_check.setChecked(config.delete_records)
        self._on_direction_changed()
        self._on_input_path_changed()

    def _config(self) -> AppConfig:
        if self.overwrite_radio.isChecked():
            mode = ConversionMode.OVERWRITE.value
        elif self.skip_radio.isChecked():
            mode = ConversionMode.SKIP_EXISTING.value
        else:
            mode = ConversionMode.SMART.value
        input_path = self.input_edit.text().strip().strip('"')
        input_type = "directory" if Path(input_path).is_dir() else "file"
        return AppConfig(
            input_path=self.input_edit.text().strip(),
            input_type=input_type,
            direction=self.direction,
            output_path=self.output_edit.text().strip(),
            recursive=self.recursive_check.isChecked(),
            mode=mode,
            extract_media=self.media_check.isChecked(),
            preserve_structure=self.preserve_check.isChecked(),
            open_output=self.open_check.isChecked(),
            delete_records=self.delete_records_check.isChecked(),
            language=self.language,
        )

    def _select_file(self) -> None:
        if not self._choose_conversion_direction():
            return
        start = self.input_edit.text() or str(Path.home())
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._t(
                "select_docx_title"
                if self.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
                else "select_markdown_title"
            ),
            start,
            self._t(
                "word_filter"
                if self.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
                else "markdown_filter"
            ),
        )
        if filename:
            self.input_edit.setText(filename)
            if not self.output_edit.text():
                self.output_edit.setText(str(Path(filename).parent))

    def _select_input_folder(self) -> None:
        if not self._choose_conversion_direction():
            return
        start = self.input_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(
            self,
            self._t("select_input_folder_title", format=self._source_format()),
            start,
        )
        if folder:
            self.input_edit.setText(folder)

    def _choose_conversion_direction(self) -> bool:
        dialog = ConversionDirectionDialog(self.language, self.direction, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.direction = dialog.selected_direction()
        self._on_direction_changed()
        return True

    def _select_output_folder(self) -> None:
        start = self.output_edit.text() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, self._t("select_output_folder_title"), start)
        if folder:
            self.output_edit.setText(folder)

    def _on_input_path_changed(self) -> None:
        path_text = self.input_edit.text().strip().strip('"')
        folder_mode = bool(path_text) and Path(path_text).is_dir()
        self.recursive_check.setEnabled(folder_mode)
        self.preserve_check.setEnabled(folder_mode)

    def _on_direction_changed(self) -> None:
        forward = self.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
        source = "docx" if forward else "markdown"
        target = "markdown" if forward else "docx"
        self.input_edit.setPlaceholderText(self._t(f"input_{source}_placeholder"))
        self.output_edit.setPlaceholderText(self._t(f"output_{target}_placeholder"))
        self.convert_button.setText(self._t(f"generate_{target}"))
        self.media_check.setEnabled(forward)

    def _append_log(self, message: str, error: bool = False) -> None:
        color = "#b33b3b" if error else "#42526b"
        self.log_edit.append(f'<span style="color:{color}">{html.escape(message)}</span>')

    def _show_error(self, message: str) -> None:
        self._message_box(QMessageBox.Icon.Critical, self._t("cannot_continue"), message)
        self.input_edit.setFocus()
        self.input_edit.selectAll()

    def _scan_current(self) -> ScanResult | None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            scan = self.engine.scan(self._config())
        except ConversionError as exc:
            self._show_error(str(exc))
            return None
        except OSError as exc:
            self._show_error(self._t("read_error", error=exc))
            return None
        finally:
            QApplication.restoreOverrideCursor()

        self.progress_bar.setRange(0, max(scan.total, 1))
        self.progress_bar.setValue(0)
        if scan.total == 0:
            self.status_line_label.setText(
                self._t("no_convertible", format=self._source_format())
            )
        else:
            self.status_line_label.setText(
                self._t(
                    "scan_summary",
                    format=self._source_format(),
                    total=scan.total,
                    convert=scan.convert_count,
                    skip=scan.skip_count,
                )
            )
        return scan

    def _scan_clicked(self) -> None:
        scan = self._scan_current()
        if scan:
            self._append_log(
                self._t(
                    "scan_log",
                    total=scan.total,
                    convert=scan.convert_count,
                    skip=scan.skip_count,
                )
            )

    def _save_settings(self) -> None:
        try:
            self.engine.validate_config(self._config(), create_output=False)
            self.settings_manager.save(self._config())
        except (ConversionError, OSError) as exc:
            self._show_error(str(exc))
            return
        self._append_log(self._t("settings_saved_log"))
        self._message_box(
            QMessageBox.Icon.Information,
            self._t("saved_title"),
            self._t("saved_message"),
        )

    def _convert_clicked(self) -> None:
        self._prepare_and_start(self._config(), sync=False)

    def _sync_clicked(self) -> None:
        config = self.settings_manager.load()
        if config is None:
            self._message_box(
                QMessageBox.Icon.Warning,
                self._t("not_saved_title"),
                self._t("not_saved_message"),
            )
            return
        config.language = self.language
        self._apply_config(config)
        self._prepare_and_start(config, sync=True)

    def _prepare_and_start(self, config: AppConfig, sync: bool) -> None:
        scan = self._scan_current()
        if scan is None:
            return
        if scan.total == 0:
            self._message_box(
                QMessageBox.Icon.Information,
                self._t("no_files_title"),
                self._t("no_files_message", format=self._source_format()),
            )
            return
        if scan.convert_count and find_pandoc() is None:
            self._show_error(self._t("pandoc_missing_gui"))
            return
        mode = self._t(f"mode_{config.mode}")
        heading = self._t(
            "sync_heading"
            if sync
            else (
                "convert_heading_markdown"
                if config.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
                else "convert_heading_docx"
            )
        )
        summary = self._t(
            "confirm_summary",
            heading=heading,
            input=scan.input_path,
            output=scan.output_path,
            mode=mode,
            format=self._source_format(),
            total=scan.total,
            convert=scan.convert_count,
            skip=scan.skip_count,
        )
        answer = self._message_box(
            QMessageBox.Icon.Question,
            self._t("confirm_start"),
            summary,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._start_worker(config, scan)

    def _start_worker(self, config: AppConfig, scan: ScanResult) -> None:
        self.log_edit.clear()
        self._append_log(self._t("task_started", count=scan.convert_count))
        self.progress_bar.setRange(0, max(scan.total, 1))
        self.progress_bar.setValue(0)
        self._set_running(True)

        thread = QThread(self)
        worker = ConversionWorker(self.engine, config, scan)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.finished.connect(self._on_finished)
        worker.crashed.connect(self._on_crashed)
        worker.finished.connect(thread.quit)
        worker.crashed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self.cancel_requested.connect(worker.cancel, Qt.ConnectionType.DirectConnection)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        for widget in (
            self.scan_button,
            self.save_button,
            self.convert_button,
            self.sync_button,
            self.select_file_button,
            self.select_folder_button,
            self.select_output_button,
            self.input_edit,
            self.output_edit,
            self.language_combo,
            self.smart_radio,
            self.overwrite_radio,
            self.skip_radio,
            self.recursive_check,
            self.preserve_check,
            self.media_check,
            self.open_check,
            self.delete_records_check,
        ):
            widget.setEnabled(not running)
        if not running:
            self._on_direction_changed()
            self._on_input_path_changed()
        self.cancel_button.setEnabled(running)

    def _on_progress(self, current: int, total: int, item: object, message: str) -> None:
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.status_line_label.setText(message)
        self._append_log(message, error=message.startswith(self._t("status_failed")))

    def _on_finished(self, summary: ConversionSummary) -> None:
        self._set_running(False)
        self._worker = None
        self._thread = None
        state = self._t("cancelled" if summary.cancelled else "finished")
        self.status_line_label.setText(
            self._t(
                "result_line",
                state=state,
                success=summary.success,
                skipped=summary.skipped,
                failed=summary.failed,
            )
        )
        report_display = (
            self._t("records_deleted") if summary.records_deleted else summary.report_path
        )
        has_errors = summary.failed > 0 or bool(summary.failures)
        self._append_log(
            self._t("report_log", state=state, report=report_display),
            error=has_errors,
        )
        details = self._t(
            "result_details",
            success=summary.success,
            skipped=summary.skipped,
            failed=summary.failed,
            report=report_display,
        )
        if summary.failures:
            first_failures = "\n".join(f"• {path}\n  {reason}" for path, reason in summary.failures[:5])
            details += f"\n\n{self._t('failure_details')}\n{first_failures}"
        if has_errors:
            self._message_box(QMessageBox.Icon.Warning, state, details)
        else:
            self._message_box(QMessageBox.Icon.Information, state, details)
        if self.open_check.isChecked() and self.output_edit.text():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_edit.text()))
        if self._close_after_cancel:
            self._close_after_cancel = False
            QTimer.singleShot(0, self.close)

    def _on_crashed(self, message: str) -> None:
        self._set_running(False)
        self._worker = None
        self._thread = None
        self.status_line_label.setText(self._t("crashed"))
        self._append_log(message, error=True)
        self._message_box(QMessageBox.Icon.Critical, self._t("crashed"), message)
        if self._close_after_cancel:
            self._close_after_cancel = False
            QTimer.singleShot(0, self.close)

    def _cancel_task(self) -> None:
        if not self._running:
            return
        self.cancel_button.setEnabled(False)
        self.status_line_label.setText(self._t("cancel_wait"))
        self.cancel_requested.emit()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            path = Path(urls[0].toLocalFile())
            suffixes = (
                {".docx"}
                if self.direction == ConversionDirection.DOCX_TO_MARKDOWN.value
                else {".md", ".markdown"}
            )
            if path.is_dir() or path.suffix.lower() in suffixes:
                event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        path = Path(event.mimeData().urls()[0].toLocalFile())
        self.input_edit.setText(str(path))
        if path.is_file() and not self.output_edit.text():
            self.output_edit.setText(str(path.parent))
        event.acceptProposedAction()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._running:
            event.accept()
            return
        answer = self._message_box(
            QMessageBox.Icon.Question,
            self._t("task_running"),
            self._t("close_running"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._close_after_cancel = True
            self.cancel_requested.emit()
            event.ignore()
        else:
            event.ignore()
