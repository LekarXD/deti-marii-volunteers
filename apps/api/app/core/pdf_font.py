from pathlib import Path

def font_path():
    """Packaged Cyrillic font, with original license retained alongside it."""
    path=Path(__file__).resolve().parents[1]/"assets/fonts/DejaVuSans.ttf"
    if not path.is_file():
        raise RuntimeError("Packaged document font is unavailable")
    return path
