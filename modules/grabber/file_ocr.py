import logging

import pyperclip
from PIL import Image

from core.notifier import Notice
from modules.grabber.cleanup import clean
from modules.grabber.ocr import recognize
from win.toast import show_toast

log = logging.getLogger("autoutil.file_ocr")


def ocr_file(path: str) -> None:
    try:
        with Image.open(path) as img:
            text = clean(recognize(img.convert("RGB")))
        if not text:
            show_toast(Notice(title="AutoUtil", body="Текст не найден."))
            return
        pyperclip.copy(text)
        show_toast(Notice(title="Текст скопирован", body=text[:80]))
    except Exception:
        log.exception("Ошибка OCR файла %s", path)
        show_toast(Notice(title="AutoUtil", body="Не удалось распознать файл."))
