import logging
import threading

import numpy as np
from PIL import Image

log = logging.getLogger("autoutil.ocr")

_engine = None
_engine_error: Exception | None = None
_lock = threading.Lock()


def _get_engine():
    """Инициализирует RapidOCR один раз: модель грузится долго."""
    global _engine, _engine_error
    with _lock:
        if _engine is None and _engine_error is None:
            try:
                from rapidocr import RapidOCR
                _engine = RapidOCR()
            except Exception as e:
                _engine_error = e
                log.error("OCR недоступен, текстовые правила для картинок не сработают: %s", e)
    return _engine


def recognize(image: Image.Image) -> str:
    engine = _get_engine()
    if engine is None:
        return ""
    try:
        result = engine(np.array(image.convert("RGB")))
        texts = getattr(result, "txts", None) or ()
        return "\n".join(str(t) for t in texts)
    except Exception:
        log.exception("Ошибка OCR")
        return ""