from pathlib import Path

import fitz

from app.vision.battery_polarity import detect_battery_polarity

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC = ROOT / "data" / "raw" / "open" / "Fiore_DC_Electrical_Circuit_Analysis.pdf"


def _detect(page_number, clip, orientation, axis_range):
    doc = fitz.open(FIORE_DC)
    page = doc[page_number]
    pix = page.get_pixmap(dpi=600, clip=clip, colorspace=fitz.csGRAY)
    if orientation == "horizontal":
        region = (0, axis_range[0], pix.width, axis_range[1])
    else:
        region = (axis_range[0], 0, axis_range[1], pix.height)
    return detect_battery_polarity(pix, region, orientation)


def test_3v_horizontal_positive_left():
    # Figure 3.8: 3V kaynağın sağ (a terminaline bağlı) ucu negatif.
    result = _detect(77, fitz.Rect(470, 125, 560, 165), "horizontal", (100, 280))
    assert result is not None
    assert result["positive_end"] == "left"


def test_6v_horizontal_positive_left():
    # Figure 3.26: gorseldeki "+"/"-" etiketleriyle dogrulandi (sol +, sag -).
    result = _detect(90, fitz.Rect(495, 135, 545, 165), "horizontal", (40, 180))
    assert result is not None
    assert result["positive_end"] == "left"


def test_24v_vertical_positive_bottom():
    # Figure 3.26: gorseldeki "+"/"-" etiketleriyle dogrulandi (ust -, alt +).
    result = _detect(90, fitz.Rect(425, 140, 460, 200), "vertical", (0, 230))
    assert result is not None
    assert result["positive_end"] == "bottom"


def test_4v_vertical_positive_bottom():
    # Figure 3.26: gorseldeki "+"/"-" etiketleriyle dogrulandi (ust -, alt +).
    result = _detect(90, fitz.Rect(515, 140, 555, 200), "vertical", (20, 220))
    assert result is not None
    assert result["positive_end"] == "bottom"


def test_returns_none_when_fewer_than_two_lines_found():
    # Bos/pil icermeyen bir bolgede guvenilir bir sonuc donmemeli.
    doc = fitz.open(FIORE_DC)
    page = doc[77]
    pix = page.get_pixmap(dpi=600, clip=fitz.Rect(0, 0, 20, 20), colorspace=fitz.csGRAY)
    result = detect_battery_polarity(pix, (0, 0, pix.width, pix.height), "horizontal")
    assert result is None
