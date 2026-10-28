"""Язык интерфейса не протекает из теста в тест.

``core.i18n.set_language()`` пишет в модульную переменную, то есть это
глобальное состояние процесса. Пока его никто не восстанавливал, тест
tests/test_naming.py оставлял «ru» и все следующие тесты шли по-русски:
tests/test_preview.py проходил только потому, что стоит в алфавите позже.

Фикстура restore_language из conftest.py возвращает язык после каждого
теста. Эти два теста проверяют её на практике: первый намеренно пачкает
состояние, второй требует исходное значение. Если фикстуру убрать,
второй упадёт — то есть регресс не пройдёт молча.
"""
from core.i18n import current_language, set_language


def test_switching_language_is_visible_inside_the_test():
    set_language("ru")
    assert current_language() == "ru"


def test_next_test_starts_with_the_default_language():
    # Значение по умолчанию из core/i18n.py: _LANG = "en".
    assert current_language() == "en"
