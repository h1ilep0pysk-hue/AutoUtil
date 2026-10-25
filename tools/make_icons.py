from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 64  # рисуем в 2x, Windows уменьшит до 16–32 px с хорошим сглаживанием
ASSETS = Path(__file__).resolve().parent.parent / "ui" / "assets"

ACCENT = (0, 102, 204, 255)      # насыщенный синий
ACCENT_DARK = (0, 70, 150, 255)  # для тени и обводки
PAUSE = (110, 110, 118, 255)     # графитовый серый
ALERT = (255, 92, 0, 255)        # ярко-оранжевый
WHITE = (255, 255, 255, 255)


def _base(color: tuple[int, int, int, int]) -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Скруглённый квадрат вместо круга, чтобы значок было легче узнать.
    draw.rounded_rectangle((4, 4, SIZE - 5, SIZE - 5), radius=14, fill=color,
                           outline=ACCENT_DARK, width=2)
    # Белая буква "A" из линий: символ утилиты.
    w = 6
    draw.line((18, 46, 32, 16), fill=WHITE, width=w)
    draw.line((32, 16, 46, 46), fill=WHITE, width=w)
    draw.line((24, 36, 40, 36), fill=WHITE, width=w)
    return img


def make_idle() -> Image.Image:
    return _base(ACCENT)


def make_paused() -> Image.Image:
    img = _base(PAUSE)
    draw = ImageDraw.Draw(img)
    # Две белые полоски поверх: знак паузы.
    draw.rectangle((26, 26, 29, 46), fill=WHITE)
    draw.rectangle((35, 26, 38, 46), fill=WHITE)
    return img


def make_alert() -> Image.Image:
    img = _base(ACCENT)
    draw = ImageDraw.Draw(img)
    r = 12
    cx, cy = SIZE - r - 2, r + 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ALERT, outline=WHITE, width=3)
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    make_idle().save(ASSETS / "tray_idle.png")
    make_alert().save(ASSETS / "tray_alert.png")
    make_paused().save(ASSETS / "tray_paused.png")
    print(f"Иконки сохранены в {ASSETS}")


if __name__ == "__main__":
    main()
