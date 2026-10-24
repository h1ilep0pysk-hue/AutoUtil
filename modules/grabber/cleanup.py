import re


def clean(text: str) -> str:
    """Склеивает переносы внутри абзацев, убирает лишние пробелы."""
    text = text.replace("\r\n", "\n")
    # Перенос слова с дефисом: "сло-\nво" -> "слово"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Одиночный перенос строки внутри предложения -> пробел.
    text = re.sub(r"(?<![.!?:])\n(?!\n)", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()