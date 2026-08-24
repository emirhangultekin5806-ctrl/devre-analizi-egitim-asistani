"""Kitap sayfasının DÜZ metninden (şemanın DIŞINDA) deterministik ipuçları.

Neden gerekli: Sadiku'da AC problemlerinin frekansı NEREDEYSE HİÇ şemanın
üzerinde yazmıyor -- paragrafta geçiyor ("vs = 4 cos 5000t V", "ve ω =
200 rad/s") (OLCULDU -- Figure 10.32/10.33/10.34 sayfaları elle okundu,
üçünde de frekans sadece metinde). VLM'in bileşen kırpımından okuduğu
frekans hep null dönüyordu bu yüzden -- kod hatası değil, mimari eksik:
per-bileşen kırpım hiçbir zaman paragrafı GÖRMÜYOR.

Bilerek DAR kapsamlı: yalnızca TEK bir sayı (frekans) çıkarıyor, paragraftaki
"R1 = 10 kΩ" gibi İSİMLİ değişken atamalarını diyagramdaki elemanlarla
eşleştirmeye ÇALIŞMIYOR -- bu, projenin bilerek kaçındığı "hangi metin
hangi elemana ait" eşleştirme problemiyle aynı sınıf (bkz. vlm_read.py
read_component_value docstring'i), tek bir global frekans sayısından çok
daha riskli. Bu yüzden YALNIZCA frekans ve "desteklenmiyor" anahtar
kelimeleri için kullanılıyor, deger OKUMA için DEĞİL.
"""
from __future__ import annotations

import math
import re

_OMEGA_RE = re.compile(r"ω\s*=\s*(\d+(?:\.\d+)?)\s*(k)?\s*rad\s*/\s*s", re.IGNORECASE)
_FREQ_RE = re.compile(r"\bf\s*=\s*(\d+(?:\.\d+)?)\s*(k)?\s*Hz\b", re.IGNORECASE)
# "vs = 4 cos 5000t V" gibi -- cos/sin icindeki t katsayisi doğrudan ω (rad/s).
_COS_RE = re.compile(r"(?:cos|sin)\s*\(?\s*(\d+(?:\.\d+)?)\s*t\b", re.IGNORECASE)

# Bu kelimeler sayfa metninde geçiyorsa devre türü desteklenmiyor demektir --
# ama YOLO bu elemanı (op-amp gibi) tespit edemeyip sessizce atlayabiliyor
# (OLCULDU -- Figure 10.32: op-amp hiç tespit edilmedi, pipeline devreyi
# sanki salt pasif RC ağıymış gibi çözüp FİZİKSEL OLARAK ANLAMSIZ ama
# power_balance≈0 -- yani "tutarlı görünen" bir cevap üretti). Diyagram
# tespiti güvenilmezken metindeki anahtar kelime son bir güvenlik ağı.
_UNSUPPORTED_KEYWORDS = ("op amp", "op-amp", "operational amplifier")


def extract_frequency_hz(text: str) -> float | None:
    """Sayfa metninden TEK bir frekans (Hz) çıkarır, bulamazsa None.

    Sırayla dener: "ω = ... rad/s", "f = ... Hz", "cos/sin(...t)". İlk
    eşleşen kazanır -- sayfada birden fazla pratik problem olabilir, bu
    yüzden KESİN değil, bir SEZGİ (yalnızca şemanın kendisi hiçbir frekans
    vermediğinde YEDEK olarak kullanılmalı, bkz. modül docstring'i).
    """
    m = _OMEGA_RE.search(text)
    if m:
        value = float(m.group(1)) * (1000 if m.group(2) else 1)
        return value / (2 * math.pi)
    m = _FREQ_RE.search(text)
    if m:
        return float(m.group(1)) * (1000 if m.group(2) else 1)
    m = _COS_RE.search(text)
    if m:
        return float(m.group(1)) / (2 * math.pi)
    return None


def mentions_unsupported_element(text: str) -> str | None:
    """Metinde desteklenmeyen bir eleman turu geciyorsa onun adini dondurur."""
    lowered = text.lower()
    for keyword in _UNSUPPORTED_KEYWORDS:
        if keyword in lowered:
            return keyword
    return None
