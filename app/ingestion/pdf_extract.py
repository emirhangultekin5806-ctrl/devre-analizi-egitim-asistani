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

**Matematik operatör sembolleri ("=", "×", "±"...).** Sadiku PDF'i bunları
düz metin karakteri olarak DEĞİL, "MathematicalPi-One/Three/Four" adlı özel
dingbat fontlarla çiziyor. `page.get_text()` bu fontların karakter kodlarını
(0x01-0x08 gibi) ANLAMSIZ kontrol karakterlerine çözüyordu — önceden "aynı
kod farklı yerlerde farklı sembol oluyor, güvenilir çözülemez" diye
işaretlenmişti. Kök neden bulundu: PDF, AYNI gömülü font PROGRAMINI onlarca
kez, HER SEFERİNDE FARKLI bir `/Encoding /Differences` dizisiyle gömüyor
(altkümeleme optimizasyonu — her sayfa kesiti yalnızca ihtiyacı olan
sembolleri 1'den başlayan kodlara paketliyor). Yani HAM KOD sayfadan sayfaya
değişken, ama fontun kendi GLİF ADI ("H11005" gibi) her zaman aynı sembole
karşılık geliyor — 40'tan fazla gerçek örnekte görsel olarak doğrulandı
(bkz. `_MATH_GLYPH_NAMES`). `_math_glyph_map()` her sayfa için kendi
`/Differences` dizisini okuyup kod→sembol eşlemesini kurar; eşleşmeyen
(nadir/tanınmayan) glifler kontrol karakteri olarak sızdırılmak yerine
sessizce atılır.

**Yunan harfleri ve "Grk" fontu.** Yukarıdaki düzeltme başta yalnızca
"MathematicalPi-*" ailesini kapsıyordu; eğik Yunan harfleri (ρ, ω, θ...)
AYRI bir font ailesinde ("MathPiOneItalic", "MathPiFourItalic",
"MathematicalPi-One-Italic") geliyordu ve bilerek kapsam dışı bırakılmıştı.
Artık `_MATH_FONT_PREFIXES`'e "MathPi" eklendi, 15 glif adı (ölçüm+görsel
doğrulama, iki ciltte de) `_MATH_GLYPH_NAMES`'e girdi — bu boşluk kapandı.

Ayrıca "Grk" adlı, kitabın kendi tasarladığı bir font DAHA vardı: bu
/Differences KULLANMIYOR (standart WinAnsiEncoding bildiriyor), ama gömülü
glif PROGRAMI harf kodlarına ("m", "p", "A"...) Yunan harfi ÇİZİYOR — yani
`get_text()` sessizce YANLIŞ ama GEÇERLİ görünen bir Latin harf
döndürüyordu (kontrol karakteri gibi göze çarpmadığı için fark edilmeden
kalabilirdi). Her iki ciltte de TEK bir gömülü font dosyası kullanıldığı
için (ölçüldü: tek `FontDescriptor` referansı) eşleme cilt boyunca sabit;
18 farklı kod gerçek kitap sayfalarında tek tek görsel doğrulandı (bkz.
`_GRK_GLYPH_CHARS`).

**"Symbol" fontu** standart Adobe glif adları (`/Omega`, `/minus`...)
kullanıyor — `_MATH_GLYPH_NAMES`'e eklenip aynı `/Differences` mekanizmasına
dahil edildi, görsel doğrulama gerekmedi (adlar zaten kendini açıklıyor).

**PyMuPDF'in font adı kısaltması.** `page.get_fonts()`'ta tam görünen bir
font adı ("MathematicalPi-One-Italic"), `get_text("dict")`'in span'larında
SESSİZCE kısaltılmış gelebiliyor (ölçüldü: sondaki "c" eksik). Tam eşleşme
arasaydı bu glif de sessizce kaçardı; `_font_map_for()` tam eşleşme
bulamazsa glyph_map'in bu (muhtemelen kısaltılmış) adla BAŞLAYAN bir
anahtarına düşer.

**Doğrulama:** iki ciltin TAMAMI (1056 sayfa) tarandı — kontrol karakteri
sızıntısı (satır sonu/sekme hariç) artık SIFIR.
"""

import re
from pathlib import Path

import fitz  # PyMuPDF

# Glif adı -> doğru Unicode sembol. Sayfa/fontun kendi rastgele kod
# numarasından BAĞIMSIZ, sabit bir eşleme (bkz. modül docstring'i).
# Her biri gerçek kitap sayfasında görsel olarak doğrulandı.
_MATH_GLYPH_NAMES = {
    "H11001": "+",
    "H11002": "−",  # − (gerçek eksi, ASCII tire değil)
    "H11003": "×",  # ×
    "H20862": "×",  # × (MathematicalPi-Three'nin kendi × glifi)
    "H11005": "=",
    "H11006": "±",  # ±
    "H11009": "→",  # →
    "H11021": "<",  # < (MathPiOneBold, kalın başlıklarda -- "(α < ω0)")
    "H11022": ">",  # > (MathPiOneBold, "(α > ω0)")
    "H11034": "°",  # °
    "H11229": "≃",  # ≃ (yaklaşık eşit)
    "H11349": "≤",  # ≤
    "H11350": "≥",  # ≥
    "H20648": "∥",  # ∥ (paralel)
    "H20910": "≜",  # ≜ (tanım gereği eşit)
    "H9024": "·",  # · (nokta çarpım, "Ω·m" gibi)
    "HS11005": "≠",  # ≠
    # "MathPiOneItalic"/"MathPiFourItalic"/"MathematicalPi-One-Italic" ailesi
    # -- eğik Yunan harfleri (ρ, ω, θ gibi). Önceden "MathematicalPi" ön eki
    # bunları kapsamıyordu (bkz. modül docstring'i, "Bilinen boşluk" notu --
    # artık kapsanıyor). 15 glif, gerçek kitap sayfalarında (Sadiku 1-2)
    # görsel olarak tek tek doğrulandı.
    "H9251": "α",
    "H9252": "β",
    "H9254": "δ",
    "H9256": "ζ",
    "H9258": "θ",
    "H9261": "λ",
    "H9262": "μ",
    "H9265": "o",  # italik alt indis "o" (i_o, v_o) -- omicron'la aynı şekil
    "H9266": "π",
    "H9267": "ρ",
    "H9268": "σ",
    "H9270": "τ",
    "H9275": "ω",
    "H9278": "φ",
    "H9280": "ε",
    # "Symbol" fontu -- standart Adobe glif adları kullanıyor (kendi
    # /Differences'ı var, "H####" gibi rastgele değil), bu yüzden görsel
    # doğrulama gerekmeden doğrudan eşlenebilir. Yalnızca gerçekten
    # kullanılanlar (bar hariç hepsi kitapta en az bir yerde geçiyor;
    # bracketleftex/bracketrightex/braceex büyük parantez/köşeli parantezin
    # PARÇALARI -- tek başına anlamlı bir karakter değil, atılır).
    "Alpha": "Α",
    "Delta": "Δ",
    "Eta": "Η",
    "Omega": "Ω",
    "approxequal": "≈",
    "asteriskmath": "*",
    "bar": "|",  # ölçüldü: "|Vo|" (genlik/mutlak değer çubuğu)
    "colon": ":",
    "degree": "°",
    "delta": "δ",
    "eight": "8",
    "equal": "=",
    "five": "5",
    "four": "4",
    "fraction": "⁄",
    "infinity": "∞",
    "integral": "∫",
    "minus": "−",
    "minute": "′",
    "multiply": "×",
    "nine": "9",
    "one": "1",
    "parenright": ")",
    "period": ".",
    "pi": "π",
    "plus": "+",
    "plusminus": "±",
    "radical": "√",
    "seven": "7",
    "six": "6",
    "space": " ",
    "three": "3",
    "two": "2",
    "zero": "0",
}
_MATH_FONT_PREFIXES = ("MathematicalPi", "MathPi", "Symbol")

# "Grk" fontu (Sadiku'nun kendi tasarladığı özel bir font) FARKLI bir sorun:
# /Differences YOK, standart WinAnsiEncoding kullanıyor -- yani kod noktası
# zaten sıradan bir Latin harfi ("m", "p", "A"...). Ama fontun kendi GÖMÜLÜ
# glif PROGRAMI o koda Yunan harfi ÇİZİYOR (ör. kod 'p' harfi görsel olarak
# "π" çiziyor). `get_text()` bu yüzden "m"/"p" gibi sessizce YANLIŞ ama
# GEÇERLİ görünen bir harf döndürüyor -- kontrol karakteri gibi göze
# çarpmadığı için normal metinle karışıp fark edilmeden kalabilirdi. Her iki
# ciltte de TEK bir FontDescriptor (gömülü font DOSYASI) kullanılıyor, yani
# bu eşleme cilt boyunca sabit -- ölçüldü, 18 farklı kod, gerçek kitap
# sayfalarında görsel olarak tek tek doğrulandı.
_GRK_FONT_NAME = "Grk"
_GRK_GLYPH_CHARS: dict[str, str] = {
    "A": "α",  # kalın başlık varyantı ("Critically Damped Case (α = ω0)")
    "a": "α",
    "F": "φ",
    "f": "φ",
    "U": "θ",  # kalın/büyük varyant
    "u": "θ",
    "b": "β",
    "c": "ψ",
    "d": "δ",
    "g": "γ",
    "l": "λ",
    "m": "μ",
    "p": "π",
    "r": "ρ",
    "s": "σ",
    "t": "τ",
    "y": "υ",
    "z": "ζ",
}


def _parse_differences(encoding_obj: str) -> dict[int, str]:
    """`/Differences [1 /Name1 /Name2 5 /Name3 ...]` dizisini kod->sembol'e çevirir.

    PDF söz dizimi: bir SAYI o andan itibaren kod sayacını sıfırlar, ardından
    gelen her /İsim o kodu alır ve sayaç 1 artar.
    """
    match = re.search(r"/Differences\s*\[(.*?)\]", encoding_obj, re.DOTALL)
    if not match:
        return {}
    result: dict[int, str] = {}
    code = 0
    for token in match.group(1).split():
        if token.startswith("/"):
            symbol = _MATH_GLYPH_NAMES.get(token[1:])
            if symbol is not None:
                result[code] = symbol
            code += 1
        else:
            code = int(token)
    return result


def _math_glyph_map(page) -> dict[str, dict[str, str]]:
    """Bu sayfadaki her "MathematicalPi-*" alt fontu İÇİN AYRI kod->sembol eşlemesi.

    Anahtar fontun kısa adı ("MathematicalPi-One" — `span["font"]` ile aynı
    biçim). AYRI tutulması zorunlu: aynı sayfada birden fazla alt font
    (One, Three, Four) aynı ham kodu (ör. 0x01) FARKLI sembollere
    atayabiliyor. Tek düz sözlükte birleştirilirse biri diğerini sessizce
    eziyordu — gerçek veride yakalandı (Sadiku s.308: MathematicalPi-One'ın
    kod 1'i "=" iken MathematicalPi-Three'nin kod 1'i "×"; ikisi tek
    sözlükte tutulunca hangi fontun son işlendiği rastgele kazanıyordu).

    Çoğu sayfada bu fontlar hiç yok — o durumda boş sözlük döner, ekstra
    maliyet neredeyse sıfır.
    """
    mapping: dict[str, dict[str, str]] = {}
    doc = page.parent
    for xref, _ext, _type, basename, *_ in page.get_fonts(full=True):
        # "HNNHDF+MathematicalPi-One" -> "MathematicalPi-One" (span["font"]
        # alt küme önekini taşımıyor, eşleşmesi için soyulmalı).
        short_name = basename.rsplit("+", 1)[-1]
        if short_name == _GRK_FONT_NAME:
            # /Differences yok (standart WinAnsiEncoding) -- sabit tabloyla
            # doğrudan eşlenir, aşağıdaki /Differences okuma adımı atlanır.
            mapping.setdefault(short_name, {}).update(_GRK_GLYPH_CHARS)
            continue
        if not any(prefix in basename for prefix in _MATH_FONT_PREFIXES):
            continue
        font_match = re.search(r"/Encoding (\d+) 0 R", doc.xref_object(xref))
        if not font_match:
            continue
        encoding_obj = doc.xref_object(int(font_match.group(1)))
        font_map = mapping.setdefault(short_name, {})
        for code, symbol in _parse_differences(encoding_obj).items():
            font_map[chr(code)] = symbol
    return mapping

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


def _font_map_for(span_font: str, glyph_map: dict[str, dict[str, str]]) -> dict[str, str] | None:
    """`span["font"]` adına karşılık gelen glif eşlemesini bulur.

    PyMuPDF, span sözlüğündeki font adını (gömülü altküme öneki soyulduktan
    sonra) belirli bir uzunlukta SESSİZCE kısaltıyor — ölçüldü: gerçek
    kitapta "DKOMFM+MathematicalPi-One-Italic" (`page.get_fonts()`'ta tam
    adıyla görünüyor) span'larda "MathematicalPi-One-Itali" (sondaki "c"
    eksik) olarak geliyordu, bu yüzden tam eşleşme sessizce başarısız olup
    o glif kontrol karakteri olarak sızıyordu. `_math_glyph_map` her zaman
    TAM adla anahtarlanır (`page.get_fonts()`'tan); burada tam eşleşme
    bulunamazsa, glyph_map'in hangi anahtarının bu (muhtemelen kısaltılmış)
    adla BAŞLADIĞINA bakılır — kısaltma yalnızca KISALTIR, asla farklı bir
    önek üretmez, bu yüzden güvenli bir geri düşüş.
    """
    font_map = glyph_map.get(span_font)
    if font_map is not None or not span_font:
        return font_map
    for name, mapping in glyph_map.items():
        if name.startswith(span_font):
            return mapping
    return None


def _line_text(line: dict, glyph_map: dict[str, dict[str, str]] | None = None) -> str:
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
        font_map = _font_map_for(span.get("font", ""), glyph_map) if glyph_map else None
        if font_map is not None:
            # Eşleşmeyen kontrol karakterleri (nadir/tanınmayan glifler)
            # anlamsız kod olarak sızdırılmak yerine atılır. Eşleme SADECE
            # bu span'ın KENDİ fontuna aitir — aynı sayfadaki başka bir
            # MathematicalPi alt fontunun kodlarıyla KARIŞTIRILMAZ (bkz.
            # `_math_glyph_map` docstring'i).
            text = "".join(ch if ord(ch) >= 32 else font_map.get(ch, "") for ch in text)
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
    """Sayfa metni; alt indisler birleştirilmiş, matematik sembolleri düzeltilmiş halde."""
    data = page.get_text("dict")
    glyph_map = _math_glyph_map(page)
    lines_out: list[str] = []
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # yalnızca metin blokları
            continue
        for line in block.get("lines", []):
            lines_out.append(_line_text(line, glyph_map))
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
