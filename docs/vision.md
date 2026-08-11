# Proje Vizyonu

> Bu doküman, proje kapsamındaki sohbetlerde netleşen ürün vizyonunu kayıt altına alır. Proje ilerledikçe küçük revizeler anlık olarak yapılacak; bu doküman da buna göre güncellenecektir.

## Ana Ekranlar / Özellikler

1. **Konu Anlatımı** — kaynaklara dayalı, öğrenci seviyesine uygun anlatım.
2. **Örnek Sorular** — hem kitaptan direkt örnekler hem kendi ürettiğimiz örnekler; basitten zora.
3. **Devre Simülatörü** — kullanıcının elle devre kurup üzerinde oynayabildiği interaktif ekran.
4. **Kendi Devreni Yükle** *(ayrı giriş noktası)* — kullanıcı kendi devre fotoğrafını/sorusunu yükler; sistem devreyi okur, kullanıcıya "böyle mi anladım?" onay/düzeltme adımı sunar, onaylandıktan sonra simülatöre aktarılıp çözülebilir/oynanabilir hale gelir.
5. **Quiz** — iki kısım: konu bazlı ve tüm devre üzerinden.
6. **İpucu ve Değerlendirme Modu** *(quiz'den ayrı, bağımsız da kullanılabilir)* — öğrenci serbest cevap yazar, sistem doğru/kısmen doğru/yanlış/yetersiz şeklinde değerlendirir; yanlışsa doğrudan cevabı vermeden kademeli (3 seviyeli) ipucu verir.

## Tüm Modlarda Ortak Olması Gerekenler

- Her cevapta kaynak gösterimi (kitap, bölüm, sayfa).
- Öğrenci seviyesi seçimi (anlatım buna göre uyarlanır).
- Getirilen kaynak/chunk'ları şeffaf şekilde gösteren bir alan (hangi metin parçalarının kullanıldığını görebilme — hem kullanıcı güveni hem demo için).

## Mimari Kararlar (sohbette netleşen)

- **Dil modeli**: local LLM (Ollama), **qwen3:4b** seçildi. Gerçekçi bir RAG senaryosuyla test edildi (kaynak metin + Türkçe soru, sistem promptu "yalnızca kaynağı kullan"): (1) kaynakta olan bir soruda formülü (η=Pout/Pin×100%) ve hesabı (%60) doğru verdi, (2) kaynakta OLMAYAN bir soruda (kapasitör zaman sabiti) uydurmadı, "Seçilen ders kitaplarında bu bilgiye ulaşamadım." dedi — halüsinasyon riski testi geçildi. Metin-only olduğu için VLM'lerden belirgin hızlı (18.8-88.7s, VLM'lerde 67-238s).
- **Görsel okuma (devre tanıma)**: local vision-language model olarak **MiniCPM-V (4.5, 8B)** seçildi. Karar, bu donanımda (GTX 1650, 4GB VRAM) yapılan gerçek karşılaştırmaya dayanıyor (bkz. `docs/vlm-karsilastirma-sonuclari.md`):
  - **Qwen3-VL:4b** denendi — Ollama'daki entegrasyonu bu sürümde ("thinking" moduna girip hiç çıkamıyor) sorunlu çıktı: tek bir görsel için 516 saniye (8.6 dakika) sürdü, `qwen3-vl:2b` ise hiç cevap üretemedi (context limitini "düşünmeyle" dolduruyor, boş dönüyor). Saf CPU'ya zorlamak da (731s) daha kötü sonuç verdi.
  - **MiniCPM-V:8b** aynı görseli 67.7 saniyede, dolu bir cevapla işledi — kullanılabilir bir hız.
  - **Doğruluk sınırı ikisinde de aynı**: her iki model de basit bir 2 kaynaklı seri devrede (Fiore Figure 3.8) terminal polaritesini yanlış okudu — bu model seçiminden bağımsız, VLM'lere özgü bilinen bir zaaf (bkz. SINA, arXiv:2607.01609). Bu yüzden aşağıdaki zorunlu onay adımı bir "nice-to-have" değil, tasarımın zorunlu parçası.
  - Kitaptaki devreler için: önceden bir kere elle doğrulanmış netlist'ler kullanılacak (canlı okumaya güvenilmeyecek).
  - Kullanıcının kendi yüklediği devreler için: canlı VLM okuma + **zorunlu onay/düzeltme adımı** (topoloji/bağlantı okuma tek başına güvenilir değil — kendi testimiz de dahil birden fazla kaynak bunu doğruluyor).
- **Simülasyon motoru**: ngspice / PySpice gibi hazır bir kütüphane kullanılacak (fizik/matematik burada yeniden icat edilmeyecek).
- **Arayüz**: sıfırdan kendi yazacağımız bir arayüz. CircuitJS/Falstad gibi araçlara yalnızca referans/ilham için bakılabilir; kod adapte edilmeyecek veya gömülmeyecek — kullanıcının net talebi bu.

## Hatırlatma: UI Dışı Teslim Şartları

Menüde görünmeyecek ama proje değerlendirmesi için zorunlu:
- En az 40 test senaryosu.
- Baseline vs geliştirilmiş RAG sistemi karşılaştırması.
- Local model karşılaştırması (artık iki boyutlu: dil modeli + vision model).
- Mimari diyagram, metadata şeması, chunking deney sonuçları, teknik rapor, demo video.

Detaylar için: `derskitabi_project_BARIKATAI.pdf` (orijinal proje dokümanı).
