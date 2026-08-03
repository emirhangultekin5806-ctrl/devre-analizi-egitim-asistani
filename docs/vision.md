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

- **Dil modeli**: local LLM (Ollama), hangi model olacağı proje ilerledikçe netleştirilecek (henüz seçilmedi).
- **Görsel okuma (devre tanıma)**: local vision-language model. Aday: **Qwen3-VL** (Ollama'da 4B/8B mevcut, OCR/diyagram okumada güçlü), karşılaştırma için **MiniCPM-V** de denenecek (proje dokümanının "en az 2 model karşılaştır" şartını da karşılar).
  - Kitaptaki devreler için: önceden bir kere elle doğrulanmış netlist'ler kullanılacak (canlı okumaya güvenilmeyecek).
  - Kullanıcının kendi yüklediği devreler için: canlı VLM okuma + **zorunlu onay/düzeltme adımı** (topoloji/bağlantı okuma tek başına güvenilir değil, araştırmalar da bunu doğruluyor — bkz. SINA, arXiv:2607.01609).
- **Simülasyon motoru**: ngspice / PySpice gibi hazır bir kütüphane kullanılacak (fizik/matematik burada yeniden icat edilmeyecek).
- **Arayüz**: sıfırdan kendi yazacağımız bir arayüz. CircuitJS/Falstad gibi araçlara yalnızca referans/ilham için bakılabilir; kod adapte edilmeyecek veya gömülmeyecek — kullanıcının net talebi bu.

## Hatırlatma: UI Dışı Teslim Şartları

Menüde görünmeyecek ama proje değerlendirmesi için zorunlu:
- En az 40 test senaryosu.
- Baseline vs geliştirilmiş RAG sistemi karşılaştırması.
- Local model karşılaştırması (artık iki boyutlu: dil modeli + vision model).
- Mimari diyagram, metadata şeması, chunking deney sonuçları, teknik rapor, demo video.

Detaylar için: `derskitabi_project_BARIKATAI.pdf` (orijinal proje dokümanı).
