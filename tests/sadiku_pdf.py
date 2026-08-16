"""Sadiku PDF'inin bu makinedeki yolu — telifli, repo dışı (bkz. docs/kaynaklar.md).

Kitap ilk makinede iki cilde bölünmüştü (`Devre analizi-1.pdf` 550 sayfa +
`Devre analizi-2.pdf` 506 sayfa; document_id'ler `sadiku_1`/`sadiku_2`).
Bu makinede TEK dosya olarak duruyor (1056 sayfa, `sadiku_full`).

**Cilt-1 sayfa indeksleri birleşik dosyada BİREBİR AYNI** — testlerin
sayfa numaralarını değiştirmeden çalışabilmesinin sebebi bu. Varsayım
değil, taşıma sırasında ölçülerek doğrulandı:
    - `compute_page_offset` her ikisinde de 31 döndürüyor
    - s.79 "Figure 2.36" -> 6 Ω (kitabın basılı cevabı)
    - s.61 "resistivity ρ" ve s.62 kontrol-karakteri testleri aynı sonuç
Cilt 2 birleşik dosyada +550 kaymış durumda (basılı numaralandırma cilt
sınırında kesintisiz devam ettiği için ofset tüm kitapta 31 kalıyor).

Başka bir makinede çalıştırmak için `SADIKU_PDF` ortam değişkeniyle yol
verilebilir.
"""

import os
from pathlib import Path

import pytest

_DEFAULT = Path(r"C:\Users\Furkan\Desktop\Emirhan+\Devre analizi.pdf")

SADIKU_PDF = Path(os.environ["SADIKU_PDF"]) if os.environ.get("SADIKU_PDF") else _DEFAULT

skip_no_sadiku = pytest.mark.skipif(
    not SADIKU_PDF.exists(),
    reason="Sadiku PDF bu makinede yok (telifli; SADIKU_PDF ile yol verilebilir)",
)
