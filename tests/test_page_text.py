"""page_text.py'nin sayfa metninden frekans/desteklenmeyen-eleman cikarimi --
gercek Sadiku sayfalarindan (Figure 10.32/10.33/10.34) olculen kaliplar."""
import math

from app.circuit.page_text import extract_frequency_hz, mentions_unsupported_element


def test_omega_rad_per_s_pattern():
    """Figure 10.33/10.34 sayfasi: 'and ω = 200 rad/s.'"""
    text = "Let R1 = R2 = 10 k, C1 = 2 mF, C2 = 1 mF, and ω = 200 rad/s."
    assert extract_frequency_hz(text) == 200 / (2 * math.pi)


def test_cos_coefficient_pattern():
    """Figure 10.32 sayfasi: 'vs = 4 cos 5000t V.'"""
    text = "Find io and vo in the op amp circuit. Let vs = 4 cos 5000t V."
    assert extract_frequency_hz(text) == 5000 / (2 * math.pi)


def test_explicit_hz_pattern():
    text = "the source operates at f = 60 Hz"
    assert extract_frequency_hz(text) == 60.0


def test_khz_suffix():
    text = "f = 2 kHz"
    assert extract_frequency_hz(text) == 2000.0


def test_no_frequency_returns_none():
    text = "This is a purely resistive practice problem with no time-varying source."
    assert extract_frequency_hz(text) is None


def test_op_amp_keyword_detected():
    assert mentions_unsupported_element("Find io in the op amp circuit of Fig. 10.32.") == "op amp"


def test_no_unsupported_keyword():
    assert mentions_unsupported_element("A simple series RC circuit.") is None
