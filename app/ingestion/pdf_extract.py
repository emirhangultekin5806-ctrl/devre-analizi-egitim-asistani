"""PDF'lerden sayfa bazlı ham metin çıkarımı (spec §13, Adım 1).

Bölüm/alt bölüm tespiti ve temizleme sonraki adımlarda eklenecek;
burada yalnızca ham metin + temel sayfa bilgisi çıkarılır.

**Alt indis birleştirme.** Düz metin çıkarımı (`page.get_text()`) alt
indisleri kaybediyor: `X_C` metinde `"X C"`, `v_c` `"v c"` olarak çıkıyor.
Bu, formüllerin cevaplarda bozuk görünmesine yol açtı ("XC = vc / ic"
yerine "X C = v c / ic"). Sorun tek tek simgelere özgü değil — PDF'te alt
indis YAPISAL bir özellik: `get_text("dict")` çıktısında alt indis span'i
hem daha küçük fontlu hem taban çizgisi daha aşağıda oluyor. Gerçek veride
ölçüldü (Fiore AC, s.30): normal metin 11.0 punto, alt indisler 6.4-6.6
punto ve ~4-6 punto aşağıda.

`_line_text()` bu iki ölçüte bakarak alt indisi önceki simgeye boşluksuz
bitiştirir. Kural simge listesine dayanmadığı için daha önce görülmemiş
değişkenlerde de (V_Th, R_in, i_L …) çalışır.
"""

from pathlib import Path

import fitz  # PyMuPDF

NEEDS_REVIEW_MIN_CHARS = 30

# Alt indis sayılmak için span'in satırın baskın font boyutuna oranı bu
# eşiğin altında olmalı. Gerçek veride alt indis/normal oranı ~0.58-0.60;
# 0.85 eşiği güvenli bir marj bırakıyor (başlık/dipnot boyut farkları
# genelde bundan küçük).
_SUBSCRIPT_SIZE_RATIO = 0.85
# Ayrıca span'in üst kenarı, satırın baskın metnine göre aşağıda olmalı —
# üst indisleri (üs, derece işareti) alt indisle karıştırmamak için.
_SUBSCRIPT_MIN_BASELINE_DROP = 1.0


def _dominant_size(spans: list[dict]) -> float:
    """Satırdaki en çok karakteri taşıyan font boyutu (satırın 'normal'i)."""
    weight: dict[float, int] = {}
    for span in spans:
        text = span.get("text", "")
        if text.strip():
            weight[span["size"]] = weight.get(span["size"], 0) + len(text)
    return max(weight, key=weight.get) if weight else 0.0


def _line_text(line: dict) -> str:
    """Bir satırı, alt indisleri önceki simgeye bitiştirerek metne çevirir."""
    spans = line.get("spans", [])
    base_size = _dominant_size(spans)
    base_top = min(
        (s["bbox"][1] for s in spans if s["size"] == base_size and s.get("text", "").strip()),
        default=0.0,
    )

    parts: list[str] = []
    for span in spans:
        text = span.get("text", "")
        is_subscript = (
            base_size > 0
            and span["size"] < base_size * _SUBSCRIPT_SIZE_RATIO
            and span["bbox"][1] > base_top + _SUBSCRIPT_MIN_BASELINE_DROP
        )
        if is_subscript and text.strip():
            # Alt indis: hem kendi baştaki boşluğunu hem önceki parçanın
            # sondaki boşluğunu at ki "X" + " C" -> "XC" olsun.
            if parts:
                parts[-1] = parts[-1].rstrip()
            parts.append(text.strip())
        else:
            parts.append(text)
    return "".join(parts)


def _page_text(page) -> str:
    """Sayfa metni; alt indisler birleştirilmiş halde."""
    data = page.get_text("dict")
    lines_out: list[str] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # yalnızca metin blokları
            continue
        for line in block.get("lines", []):
            lines_out.append(_line_text(line))
    # NOT: bloklar arasına boş satır EKLENMİYOR. Eklendiğinde (ilk sürümde
    # öyleydi) bu PDF'lerde her satır ayrı blok olduğu için metin baştan sona
    # çift satır sonuna dönüşüyor, paragraf sınırları çoğalıyor ve chunk
    # sayısı %32 artıp ortalama chunk boyutu 408 -> 311 token'a düşüyordu.
    # Amaç yalnızca alt indisleri düzeltmek; metnin yapısı korunmalı.
    return "\n".join(lines_out)


def extract_pages(pdf_path: Path, document_id: str) -> list[dict]:
    """PDF'in her sayfası için bir kayıt döndürür."""
    doc = fitz.open(pdf_path)
    pages = []
    for index, page in enumerate(doc):
        raw_text = _page_text(page)
        char_count = len(raw_text.strip())
        pages.append(
            {
                "document_id": document_id,
                "source_file": str(pdf_path),
                "page_number": index,
                "page_label": page.get_label() or None,
                "raw_text": raw_text,
                "char_count": char_count,
                "extraction_method": "pymupdf",
                "chapter_number": None,
                "chapter_title": None,
                "section_number": None,
                "section_title": None,
                "needs_review": char_count < NEEDS_REVIEW_MIN_CHARS,
            }
        )
    doc.close()
    return pages
