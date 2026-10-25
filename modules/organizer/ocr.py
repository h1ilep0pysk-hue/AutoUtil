from PIL import Image

def recognize(image: Image.Image) -> str:
    """Simple OCR placeholder.
    Attempts to use pytesseract if available; otherwise returns empty string.
    """
    try:
        import pytesseract
        return pytesseract.image_to_string(image)
    except Exception:
        return ""
