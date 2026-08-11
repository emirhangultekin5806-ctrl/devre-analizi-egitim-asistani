"""Pil/gerilim kaynağı sembolünün polaritesini, semboldeki çizgi
uzunluklarından (uzun çizgi = pozitif, kısa çizgi = negatif, standart
şematik çizim kuralı) deterministik olarak tespit eder.

VLM'in devre okurken en çok hata yaptığı nokta terminal polaritesi
(bkz. docs/vlm-karsilastirma-sonuclari.md) — VLM'e güvenmek yerine
görüntü işleme ile bağımsız bir doğrulama katmanı sağlar.

Yalnızca PDF'ten render edilmiş temiz/vektörel şemalar için
doğrulandı (el çizimi/fotoğraf kapsam dışı — bkz. docs/vision.md).
Sayfada pil sembolünü otomatik BULMA henüz kapsam dışı; çağıran taraf
sembolün bulunduğu bölgeyi (region) ve yönelimini (orientation) vermeli.

4 örnekte doğrulandı (Fiore DC, Figure 3.8 ve Figure 3.26):
  - 3V (yatay pil, kolon taraması): sol uzun(+), sağ kısa(-)
  - 6V (yatay pil, kolon taraması): sol uzun(+), sağ kısa(-)
  - 24V (dikey pil, satır taraması): üst kısa(-), alt uzun(+)
  - 4V (dikey pil, satır taraması): üst kısa(-), alt uzun(+)
Hepsi görüntüdeki +/- etiketleriyle (ya da kitabın metnindeki
çözümle) birebir eşleşti.
"""


def _scan_lines(pix, region, axis, threshold=128, min_run=8):
    """region=(x0,y0,x1,y1) pixmap içindeki alt-bölge (piksel).
    axis='cols' -> dikey çizgileri bulur (kolon bazlı dikey run).
    axis='rows' -> yatay çizgileri bulur (satır bazlı yatay run).
    Dönen: [(pozisyon, uzunluk), ...] çizgi merkezleri, büyük->küçük
    gürültü filtresiyle (min_run altındaki run'lar yok sayılır,
    ardından bitişik pozisyonlar gruplanır).
    """
    x0, y0, x1, y1 = region
    stride = pix.stride
    samples = pix.samples

    def is_dark(x, y):
        return samples[y * stride + x] < threshold

    profile = []  # (pos, run_length)
    if axis == "cols":
        for x in range(x0, x1):
            max_run = cur = 0
            for y in range(y0, y1):
                if is_dark(x, y):
                    cur += 1
                    max_run = max(max_run, cur)
                else:
                    cur = 0
            profile.append((x, max_run))
    else:  # rows
        for y in range(y0, y1):
            max_run = cur = 0
            for x in range(x0, x1):
                if is_dark(x, y):
                    cur += 1
                    max_run = max(max_run, cur)
                else:
                    cur = 0
            profile.append((y, max_run))

    groups = []
    cur_group = []
    for pos, run in profile:
        if run > min_run:
            cur_group.append((pos, run))
        else:
            if cur_group:
                groups.append(cur_group)
                cur_group = []
    if cur_group:
        groups.append(cur_group)

    lines = []
    for g in groups:
        max_len = max(run for _, run in g)
        center = sum(pos for pos, _ in g) / len(g)
        lines.append((center, max_len))
    return lines


def _largest_cluster(points, max_gap=60):
    """Ardışık pozisyonlar arası fark <= max_gap olanları aynı kümede
    toplar, en az 2 elemanlı en geniş (en çok eleman içeren) kümeyi
    döndürür. Pil sembolünün çizgileri birbirine yakın/düzenli aralıklı
    olduğu için (~35px), tek başına duran uzak bir gürültü çizgisini
    (terminal düğüm noktası, metin karakteri) bu şekilde eleriz.
    """
    points = sorted(points, key=lambda p: p[0])
    clusters = []
    cur = [points[0]]
    for p in points[1:]:
        if p[0] - cur[-1][0] <= max_gap:
            cur.append(p)
        else:
            clusters.append(cur)
            cur = [p]
    clusters.append(cur)
    candidates = [c for c in clusters if len(c) >= 2]
    if not candidates:
        return None
    return max(candidates, key=len)


def detect_battery_polarity(pix, region, orientation, min_battery_len=40):
    """orientation: 'horizontal' (pil yatay çizilmiş, kolon taraması
    kullanılır, sol/sağ polarite döner) ya da 'vertical' (pil dikey
    çizilmiş, satır taraması kullanılır, üst/alt polarite döner).

    Dönen: dict(lines=[...], positive_end='left'|'right'|'top'|
    'bottom') ya da None (güvenilir pil deseni bulunamadıysa).

    İki aşamalı filtre: (1) minimum uzunluk (metin/terminal noktası
    gibi kısa gürültüyü eler), (2) pozisyon kümeleme (uzakta duran,
    uzun ama pille ilgisiz bir çizgiyi eler — pil çizgileri birbirine
    yakın ve düzenli aralıklıdır, tek başına değil).
    """
    axis = "cols" if orientation == "horizontal" else "rows"
    lines = _scan_lines(pix, region, axis)
    battery_lines = [(p, length) for p, length in lines if length >= min_battery_len]
    if len(battery_lines) < 2:
        return None

    cluster = _largest_cluster(battery_lines)
    if cluster is None:
        return None

    leftmost = cluster[0]
    rightmost = cluster[-1]
    positive_end = "left" if leftmost[1] > rightmost[1] else "right"
    if orientation == "vertical":
        positive_end = {"left": "top", "right": "bottom"}[positive_end]

    return {
        "lines": cluster,
        "positive_end": positive_end,
    }
