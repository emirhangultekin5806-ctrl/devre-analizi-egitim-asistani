# 3. Gün — Kısa Risk Değerlendirmesi

> Doküman 1'in 3. Gün gereksinimi: "Bu çözüm hangi durumda bozulabilir?" sorusunun cevabı, gün sonu teslimlerinden biri.

Bu turda iki çözüm uygulandı: Fiore için `clean_text()` (Adım 3) ve Sadiku 1-2 için genelleme — `detect_structure_sadiku()`, `compute_page_offset()`, `clean_text_sadiku()` (Adım 4). İkisi de gerçek veriye karşı doğrulandı ve test edildi, ama her sezgisel (heuristic) çözümde olduğu gibi kırılabileceği varsayımlar var.

## Adım 3 — `clean_text()` (Fiore)

1. **Sayfa no ile tesadüfen çakışan gerçek veri.** Kural, `page_number + 1`'e eşit tek başına duran her satırı siler. Bir grafik ekseni değeri ya da formülün parçası olan bir sayı tesadüfen bu değere eşitse, o satır da yanlışlıkla silinir. Gerçek veride örneği görülmedi ama kuralın kendisi bunu ayırt edemiyor.
2. **"Notes" ayraç sayfası tespiti tam 5 satırlık sabit bir kalıba dayanıyor.** Fiore ileride bu sayfayı biraz farklı biçimlendirirse (örn. dekoratif satır sayısı değişirse) tespit kaçırılır, sayfa temizlenmeden kalır — sessiz bir kaçırma, hata vermez.
3. **Tek başına duran "." her zaman TOC nokta-lideri sayılıp siliniyor.** Meşru bir yerde (örn. yalnız başına bir ondalık nokta) aynı şekilde çıkarsa o da silinir.

## Adım 4 — Sadiku genelleme

1. **`compute_page_offset` tüm kitap için tek bir sabit ofset varsayıyor.** Kitabın ortasında beklenmedik bir numaralandırma kesintisi olursa (örn. araya farklı numaralı bir ek girmesi), o bölge için ofset yanlış olur — ya gerçek footer kaçırılır ya da yanlış bir satır silinir.
2. **Bootstrap pekiştirme penceresi (40 sayfa) ampirik bir sabit, kitabın yapısal bir garantisi değil.** Bir bölüm gerçekten 40 sayfadan uzun bir giriş bloğuyla açılsaydı, gerçek bölüm sessizce reddedilir ve önceki bölüm numarası o sayfalara yanlışlıkla taşınmaya devam ederdi. Bu en riskli senaryo: hata vermeden sessizce yanlış etiketleme.
3. **"Guided Tour" sahte-splash reddi, "gerçek pekiştirme bulunamıyor" varsayımına dayanıyor.** Kitapta bir bölümün birebir tekrarlandığı VE ardından gerçekten pekiştirici içerik geldiği bir ek olsaydı (örn. bir bölümün tamamen yeniden basıldığı bir ek), algoritma bunu yanlışlıkla gerçek bir bölüm geçişi sanabilirdi.
4. **Ön-madde/Index/Ek footer'ları (roma rakamı, `I-N`, `A-N`) bilerek temizlenmiyor.** Bu bölgelerin `clean_text`'inde hâlâ sayfa no kalıntısı var; chunking aşamasında bunun farkında olunmalı.
5. **Verso/recto desenleri çok spesifik literal string'lere ("Chapter N", "N.M") bağlı.** Extraction bir satırı beklenmedik şekilde bölerse (örn. "Chapter" ve numarası iki ayrı sayfaya düşerse), o noktada section-level tespit sessizce zayıflar; chapter_number splash sayesinde yine de doğru kalır.

## Ortak ders

Hiçbiri "kod çöker" türünden bir kırılma değil — hepsi **sessiz, yanlış etiketleme** riski. Bu yüzden ileride (chunking/embedding aşamasında) bu alanlara güvenirken, düşük-güven bölgelerini (needs_review, chapter_number=None, ofset=None sayfaları) ayrı işaretlemek faydalı olur.
