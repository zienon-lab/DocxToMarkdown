from __future__ import annotations

import threading

from PySide6.QtCore import QObject, Signal, Slot

from app.converter import ConversionEngine
from app.models import AppConfig, ConversionItem, ScanResult


class ConversionWorker(QObject):
    progress = Signal(int, int, object, str)
    finished = Signal(object)
    crashed = Signal(str)

    def __init__(self, engine: ConversionEngine, config: AppConfig, scan: ScanResult) -> None:
        super().__init__()
        self.engine = engine
        self.config = config
        self.scan = scan
        self._cancel_event = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            summary = self.engine.run(
                self.config,
                self.scan,
                self._cancel_event.is_set,
                self._emit_progress,
            )
            self.finished.emit(summary)
        except Exception as exc:
            self.crashed.emit(str(exc).strip() or exc.__class__.__name__)

    def _emit_progress(
        self, current: int, total: int, item: ConversionItem, message: str
    ) -> None:
        self.progress.emit(current, total, item, message)

    @Slot()
    def cancel(self) -> None:
        self._cancel_event.set()
