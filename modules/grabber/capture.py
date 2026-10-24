import mss
from PIL import Image
from PySide6.QtCore import QRect


def capture_rect(rect: QRect) -> Image.Image:
    """Снимок прямоугольника экрана. Координаты уже учитывают DPI процесса."""
    region = {
        "left": rect.x(),
        "top": rect.y(),
        "width": rect.width(),
        "height": rect.height(),
    }
    with mss.mss() as sct:
        shot = sct.grab(region)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")