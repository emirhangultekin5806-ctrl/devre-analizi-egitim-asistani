"""PDF sayfasındaki devre şeklinin VEKTÖR verisini geometrik ilkellere çevirir.

Ölçüm sonucu (Sadiku vol.1, Practice Problem 2.9 sayfası): sayfada 0 raster
görüntü, 398 doğru parçası, 23 dikdörtgen, 66 eğri. Yani şekiller taranmış
resim değil, tam koordinatlı çizim komutları. Bu modül o komutları okur;
topoloji çıkarımını `schematic.py` yapar.

Sembol sözlüğü (ölçümle çıkarıldı, tahmin değil):

| çizim yolu                                  | anlamı                |
|---------------------------------------------|-----------------------|
| çok sayıda kısa çizgi, küçük sınır kutusu   | direnç (zikzak)       |
| uzun düz çizgi(ler)                          | tel                   |
| 4 eğri, çap ~3.7, BEYAZ dolgu                | dış uç (açık daire)   |
| 4 eğri, çap ~3.3, renkli dolgu               | birleşim noktası      |
| 4 eğri, çap ~13.4                            | kaynak (daire gövde)  |

Kaynak sembollerinin polaritesi ve türü (V/I) bu sürümde çözülmüyor —
`battery_polarity.py` bunu piksel tarayarak yapıyor, ikisi ileride
birleştirilecek. Şimdilik yalnızca direnç ağları (Bölüm 2'nin büyük kısmı)
netlist'e çevrilir; tanınmayan bir sembol görülürse SchematicError atılır,
sessizce atlanmaz.
"""

import math
import re
from dataclasses import dataclass
from itertools import pairwise

from app.vision.schematic import Figure, Label, SchematicError, Symbol, Terminal, Wire

# --- eşikler (hepsi ölçülen değerlerden, pt cinsinden) ---------------------

# Direnç zikzağı: ~16.7 x 4.9 pt, 11-15 kısa çizgi parçası.
ZIGZAG_MIN_SEGMENTS = 8
SYMBOL_MAX_SIZE = 30.0
# Dış uç / birleşim noktası daireleri: çap 3.3-3.7 pt.
NODE_MARK_MAX_SIZE = 6.0
# Kaynak gövdesi: çap ~13.4 pt.
SOURCE_MIN_SIZE, SOURCE_MAX_SIZE = 10.0, 18.0
# Bağımlı kaynak baklavası: ölçülen 17.8 x 17.8 pt.
DIAMOND_MIN_SIZE, DIAMOND_MAX_SIZE = 14.0, 24.0
# Ok ucu üçgeni: ölçülen 3.3 x 6.1 pt.
ARROWHEAD_MAX_SIZE = 9.0
# Toprak sembolü: ölçülen 11.0-11.5 pt genişlik, 2.4-3.6 pt yükseklik.
GROUND_MAX_SIZE = 20.0
# Kalın tel şeridinin iki yakası arası: ölçülen 8.37 pt.
RIBBON_MAX_WIDTH = 11.0
# Akım referans oku ("Io") elemana PROBE_MARGIN'den daha uzakta durabiliyor
# — ölçülen: ok-eleman 12.8 pt, ok-etiket 8.1 pt (Example 3.6, Figure 3.20).
CURRENT_ARROW_MARGIN = 18.0
CURRENT_LABEL_MARGIN = 12.0
# Kaynak dairesi içindeki +/- işaretleri ve ok, daire sınırının bu kadar
# dışına taşabiliyor (glif kutuları daireden biraz büyük).
SOURCE_INNER_PAD = 3.0

# Bir kümenin "devre çizimi" sayılması için içinde gerçek bir eleman gövdesi
# olmalı. Tek başına duran açıklama okları (R_eq göstergesi, akım yönü oku)
# yoksa çizim sanılıp başlıkla eşleşmeye aday oluyordu.
ELEMENT_PRIMITIVES = {"resistor", "source", "dependent_source"}

# Kapasitör plakaları: ölçülen ~11 pt uzunluk, ~2.4 pt boşluk (Figure 7.43).
CAPACITOR_MAX_GAP = 6.0
CAPACITOR_MIN_PLATE = 6.0

# Anahtar körü: ölçülen boyut ~11.6x11.6 pt (Figure 7.43). Daha büyük eğik
# çizgiler (varsa) köprü teli olabilir, bu eşik onları dışarıda bırakır.
SWITCH_BLADE_MAX_SIZE = 20.0
SWITCH_BLADE_MIN_SKEW = 2.0
# Sayfa süsleri (kesim işaretleri, kenarlık) şekilden çok daha büyük.
PAGE_DECORATION_MIN_SIZE = 250.0
# Aynı şekle ait ilkeller arası en büyük boşluk. Kitapta ayrı şekiller
# arasındaki en küçük dikey boşluk ~38 pt; bir şekil içindeki parçalar ise
# teller üzerinden değiyor.
CLUSTER_GAP = 8.0
# Etiketler şeklin sınır kutusunun hemen dışında da olabilir.
LABEL_MARGIN = 14.0
# Uca yazılan harf (a, b) ucun hemen yanındadır; ölçülen uzaklık 7-11 pt.
TERMINAL_LABEL_RANGE = 12.0

# Başlık, kendi başına duran "Figure N.M" parçasıdır. Sondaki `$` şart:
# gövde metnindeki "Figure 3.37 depicts various kinds of..." gibi ATIFLAR da
# aksi halde başlık sayılıyor ve sayfadaki alakasız bir çizime bağlanıyordu.
_CAPTION_RE = re.compile(r"^Figure\s+\d+\.\d+$")

_PREFIXES = {"": 1.0, "k": 1e3, "K": 1e3, "M": 1e6, "m": 1e-3, "µ": 1e-6, "μ": 1e-6, "n": 1e-9, "p": 1e-12}
# Ohm işareti iki ayrı kod noktası olabilir: U+03A9 (Yunan omega, Symbol
# fontundan bu gelir) ve U+2126 (ohm işareti). İkisi de kabul edilir.
_UNIT_SYMBOLS = {
    "Ω": "ohm",
    "Ω": "ohm",
    "V": "volt",
    "A": "amper",
    "F": "farad",
    "H": "henry",
}
_VALUE_RE = re.compile(
    r"(?P<number>\d+(?:\.\d+)?)\s*(?P<prefix>[kKMmµμnp]?)\s*"
    r"(?P<unit>[ΩΩVAFH])"
)


@dataclass(frozen=True)
class _Primitive:
    """Sınıflandırılmış tek bir çizim ögesi."""

    kind: str  # "wire" | "resistor" | "terminal" | "dot" | "source" | ...
    rect: tuple[float, float, float, float]
    wire: Wire | None = None
    # Ok ucunun sivri köşesi (yalnızca kind == "arrowhead").
    apex: tuple[float, float] | None = None
    # Okun TABAN kenarının orta noktası (yalnızca kind == "arrowhead").
    # Okun kendi yönü `apex - base`'dir — bu, okun yakınındaki elemanın
    # MERKEZİNE göre değil, okun KENDİ geometrisine göre hesaplanmalı: küçük
    # bir akım referans oku bir elemanın hemen yanına, elemanın tümüyle bir
    # tarafında duracak şekilde çizilebiliyor (bkz. Example 3.6, Figure
    # 3.20'deki "Io" oku) — o durumda "apex - eleman_merkezi" okun gerçek
    # yönünü YANLIŞ verir, çünkü apex de taban da elemanın aynı tarafında
    # kalabilir.
    base: tuple[float, float] | None = None


def _triangle_apex(points) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Üçgenin sivri köşesi VE taban kenarının orta noktası.

    Ok ucu ince ve uzundur; taban kenarı en kısa kenardır ama bunu "en kısa
    kenarın karşısı" diye aramak eşkenara yakın üçgenlerde kırılgan. Karşı
    kenar ortasına uzaklık ölçütü ok uçlarında belirgin biçimde ayrışır.

    Dönen: (apex, taban_orta_noktası). Okun KENDİ yönü apex-taban'dır — bu,
    yakınındaki elemanın merkezine göre DEĞİL, okun kendi geometrisine göre
    hesaplanmalı (bkz. `_Primitive.base` docstring'i).
    """
    unique = []
    for point in points:
        if all(math.dist(point, seen) > 0.3 for seen in unique):
            unique.append(point)
    if len(unique) != 3:
        return None
    best, best_midpoint, best_distance = None, None, -1.0
    for index, vertex in enumerate(unique):
        other = [unique[i] for i in range(3) if i != index]
        midpoint = ((other[0][0] + other[1][0]) / 2, (other[0][1] + other[1][1]) / 2)
        distance = math.dist(vertex, midpoint)
        if distance > best_distance:
            best, best_midpoint, best_distance = vertex, midpoint, distance
    return best, best_midpoint


def _is_rhombus(lines) -> bool:
    """4 eşit kenarlı, hepsi eğik kapalı dörtgen = bağımlı kaynak baklavası.

    Kenar eşitliği şart: döndürülmüş bir direncin beyaz maske dörtgeni de
    4 eğik kenarlıdır ama kenarları 1.9 / 16.2 gibi çok farklıdır.
    """
    if len(lines) != 4:
        return False
    lengths = [math.dist((i[1].x, i[1].y), (i[2].x, i[2].y)) for i in lines]
    if min(lengths) <= 0 or max(lengths) / min(lengths) > 1.15:
        return False
    return all(abs(i[1].x - i[2].x) > 1.0 and abs(i[1].y - i[2].y) > 1.0 for i in lines)


def _ground_point(lines) -> tuple[float, float] | None:
    """Toprak sembolü mü? Öyleyse tele değen (en üstteki, en geniş) noktası.

    Toprak, üst üste duran ve aşağı indikçe KISALAN yatay çizgilerle çizilir.
    Kitapta iki farklı çizimi görüldü (2 ve 3 çizgili); ortak ölçüt bu.
    """
    horizontal = [i for i in lines if abs(i[1].y - i[2].y) < 0.5 and abs(i[1].x - i[2].x) > 1.0]
    if len(horizontal) < len(lines) or len(horizontal) < 2:
        return None
    rows: dict[float, list[float]] = {}
    for item in horizontal:
        rows.setdefault(round(item[1].y, 1), []).extend([item[1].x, item[2].x])
    if len(rows) < 2:
        return None
    ordered = sorted(rows.items())
    widths = [max(xs) - min(xs) for _, xs in ordered]
    if any(later >= earlier for earlier, later in pairwise(widths)):
        return None  # aşağı doğru kısalmıyor -> toprak değil
    top_y, top_xs = ordered[0]
    return ((min(top_xs) + max(top_xs)) / 2, top_y)


def _capacitor_plates(lines) -> bool:
    """Kapasitör mü? İki PARALEL çizgi grubu (plaka), aralarında kendi
    uzunluklarına göre KÜÇÜK bir boşlukla duruyor.

    Ölçülen (Sadiku, Figure 7.43): plaka uzunluğu ~11 pt, plakalar arası
    boşluk ~2.4 pt — her plaka bazen ortadan ikiye bölünmüş iki çizgi
    olarak geliyor (kitabın kendi çizim komutu böyle), o yüzden aynı
    satırdaki/sütundaki çizgilerin uzunlukları TOPLANIR. Düz bir tel tek
    satırda kalır (yalnızca 1 grup), bu yüzden ayrım güvenilir.
    """
    if len(lines) < 2:
        return False
    horizontal = all(abs(item[1].y - item[2].y) < 0.5 for item in lines)
    vertical = all(abs(item[1].x - item[2].x) < 0.5 for item in lines)
    if horizontal:
        def key(item):
            return round(item[1].y, 1)

        def span(item):
            return abs(item[2].x - item[1].x)
    elif vertical:
        def key(item):
            return round(item[1].x, 1)

        def span(item):
            return abs(item[2].y - item[1].y)
    else:
        return False

    groups: dict[float, float] = {}
    for item in lines:
        groups[key(item)] = groups.get(key(item), 0.0) + span(item)
    if len(groups) != 2:
        return False
    (pos1, len1), (pos2, len2) = sorted(groups.items())
    gap = pos2 - pos1
    plate_length = max(len1, len2)
    return 0 < gap <= CAPACITOR_MAX_GAP and plate_length >= CAPACITOR_MIN_PLATE


def _bbox_of(points) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _is_white(color) -> bool:
    return color is not None and all(channel > 0.9 for channel in color[:3])


def _classify_path(path) -> list[_Primitive]:
    """Tek bir çizim yolunu ilkellere çevirir (tanınmayan yol -> boş liste)."""
    rect = path["rect"]
    width, height = rect.width, rect.height
    if max(width, height) >= PAGE_DECORATION_MIN_SIZE:
        return []  # sayfa kenarlığı / kesim işaretleri

    items = path["items"]
    lines = [item for item in items if item[0] == "l"]
    curves = [item for item in items if item[0] == "c"]
    bounds = (rect.x0, rect.y0, rect.x1, rect.y1)

    # Daireler: dış uç, birleşim noktası ya da kaynak gövdesi. En az 4 eğri
    # şartı bilinçli: TAM bir daire kapanmak için tipik olarak 4 Bézier
    # parçası gerekir (ölçülen her gerçek kaynak/uç/nokta böyle). Anahtar
    # (switch) sembolündeki dönüş yönünü gösteren dekoratif yay (2 eğri,
    # AÇIK) bu şart olmadan boyut aralığı çakıştığı için yanlışlıkla
    # "kaynak" sanılıyordu (Figure 7.43'te yakalandı).
    if curves and not lines:
        if len(curves) < 4:
            return []  # kapanmamış yay — dekoratif, devre elemanı değil
        size = max(width, height)
        if size <= NODE_MARK_MAX_SIZE:
            # Beyaz dolgu = içi boş çizilmiş dış uç; renkli dolgu = bağlantı noktası.
            kind = "terminal" if _is_white(path.get("fill")) else "dot"
            return [_Primitive(kind, bounds)]
        if SOURCE_MIN_SIZE <= size <= SOURCE_MAX_SIZE:
            return [_Primitive("source", bounds)]
        return []

    # Zikzak = direnç. Küçük kutuda çok sayıda kısa parça.
    if len(lines) >= ZIGZAG_MIN_SEGMENTS and max(width, height) <= SYMBOL_MAX_SIZE:
        return [_Primitive("resistor", bounds)]

    # Baklava = bağımlı (kontrollü) kaynak. Tel sanılırsa kapalı bir ilmek
    # oluşturup devreyi sessizce kısa devre eder — bu yüzden açıkça tanınır.
    if DIAMOND_MIN_SIZE <= max(width, height) <= DIAMOND_MAX_SIZE and _is_rhombus(lines):
        return [_Primitive("dependent_source", bounds)]

    ground = _ground_point(lines) if lines and max(width, height) <= GROUND_MAX_SIZE else None
    if ground is not None:
        return [_Primitive("ground", bounds, apex=ground)]

    # Kapasitör: iki yakın, paralel plaka — düz bir telle KARIŞMAMASI için
    # önce (tek çizgili) tel/kör sınıflandırmasından ayrı, açıkça denenir.
    if lines and max(width, height) <= SYMBOL_MAX_SIZE and _capacitor_plates(lines):
        return [_Primitive("capacitor", bounds)]

    # Anahtar (switch) körü (blade): TEK, belirgin biçimde EĞİK (ne yatay
    # ne dikey) çizgi. Kitaptaki teller neredeyse istisnasız eksen-hizalı
    # çizildiği için eğiklik güvenilir bir ayırt edici — genel "wire"
    # olarak bırakılırsa kör sessizce sıradan bir tele karışır ve anahtarın
    # HANGİ konumda olduğu bilgisi kaybolur (ölçüldü: Figure 7.43, dx≈dy≈12pt).
    if len(lines) == 1 and len(items) == 1 and max(width, height) <= SWITCH_BLADE_MAX_SIZE:
        (x0, y0), (x1, y1) = (lines[0][1].x, lines[0][1].y), (lines[0][2].x, lines[0][2].y)
        if abs(x1 - x0) > SWITCH_BLADE_MIN_SKEW and abs(y1 - y0) > SWITCH_BLADE_MIN_SKEW:
            return [_Primitive("switch_blade", bounds, wire=Wire((x0, y0), (x1, y1)))]

    # Yalnızca dolgu (kontur yok): ok ucu ya da gölge — tel değil.
    if path.get("type") == "f":
        if len(lines) == 3 and max(width, height) <= ARROWHEAD_MAX_SIZE:
            corners = [(item[1].x, item[1].y) for item in lines] + [
                (item[2].x, item[2].y) for item in lines
            ]
            found = _triangle_apex(corners)
            if found is not None:
                apex, base = found
                return [_Primitive("arrowhead", bounds, apex=apex, base=base)]
        return []

    segments = [((item[1].x, item[1].y), (item[2].x, item[2].y)) for item in lines]
    # Konturu çizilmiş dikdörtgen = kapalı tel ilmeği (kitapta devre çerçevesi
    # böyle çiziliyor); dört kenarı da tel.
    if "s" in str(path.get("type", "")):
        for item in items:
            if item[0] == "re":
                segments += _rect_edges(item[1])
    segments = _merge_ribbons(segments)

    primitives = []
    for start, end in segments:
        if math.dist(start, end) < 1.0:
            continue  # sıfır uzunlukta artık
        primitives.append(_Primitive("wire", _bbox_of([start, end]), Wire(start, end)))

    # Yaylar TEL değil BAĞ: yuvarlatılmış köşeler ve kesişme atlamaları
    # bunlarla çiziliyor. Düz tel gibi ele alınırsa kirişleri yakınından
    # geçen tellere yalancı temas üretiyor (bkz. schematic.Figure.links).
    for item in curves:
        start, end = (item[1].x, item[1].y), (item[4].x, item[4].y)
        if math.dist(start, end) >= 1.0:
            primitives.append(_Primitive("link", _bbox_of([start, end]), Wire(start, end)))
    return primitives


def _rect_edges(rect) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    corners = [
        (rect.x0, rect.y0),
        (rect.x1, rect.y0),
        (rect.x1, rect.y1),
        (rect.x0, rect.y1),
    ]
    return [(corners[i], corners[(i + 1) % 4]) for i in range(4)]


def _ribbon_centre(a, b) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """İki kenar aynı KALIN telin iki yakası mı? Öyleyse orta çizgisi.

    Kitap bazı telleri tek çizgi değil, iki paralel kenar + yuvarlak uçtan
    oluşan kalın bir şerit olarak çiziyor. İki kenar ayrı tel sayılırsa
    aralarında 8 pt olan iki AYRI iletken üretilir ve devre yanlış çıkar.

    Ölçüt sıkı: kenarlar paralel, uçları birebir hizalı ve aradaki mesafe
    tel kalınlığı kadar. Gerçekten ayrı iki devre teli bu üç şartı aynı anda
    sağlamaz.
    """
    span = min(math.dist(*a), math.dist(*b))
    for candidate in (b, (b[1], b[0])):
        gap_start = math.dist(a[0], candidate[0])
        gap_end = math.dist(a[1], candidate[1])
        if max(gap_start, gap_end) > RIBBON_MAX_WIDTH or min(gap_start, gap_end) < 0.1:
            continue
        if abs(gap_start - gap_end) > 1.0:
            continue  # uçlar hizalı değil -> şerit değil
        if span <= max(gap_start, gap_end):
            continue  # kısa ve uç uca iki parça; şerit yakası değil
        return (
            ((a[0][0] + candidate[0][0]) / 2, (a[0][1] + candidate[0][1]) / 2),
            ((a[1][0] + candidate[1][0]) / 2, (a[1][1] + candidate[1][1]) / 2),
        )
    return None


def _merge_ribbons(segments):
    used: set[int] = set()
    result = []
    for i, first in enumerate(segments):
        if i in used:
            continue
        merged = None
        for j in range(i + 1, len(segments)):
            if j in used:
                continue
            merged = _ribbon_centre(first, segments[j])
            if merged is not None:
                used.add(j)
                break
        result.append(merged if merged is not None else first)
    return result


def _cluster(primitives: list[_Primitive]) -> list[list[_Primitive]]:
    """Birbirine değen/yakın ilkelleri aynı şekle toplar."""
    count = len(primitives)
    parent = list(range(count))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(count):
        for j in range(i + 1, count):
            if _rects_near(primitives[i].rect, primitives[j].rect, CLUSTER_GAP):
                parent[find(j)] = find(i)

    groups: dict[int, list[_Primitive]] = {}
    for index, primitive in enumerate(primitives):
        groups.setdefault(find(index), []).append(primitive)
    return list(groups.values())


def _rects_near(a, b, gap: float) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def _spans(page) -> list[tuple[tuple[float, float, float, float], str]]:
    """Sayfadaki metin parçaları (bbox, metin) — boşlar atılır."""
    result = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if span["text"].strip():
                    result.append((tuple(span["bbox"]), span["text"]))
    return result


def _adjacent(left, right) -> bool:
    """`right` parçası `left`'in hemen sağında ve aynı yazı satırında mı?

    Dikey ÖRTÜŞME oranına bakılır, üst kenar eşitliğine değil: alt indis
    ("R" + "eq") tabanı düşürülmüş olarak dizildiği için üst kenarları
    tutmaz ama satırlar örtüşür. Üst kenar karşılaştırması bu yüzden
    "R"yi tek harf sanıp uç adı olarak almamıza yol açmıştı.
    """
    gap = right[0] - left[2]
    if not (-1.0 <= gap <= 1.5):
        return False
    overlap = min(left[3], right[3]) - max(left[1], right[1])
    smallest = min(left[3] - left[1], right[3] - right[1])
    return smallest > 0 and overlap / smallest > 0.5


def _merge_runs(spans) -> list[tuple[tuple[float, float, float, float], str]]:
    """Bitişik parçaları birleştirir: "6" + "Ω" ayrı span'lar olarak gelir.

    Değer ile birimi ayrı fontlarda dizen mizanpaj yüzünden (Times-Roman +
    Symbol) parçalar birleştirilmeden hiçbir etiket okunamaz.
    """
    ordered = sorted(spans, key=lambda item: item[0][0])
    merged: list[tuple[tuple, str]] = []
    consumed: set[int] = set()
    for index, (bbox, text) in enumerate(ordered):
        if index in consumed:
            continue
        for other in range(index + 1, len(ordered)):
            if other in consumed:
                continue
            next_bbox, next_text = ordered[other]
            if _adjacent(bbox, next_bbox):
                bbox = (
                    bbox[0],
                    min(bbox[1], next_bbox[1]),
                    next_bbox[2],
                    max(bbox[3], next_bbox[3]),
                )
                text += next_text
                consumed.add(other)
        merged.append((bbox, text))
    return merged


def _parse_label(bbox, text: str) -> Label:
    center = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
    match = _VALUE_RE.search(text)
    if match is None:
        return Label(text=text, center=center, bbox=tuple(bbox))
    multiplier = _PREFIXES.get(match.group("prefix"), 1.0)
    return Label(
        text=text,
        center=center,
        bbox=tuple(bbox),
        value=float(match.group("number")) * multiplier,
        unit=_UNIT_SYMBOLS[match.group("unit")],
    )


def _captions(page) -> list[tuple[tuple[float, float, float, float], str]]:
    return [(bbox, text) for bbox, text in _spans(page) if _CAPTION_RE.match(text.strip())]


def extract_figures(page, caption: str) -> list[Figure]:
    """Verilen başlığa ait devre şekillerini çıkarır.

    `caption` örn. "Figure 2.36". Bir başlık altında birden fazla alt şekil
    olabilir (örn. "(a)" ve "(b)"); hepsi soldan sağa / yukarıdan aşağı
    sırayla döndürülür.
    """
    captions = _captions(page)
    target = next((bbox for bbox, text in captions if text.strip().startswith(caption)), None)
    if target is None:
        raise SchematicError(f"{caption!r} başlığı bu sayfada yok")

    primitives = [p for path in page.get_drawings() for p in _classify_path(path)]
    clusters = [c for c in _cluster(primitives) if any(p.kind in ELEMENT_PRIMITIVES for p in c)]
    if not clusters:
        raise SchematicError(f"{caption}: sayfada devre çizimi bulunamadı")

    # Bir çizim, ALTINDAKİ en yakın başlığa aittir (kitabın sayfa düzeni).
    owned = [c for c in clusters if _owning_caption(c, captions) == target]
    if not owned:
        raise SchematicError(f"{caption}: başlığa ait çizim eşleşmedi")

    spans = _spans(page)
    runs = _merge_runs(spans)
    figures = [_figure_from(cluster, runs, spans) for cluster in owned]
    return sorted(figures, key=lambda f: _figure_origin(f))


def extract_figure(page, caption: str) -> Figure:
    """Tek şekil bekler; başlık altında birden fazla alt şekil varsa hata verir."""
    figures = extract_figures(page, caption)
    if len(figures) > 1:
        raise SchematicError(
            f"{caption}: başlık altında {len(figures)} ayrı çizim var "
            "(örn. (a)/(b)); extract_figures ile hangisini istediğinizi seçin"
        )
    return figures[0]


def _figure_origin(figure: Figure) -> tuple[float, float]:
    """Şeklin sol-üst köşesi (sıralama için). Telsiz şekil sona atılır."""
    points = [wire.p1 for wire in figure.wires] or [symbol.center() for symbol in figure.symbols]
    if not points:
        return (float("inf"), float("inf"))
    return (min(p[1] for p in points), min(p[0] for p in points))


def _owning_caption(cluster: list[_Primitive], captions) -> tuple | None:
    """Kümenin altındaki, yatayda örtüşen en yakın başlık."""
    bottom = max(p.rect[3] for p in cluster)
    left = min(p.rect[0] for p in cluster)
    right = max(p.rect[2] for p in cluster)
    best, best_gap = None, None
    for bbox, _ in captions:
        gap = bbox[1] - bottom
        if gap < 0:
            continue  # başlık çizimin üstünde -> başka şeklin başlığı
        if bbox[2] < left - LABEL_MARGIN or bbox[0] > right + LABEL_MARGIN:
            continue  # yatayda hizasız
        if best_gap is None or gap < best_gap:
            best, best_gap = bbox, gap
    return best


_MINUS_SIGNS = {"-", "−", "–", "—"}

# "2vx", "vx", "4Io" gibi bağımlı-kaynak / kontrol-değişkeni etiketleri.
# `kind` harfi büyük/küçük "v"/"i" — hangi büyüklüğün kontrol edildiğini
# (gerilim mi akım mı) ayırt eder.
#
# Alt indis SADECE HARF olmalı ("o", "x" gibi) — RAKAM DEĞİL. Kitapta iki
# ayrı gösterim var: bağımlı kaynak kontrol değişkenleri harf alt indisli
# (vo, vx, Io — Example 2.6/3.6'da doğrulandı), ama KCL/mesh akım OKLARI
# (i1, i2, i3 — Example 3.1'de görüldü, dependent source İLE İLGİSİZ) rakam
# alt indisli. Rakamlar da kabul edilseydi, her sıradan dirence yakın
# duran "i2" gibi bir akım-yönü etiketi yanlışlıkla "akım probu" sanılıp o
# direncin yönünü (dolayısıyla raporlanan akım işaretini) rastgele/kararsız
# biçimde çeviriyordu (Figure 3.3'te iki çizim arasında farklı sonuç
# üretiyordu — sessiz ve tehlikeli bir hataydı).
_CONTROL_LABEL_RE = re.compile(r"^(?P<coeff>\d+(?:\.\d+)?)?(?P<kind>[vViI])(?P<sub>[a-zA-Z]{1,3})$")

# Bir elemanın kendi "+/- <değişken>" prob etiketiyle arası: ölçülen ~0.3-5 pt.
# LABEL_MARGIN'den (14, sayısal değer etiketleri için) kasıtlı daha dar —
# geniş tutulursa alakasız bir "+" ya da "−" yanlışlıkla eşleşip bir
# elemanın yönünü (dolayısıyla raporlanan akım işaretini) sessizce
# ters çevirebilir.
PROBE_MARGIN = 8.0
# Bağımlı kaynağın kendi "2vx" değer etiketiyle arası: ölçülen ~4-11 pt.
DEPENDENT_LABEL_MARGIN = 16.0


def _center_in(bbox, rect) -> bool:
    x, y = (bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def _unit(vector) -> tuple[float, float]:
    length = math.hypot(*vector)
    if length == 0:
        raise SchematicError("Kaynak yönü belirlenemedi: sıfır uzunlukta vektör")
    return (vector[0] / length, vector[1] / length)


def _plus_minus_orientation(rect, spans, pad: float) -> tuple[float, float] | None:
    """Rect'e komşu "+" ve "−" METİNLERİNDEN yön vektörü (−'dan +'ya).

    Bağımsız kaynağın polaritesinde ve bir elemanın "prob" işaretlemesinde
    (örn. "+ vx −") aynı desen kullanılıyor — ikisi de bu fonksiyonu paylaşır.
    """
    inner = (rect[0] - pad, rect[1] - pad, rect[2] + pad, rect[3] + pad)
    plus = [bbox for bbox, text in spans if text.strip() == "+" and _center_in(bbox, inner)]
    minus = [bbox for bbox, text in spans if text.strip() in _MINUS_SIGNS and _center_in(bbox, inner)]
    if not (plus and minus):
        return None
    from_minus = _center(minus[0])
    to_plus = _center(plus[0])
    return _unit((to_plus[0] - from_minus[0], to_plus[1] - from_minus[1]))


def _control_label_near(rect, runs, margin: float):
    """Rect'e en yakın kontrol-değişkeni etiketini ("2vx", "vx"...) çözer.

    Dönen: (katsayı ya da None, tür harfi, alt indis) ya da hiçbiri yoksa None.
    """
    region = (rect[0] - margin, rect[1] - margin, rect[2] + margin, rect[3] + margin)
    centre = _center(rect)
    candidates = []
    for bbox, text in runs:
        match = _CONTROL_LABEL_RE.match(text.strip())
        if match is None or not _center_in(bbox, region):
            continue
        candidates.append((math.dist(centre, _center(bbox)), match))
    if not candidates:
        return None
    match = min(candidates, key=lambda item: item[0])[1]
    coeff = float(match.group("coeff")) if match.group("coeff") else None
    return coeff, match.group("kind"), match.group("sub")


def _source_symbol(rect, spans, arrowheads: list[_Primitive]) -> Symbol:
    """Daire sembolü gerilim kaynağı mı akım kaynağı mı, ve hangi yönde?

    Ayrım ölçülen veriye dayanıyor: gerilim kaynağının içinde "+" ve "−"
    METİNLERİ var; akım kaynağının içinde ok (bir çizgi + dolu üçgen) var.
    Üçüncü bir durum görülmedi; görülürse sessizce varsayım yapmak yerine
    hata veriyoruz — yön yanlış okunursa devre çözülür ama tüm işaretler
    ters çıkar, ve bu fark edilmesi en zor hata türüdür.
    """
    centre = _center(rect)
    orientation = _plus_minus_orientation(rect, spans, SOURCE_INNER_PAD)
    if orientation is not None:
        return Symbol("voltage_source", rect, orientation=orientation)

    inner = (
        rect[0] - SOURCE_INNER_PAD,
        rect[1] - SOURCE_INNER_PAD,
        rect[2] + SOURCE_INNER_PAD,
        rect[3] + SOURCE_INNER_PAD,
    )
    inside = [head for head in arrowheads if _center_in(head.rect, inner)]
    if len(inside) == 1:
        apex = inside[0].apex
        arrow = _unit((apex[0] - centre[0], apex[1] - centre[1]))
        # SPICE'ta akım kaynağın İÇİNDE n+'dan n-'ye akar ve ok o yönü
        # gösterir; dolayısıyla n+ (nodes[0]) okun TERSİ yöndeki uçtur.
        return Symbol("current_source", rect, orientation=(-arrow[0], -arrow[1]))

    raise SchematicError(
        f"Kaynak sembolü ({centre[0]:.1f}, {centre[1]:.1f}) tanınamadı: içinde ne +/- "
        "işareti ne de tek bir ok bulundu"
    )


def _nearest_arrowhead(rect, arrowheads: list[_Primitive], margin: float) -> _Primitive | None:
    region = (rect[0] - margin, rect[1] - margin, rect[2] + margin, rect[3] + margin)
    centre = _center(rect)
    candidates = [head for head in arrowheads if _center_in(head.rect, region)]
    if not candidates:
        return None
    return min(candidates, key=lambda head: math.dist(centre, _center(head.rect)))


def _dependent_source_symbol(rect, spans, runs, arrowheads: list[_Primitive]) -> Symbol:
    """Baklava sembolü: yönü kendi +/- işaretinden, değeri ("2vx"/"4Io")
    yakınındaki etiketten okunur.

    Desteklenen tek tür: **CCVS** (akım kontrollü gerilim kaynağı) ile
    **VCVS** (gerilim kontrollü gerilim kaynağı) — ikisinin de ÇIKIŞI
    gerilimdir (baklavanın içinde +/-), yalnızca kontrol büyüklüğü farklıdır
    ("2vx" gerilim, "4Io" akım). Çıkışı AKIM olan bağımlı kaynaklar (VCCS,
    CCCS — baklava içinde ok olurdu) bu sürümde yok; sessizce yanlış okumak
    yerine açık hata veriliyor.
    """
    centre = _center(rect)
    orientation = _plus_minus_orientation(rect, spans, SOURCE_INNER_PAD)
    if orientation is None:
        inner = (
            rect[0] - SOURCE_INNER_PAD,
            rect[1] - SOURCE_INNER_PAD,
            rect[2] + SOURCE_INNER_PAD,
            rect[3] + SOURCE_INNER_PAD,
        )
        if any(_center_in(head.rect, inner) for head in arrowheads):
            raise SchematicError(
                f"Bağımlı kaynak sembolü ({centre[0]:.1f}, {centre[1]:.1f}): çıkışı akım "
                "olan bağımlı kaynaklar (VCCS/CCCS) bu sürümde desteklenmiyor"
            )
        raise SchematicError(
            f"Bağımlı kaynak sembolü ({centre[0]:.1f}, {centre[1]:.1f}) polaritesi "
            "okunamadı: içinde +/- işareti bulunamadı"
        )
    found = _control_label_near(rect, runs, DEPENDENT_LABEL_MARGIN)
    if found is None:
        raise SchematicError(
            f"Bağımlı kaynak sembolü ({centre[0]:.1f}, {centre[1]:.1f}) yanında "
            "değeri okunamadı (örn. '2vx' biçiminde bir etiket bulunamadı)"
        )
    coeff, kind_char, sub = found
    kind = "vcvs" if kind_char in ("v", "V") else "ccvs"
    return Symbol(
        kind,
        rect,
        value=coeff if coeff is not None else 1.0,
        orientation=orientation,
        control_ref=sub.lower(),
    )


def _probed_element(kind: str, rect, spans, runs, arrowheads: list[_Primitive]) -> Symbol:
    """Sıradan bir eleman (örn. direnç) — üstünde bir prob işareti varsa
    `probe_key`/`orientation` ile işaretlenir, yoksa düz döner.

    İki prob türü var: "+ vx −" (GERİLİM, VCVS için) ve ok + "Io" (AKIM,
    CCVS için). Aranan iz DAR bir mesafede (`PROBE_MARGIN`) tutuluyor: geniş
    tutulsaydı alakasız bir işaret bir elemanın yönünü sessizce ters çevirip
    yanlış akım işareti raporlatabilirdi.
    """
    voltage_orientation = _plus_minus_orientation(rect, spans, PROBE_MARGIN)
    if voltage_orientation is not None:
        found = _control_label_near(rect, runs, PROBE_MARGIN)
        if found is not None:
            _, _, sub = found
            return Symbol(kind, rect, orientation=voltage_orientation, probe_key=sub.lower())
        return Symbol(kind, rect)

    arrow = _nearest_arrowhead(rect, arrowheads, CURRENT_ARROW_MARGIN)
    if arrow is not None:
        # Etiket ("Io") elemana değil, OKA yakındır — ikisi birbirine bitişik
        # duruyor (bkz. CURRENT_LABEL_MARGIN ölçümü).
        found = _control_label_near(arrow.rect, runs, CURRENT_LABEL_MARGIN)
        if found is not None:
            _, kind_char, sub = found
            if kind_char in ("i", "I"):
                # Okun KENDİ yönü kullanılmalı (taban -> apex), elemanın
                # merkezine göre DEĞİL: bu ok küçük ve elemanın bütünüyle
                # bir tarafında durabiliyor (Example 3.6/Figure 3.20'de
                # ölçüldü) — "apex - eleman_merkezi" o durumda okun gerçek
                # yönünü yanlış verirdi (apex de taban da aynı tarafta
                # kalıyor, ikisi arasındaki KENDİ vektörleri asıl yön).
                arrow_direction = _unit(
                    (arrow.apex[0] - arrow.base[0], arrow.apex[1] - arrow.base[1])
                )
                # nodes[0]→nodes[1]'in ok yönünü (taban->apex, yani akışın
                # kendisi) göstermesi için, o yönde "ileri" pin nodes[1]
                # olacak şekilde orientation TERS veriliyor — nodes[0] her
                # zaman `orientation` boyunca projeksiyonu YÜKSEK olan pindir
                # (bkz. `_flipped`), o yüzden orientation akış yönünün
                # tersini (nodes[0]/yukarı-akış tarafını) göstermeli.
                current_orientation = (-arrow_direction[0], -arrow_direction[1])
                return Symbol(
                    kind,
                    rect,
                    orientation=current_orientation,
                    probe_key=sub.lower(),
                    probe_is_current=True,
                )
    return Symbol(kind, rect)


def _figure_from(cluster: list[_Primitive], runs, spans) -> Figure:
    figure = Figure()
    # Kaynak gövdesinin İÇİ devre teli değildir: akım kaynağının ok gövdesi
    # tek bir düz çizgi olarak geliyor ve tel sanılınca kaynak "iki teli
    # birden kesiyor" hatası veriyordu.
    bodies = [p.rect for p in cluster if p.kind in {"source", "dependent_source"}]
    arrowheads = [p for p in cluster if p.kind == "arrowhead"]
    # Akım-referans oku aramasında BAĞIMSIZ kaynakların KENDİ ok'ları hariç
    # tutulur: bir direnç, kaynağın ok'una yakın durabiliyor (Fig 3.3'te
    # ölçüldü) ve o durumda kaynağın oku sanki dirence ait bir "Io" referansı
    # gibi yanlışlıkla eşleşip her okumada FARKLI (kararsız) bir yön
    # üretiyordu.
    probe_arrowheads = [
        head for head in arrowheads if not any(_contains(body, head.rect) for body in bodies)
    ]
    for primitive in cluster:
        if primitive.kind in {"wire", "link"} and any(
            _contains(body, primitive.rect) for body in bodies
        ):
            continue
        if primitive.kind == "wire":
            figure.wires.append(primitive.wire)
        elif primitive.kind == "link":
            figure.links.append(primitive.wire)
        elif primitive.kind == "resistor":
            figure.symbols.append(
                _probed_element("resistor", primitive.rect, spans, runs, probe_arrowheads)
            )
        elif primitive.kind == "capacitor":
            figure.symbols.append(Symbol("capacitor", primitive.rect))
        elif primitive.kind == "dot":
            figure.dots.append(_center(primitive.rect))
        elif primitive.kind == "terminal":
            figure.terminals.append(Terminal(_center(primitive.rect)))
        elif primitive.kind == "ground":
            figure.grounds.append(primitive.apex)
        elif primitive.kind == "source":
            figure.symbols.append(_source_symbol(primitive.rect, spans, arrowheads))
        elif primitive.kind == "dependent_source":
            figure.symbols.append(
                _dependent_source_symbol(primitive.rect, spans, runs, arrowheads)
            )
        elif primitive.kind == "switch_blade":
            if figure.switch_blade is not None:
                raise SchematicError("Şekilde birden fazla anahtar körü bulundu — desteklenmiyor")
            figure.switch_blade = primitive.wire

    bounds = _cluster_bounds(cluster)
    # Baslik ("Figure 9.16") sekle bitisik durur; kutu-kutu mesafesi kuralinda
    # (bkz. _inside) artik pay icine giriyor -- bir ETIKET degil, disarida
    # birakilir. Metni ("9.16") sayi gibi gorunur, bir dugum adiyla ya da
    # degerle karistirilmasi icin sebep yok.
    figure.labels = [
        _parse_label(bbox, text)
        for bbox, text in runs
        if _inside(bbox, bounds, LABEL_MARGIN) and not _CAPTION_RE.match(text.strip())
    ]
    figure.terminals = [_named(terminal, figure.labels) for terminal in figure.terminals]
    return figure


def _named(terminal: Terminal, labels: list[Label]) -> Terminal:
    """Uca yazılmış tek harfi (a, b, c...) uç adı olarak alır."""
    candidates = [
        (math.dist(terminal.point, label.center), label.text)
        for label in labels
        if label.value is None and len(label.text.strip()) == 1 and label.text.strip().isalpha()
    ]
    if not candidates:
        return terminal
    distance, text = min(candidates)
    return Terminal(terminal.point, text.strip()) if distance <= TERMINAL_LABEL_RANGE else terminal


def _center(rect) -> tuple[float, float]:
    return ((rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2)


def _contains(outer, inner) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and inner[2] <= outer[2]
        and inner[3] <= outer[3]
    )


def _cluster_bounds(cluster: list[_Primitive]) -> tuple[float, float, float, float]:
    return (
        min(p.rect[0] for p in cluster),
        min(p.rect[1] for p in cluster),
        max(p.rect[2] for p in cluster),
        max(p.rect[3] for p in cluster),
    )


def _inside(bbox, bounds, margin: float) -> bool:
    """Etiket şeklin sınırlarına `margin` pt'den yakın mı (kutu-kutu mesafesi)?

    Tamamen içinde olma şartı fazla katıydı: en sağdaki "5 Ω" etiketi
    sınırın 0.4 pt dışına taştığı için düşüyor, o direnç değersiz kalıyordu.
    Bunun ilk çözümü etiketin MERKEZİNE bakmaktı; o da GENİŞ etiketleri
    kaybediyordu: BULUNDU (2026-08-25, Figure 9.16) kaynağın "vs = 10 cos 4t"
    etiketi çizime 4.4 pt uzaklıkta duruyor ama GENİŞ olduğu için merkezi
    47 pt uzakta kalıyor -- etiket düşüyor, PNG kırpımı onu dışarıda
    bırakıyor, VLM kaynağın değerini okuyamayıp null dönüyordu (aynı hata
    Figure 11.3'te de ölçüldü).

    Kutu-kutu mesafesi ikisini de doğru kapsar: örtüşen etiketin mesafesi
    zaten 0'dır (eski düzeltme korunur), geniş etiket ise EN YAKIN kenarıyla
    değerlendirilir -- genişliği onu cezalandırmaz.
    """
    gap_x = max(bounds[0] - bbox[2], bbox[0] - bounds[2], 0.0)
    gap_y = max(bounds[1] - bbox[3], bbox[1] - bounds[3], 0.0)
    return gap_x <= margin and gap_y <= margin


# Sekli PNG'e render ederken kullanilan kirpim payi (punto). Iki export
# script'i (export_sadiku_test_set.py, export_figure_ground_truth.py) AYNI
# olcegi kullanmali, yoksa uretilen goruntuler birbirine benzemez.
PAD_PT = 15.0


def figure_bbox(figure, pad: float = PAD_PT) -> tuple[float, float, float, float]:
    """Sekli PNG'e render ederken kullanilacak kirpim dikdortgeni.

    Etiketler TAM SINIRLARIYLA (`Label.bbox`) hesaba katilir. BULUNDU
    (2026-08-25, Figure 9.16 ve 11.3): eskiden yalnizca `label.center`
    kullaniliyordu, yani genis bir etiketin sol/sag yarisi kirpimin DISINDA
    kaliyordu -- render edilen PNG'de kaynagin degeri ("12 cos 4t V") yarim
    ("s 4t") gorunuyor, VLM sayiyi okuyamayip null donuyordu. Etiket
    metninin kendisi sekle AITTIR, sadece merkezi degil.

    Ayni fonksiyon eskiden IKI export script'inde birebir kopyaydi -- tek
    yerde tutuluyor ki ikisi ayrisamasin.
    """
    xs: list[float] = []
    ys: list[float] = []
    for wire in figure.wires:
        xs += [wire.p1[0], wire.p2[0]]
        ys += [wire.p1[1], wire.p2[1]]
    for symbol in figure.symbols:
        x0, y0, x1, y1 = symbol.rect
        xs += [x0, x1]
        ys += [y0, y1]
    for label in figure.labels:
        if label.bbox is not None:
            x0, y0, x1, y1 = label.bbox
            xs += [x0, x1]
            ys += [y0, y1]
        else:
            xs.append(label.center[0])
            ys.append(label.center[1])
    return min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad
