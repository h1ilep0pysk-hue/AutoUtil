import logging
import threading

import numpy as np
from PIL import Image
from rapidocr import RapidOCR

log = logging.getLogger("autoutil.ocr")

_engine: RapidOCR | None = None
_lock = threading.Lock()


def _get_engine() -> RapidOCR:
    global _engine
    with _lock:
        if _engine is None:
            log.info("Загрузка модели OCR")
            _engine = RapidOCR()
        return _engine


def recognize(image: Image.Image) -> str:
    """Возвращает распознанный текст, строки разделены переводом строки."""
    output = _get_engine()(np.array(image))
    if output is None or output.txts is None:
        return ""

    # В новых версиях результат объекта с полями boxes, txts, scores.
    # Сортируем строки сверху вниз, слева направо по верхнему левому углу бокса.
    items = sorted(
        zip(output.boxes, output.txts),
        key=lambda item: (item[0][0][1], item[0][0][0]),
    )
    return "\n".join(text for _, text in items)