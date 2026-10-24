import logging
import threading

import pyperclip
from PIL import Image
from PySide6.QtCore import QRect

from core.events import TextCaptured, bus
from core.notifier import Notice, Notifier
from modules.grabber.capture import capture_rect
from modules.grabber.cleanup import clean
from modules.grabber.history import History
from modules.grabber.ocr import recognize

log = logging.getLogger("autoutil.pipeline")


class GrabPipeline:
    def __init__(self, history: History, notifier: Notifier) -> None:
        self.history = history
        self.notifier = notifier

    def run_async(self, rect: QRect, raw: bool = False) -> None:
        """Запускает захват в фоне. raw=True копирует текст без очистки."""
        threading.Thread(target=self._run, args=(rect, raw), daemon=True).start()

    def _run(self, rect: QRect, raw: bool) -> None:
        try:
            image: Image.Image = capture_rect(rect)
            text = recognize(image)
            if not text.strip():
                self.notifier.notify(Notice(
                    title="AutoUtil",
                    body="Текст не распознан.",
                ))
                return

            result = text if raw else clean(text)
            pyperclip.copy(result)
            self.history.add(result)
            bus.publish(TextCaptured(text=result))

            preview = result if len(result) <= 80 else result[:77] + "..."
            self.notifier.notify(Notice(
                title="Текст скопирован",
                body=preview,
            ))
        except Exception:
            log.exception("Ошибка при захвате текста")
            self.notifier.notify(Notice(
                title="AutoUtil",
                body="Не удалось распознать текст. Подробности в журнале логов.",
            ))