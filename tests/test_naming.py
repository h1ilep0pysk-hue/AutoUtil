from core.i18n import set_language
from modules.organizer.analyzer import Features
from modules.organizer.naming import render_name


def feats(tmp_path, name="check.pdf", text=""):
    p = tmp_path / name
    p.write_bytes(b"x")
    return Features(path=p, ext=".pdf", size=1, text=text)


def test_render_template(tmp_path):
    f = feats(tmp_path)
    out = render_name("{year}_{name}.{ext}", f)
    assert out.endswith(".pdf")
    assert f.path.stem in out


def test_unknown_vendor_localized(tmp_path):
    f = feats(tmp_path, text="")
    try:
        set_language("en")
        assert "unknown" in render_name("{date}_{vendor}.pdf", f)
        set_language("ru")
        assert "неизвестно" in render_name("{date}_{vendor}.pdf", f)
    finally:
        set_language("ru")


def test_bad_chars_sanitized_and_ext_kept(tmp_path):
    f = feats(tmp_path, name="weird:name.pdf")
    out = render_name("{name}", f)
    assert ":" not in out and out.lower().endswith(".pdf")
