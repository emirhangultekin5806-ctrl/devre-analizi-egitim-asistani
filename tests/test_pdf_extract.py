from pathlib import Path

from sadiku_pdf import SADIKU_PDF, skip_no_sadiku

from app.ingestion.pdf_extract import _parse_differences, extract_pages

ROOT = Path(__file__).resolve().parent.parent
FIORE_DC = ROOT / "data" / "raw" / "open" / "Fiore_DC_Electrical_Circuit_Analysis.pdf"


def test_extract_pages_returns_readable_text():
    pages = extract_pages(FIORE_DC, "fiore_dc")

    assert len(pages) == 374

    # İlk 20 sayfa arasında en az birkaçı okunabilir metin içermeli
    # (kapak/boş sayfalar olabileceği için tamamı değil).
    readable = [p for p in pages[:20] if p["char_count"] > 100]
    assert len(readable) > 5

    for page in pages:
        assert page["document_id"] == "fiore_dc"
        assert page["extraction_method"] == "pymupdf"
        assert isinstance(page["needs_review"], bool)


# --- MathematicalPi glif çözümleme (kontrol karakteri -> gerçek sembol) -----
#
# Kök neden: PDF aynı gömülü font PROGRAMINI onlarca kez, her seferinde
# FARKLI bir /Encoding /Differences ile gömüyor (altkümeleme). Ham kod
# (0x01, 0x02...) sayfadan sayfaya değişken; glif ADI ("H11005") sabit.
# `_parse_differences` bunu saf metin üzerinde (PDF açmadan) test eder.


def test_parse_differences_maps_known_glyph_names_to_symbols():
    # Gerçek kitaptan (Sadiku vol.1, s.61): kod 1=eşittir, 2=çarpı, 3=eksi, 4=nokta.
    encoding = "<< /Differences [ 1 /H11005 /H11003 /H11002 /H9024 32 /space ] /Type /Encoding >>"
    assert _parse_differences(encoding) == {1: "=", 2: "×", 3: "−", 4: "·", 32: " "}


def test_parse_differences_handles_multiple_number_runs():
    # PDF söz dizimi: bir sayı kod sayacını sıfırlar; ardından gelen her
    # isim o koddan başlar. Gerçek veride (s.44) H11034 kod 5'te, farklı
    # bir sayfada (s.78) aynı kod 5 H11009'a karşılık geliyordu.
    encoding = "<< /Differences [ 1 /H11002 /H11005 5 /H11034 32 /space ] /Type /Encoding >>"
    assert _parse_differences(encoding) == {1: "−", 2: "=", 5: "°", 32: " "}


def test_parse_differences_ignores_unknown_glyph_names():
    """Tanınmayan bir glif adı (nadir sembol) sessizce atlanır — uydurma
    sembol üretilmez, o kod eşlemede yer almaz."""
    encoding = "<< /Differences [ 1 /H99999 /H11005 32 /space ] /Type /Encoding >>"
    assert _parse_differences(encoding) == {2: "=", 32: " "}


def test_parse_differences_without_the_key_returns_empty():
    assert _parse_differences("<< /Type /Encoding >>") == {}


def test_font_map_for_falls_back_to_a_truncated_prefix_match():
    """PyMuPDF span'larda font adını kısaltabiliyor (bkz. `_font_map_for`
    docstring'i). Tam eşleşme yoksa, glyph_map'in bu KISALTILMIŞ adla
    BAŞLAYAN tam anahtarına düşülür."""
    from app.ingestion.pdf_extract import _font_map_for

    glyph_map = {"MathematicalPi-One-Italic": {"\x01": "ρ"}}
    assert _font_map_for("MathematicalPi-One-Itali", glyph_map) == {"\x01": "ρ"}


def test_font_map_for_prefers_an_exact_match_over_a_prefix_match():
    from app.ingestion.pdf_extract import _font_map_for

    glyph_map = {"MathematicalPi-One": {"\x01": "="}, "MathematicalPi-One-Italic": {"\x01": "ρ"}}
    assert _font_map_for("MathematicalPi-One", glyph_map) == {"\x01": "="}


def test_font_map_for_returns_none_for_an_unknown_font():
    from app.ingestion.pdf_extract import _font_map_for

    assert _font_map_for("Times-Roman", {"MathematicalPi-One": {"\x01": "="}}) is None


def test_parse_differences_resolves_standard_symbol_font_names():
    """"Symbol" fontu "H####" değil, standart Adobe glif adları kullanıyor
    (kendi /Differences'ı var) — `_parse_differences` aynı mekanizmayla,
    ayrı bir kod dalı gerekmeden bunları da çözüyor."""
    encoding = "<< /Differences [ 1 /Omega 32 /space 138 /minus /bar ] /Type /Encoding >>"
    assert _parse_differences(encoding) == {1: "Ω", 32: " ", 138: "−", 139: "|"}


def test_parse_differences_resolves_math_pi_one_bold_comparison_operators():
    # Gerçek kitaptan (Sadiku vol.1, s.352-354): "(α < ω0)" / "(α > ω0)" başlıkları.
    encoding = "<< /Differences [ 1 /H11021 /H11022 ] /Type /Encoding >>"
    assert _parse_differences(encoding) == {1: "<", 2: ">"}


# --- gerçek kitap sayfalarında uçtan uca doğrulama --------------------------


@skip_no_sadiku
def test_operators_are_resolved_not_left_as_control_characters():
    """Sadiku s.61: '1 Ω = ...', '3 × 10^-19' gibi formüllerde "=" ve "×"
    artık okunaklı — önceden \\x01/\\x02 gibi anlamsız kontrol karakterleriydi."""
    import fitz

    from app.ingestion.pdf_extract import _page_text

    with fitz.open(SADIKU_PDF) as doc:
        text = _page_text(doc[61])

    assert "=" in text
    assert "×" in text


@skip_no_sadiku
def test_pages_without_greek_letters_leak_no_control_characters():
    """s.62'de yalnızca MathematicalPi-One/Three operatörleri var (Yunan
    harfi yok) — kontrol karakteri (satır sonu/sekme hariç) hiç sızmamalı."""
    import fitz

    from app.ingestion.pdf_extract import _page_text

    with fitz.open(SADIKU_PDF) as doc:
        text = _page_text(doc[62])

    leaked = [ch for ch in text if ord(ch) < 32 and ch not in "\n\t"]
    assert not leaked, f"sızan kontrol karakterleri: {[hex(ord(c)) for c in leaked]}"


@skip_no_sadiku
def test_greek_letter_italic_font_gap_is_now_closed():
    """Önceden "MathPiOneItalic" adlı AYRI bir font ailesi (ρ, ω, θ gibi eğik
    Yunan harfleri — H9267 vb.) kapsam dışıydı; s.61'deki "resistivity ρ"
    formülünde ρ \\x01 olarak sızıyordu. Artık `_MATH_FONT_PREFIXES`'e
    "MathPi" eklendi ve 15 glif adı (gerçek kitap sayfalarında görsel olarak
    tek tek doğrulandı) `_MATH_GLYPH_NAMES`'e girdi — bu boşluk kapandı."""
    import fitz

    from app.ingestion.pdf_extract import _page_text

    with fitz.open(SADIKU_PDF) as doc:
        text = _page_text(doc[61])

    assert "\x01" not in text
    assert "resistivity ρ" in text


@skip_no_sadiku
def test_grk_font_greek_letters_are_no_longer_misread_as_latin():
    """"Grk" fontu /Differences KULLANMIYOR (standart WinAnsiEncoding), ama
    kodun kendi gömülü glif programı harf kodlarına ("m", "p", "A"...) Yunan
    harfi ÇİZİYOR — get_text() önceden sessizce YANLIŞ ama GEÇERLİ görünen
    bir Latin harf döndürüyordu (kontrol karakteri gibi göze çarpmadığı için
    normal metinle karışıp fark edilmeden kalabilirdi). s.61'de aynı sayfada
    "Grk" fontuyla çizilmiş üç ayrı ρ (resistivity tablosu) var — kod 'r'."""
    import fitz

    from app.ingestion.pdf_extract import _math_glyph_map

    with fitz.open(SADIKU_PDF) as doc:
        glyph_map = _math_glyph_map(doc[61])

    assert glyph_map["Grk"]["r"] == "ρ"


def test_grk_glyph_table_covers_every_character_seen_in_the_book():
    """`_GRK_GLYPH_CHARS`, her iki ciltte de görsel olarak tek tek
    doğrulanan 18 farklı ham koddan (A,F,U,a,b,c,d,f,g,l,m,p,r,s,t,u,y,z)
    türetildi. Bu test o tam listeyi sabitler — biri sessizce silinirse
    (ör. yeniden düzenleme sırasında) yakalanır."""
    from app.ingestion.pdf_extract import _GRK_GLYPH_CHARS

    assert set(_GRK_GLYPH_CHARS) == set("AFUabcdfglmprstuyz")


@skip_no_sadiku
def test_page_474_truncated_font_name_is_still_resolved():
    """PyMuPDF, span sözlüğündeki font adını sessizce kısaltıyor (ölçüldü:
    "DKOMFM+MathematicalPi-One-Italic" `get_fonts()`'ta tam görünürken,
    span'da soyulmuş+kısaltılmış "MathematicalPi-One-Itali" — sondaki "c"
    eksik — olarak geliyor). Tam eşleşme arasaydı bu glif sessizce kontrol
    karakteri olarak sızardı; `_font_map_for`'un önek geri düşüşü bunu
    çözüyor. Bu, tüm kitapta (iki cilt) kontrol karakteri sızıntısının SIFIR
    olduğunu doğrulayan tarama sırasında yakalanan gerçek bir örnek."""
    import fitz

    from app.ingestion.pdf_extract import _page_text

    with fitz.open(SADIKU_PDF) as doc:
        text = _page_text(doc[474])

    leaked = [ch for ch in text if ord(ch) < 32 and ch not in "\n\t"]
    assert not leaked, f"sızan kontrol karakterleri: {[hex(ord(c)) for c in leaked]}"


@skip_no_sadiku
def test_the_same_raw_code_resolves_differently_on_different_pages():
    """Bu, sorunun kök nedeninin doğru anlaşıldığının kanıtı: aynı ham kod
    (0x02) bir sayfada "=" bir başkasında farklı bir sembole karşılık
    gelebiliyordu; artık ikisi de KENDİ sayfasının /Differences'ına göre
    doğru çözülüyor (bkz. modül docstring'i)."""
    import fitz

    from app.ingestion.pdf_extract import _math_glyph_map

    with fitz.open(SADIKU_PDF) as doc:
        map_61 = _math_glyph_map(doc[61])
        map_63 = _math_glyph_map(doc[63])

    # Ham kod 0x01 iki sayfada FARKLI sembole karşılık geliyor (altkümeleme
    # kanıtı): s.61'de "=" (H11005), s.63'te "·" (H9024). Eşleme kod
    # numarasına değil glif adına dayansaydı bu asla olmazdı.
    assert map_61["MathematicalPi-One"]["\x01"] == "="
    assert map_63["MathematicalPi-One"]["\x01"] == "·"


@skip_no_sadiku
def test_two_math_pi_subfonts_on_one_page_do_not_overwrite_each_other():
    """Sadiku s.308: MathematicalPi-One'ın kod 1'i "=" iken aynı sayfadaki
    MathematicalPi-Three'nin kod 1'i "×" — tek düz sözlükte tutulsaydı biri
    diğerini sessizce ezerdi (gerçek veride yakalandı: "v(t)=v(∞)+..."
    formülündeki "=" yanlışlıkla "×" çıkıyordu)."""
    import fitz

    from app.ingestion.pdf_extract import _math_glyph_map, _page_text

    with fitz.open(SADIKU_PDF) as doc:
        glyph_map = _math_glyph_map(doc[308])
        text = _page_text(doc[308])

    assert glyph_map["MathematicalPi-One"]["\x01"] == "="
    assert glyph_map["MathematicalPi-Three"]["\x01"] == "×"
    assert "v(t) = v(" in text
