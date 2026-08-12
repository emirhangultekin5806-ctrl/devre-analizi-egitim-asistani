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

- **Dil modeli**: local LLM (Ollama), **qwen2.5:3b-instruct** + "numaralı cümle seçimi" mimarisi. Karar, gerçek veri üzerinde yapılan üç turluk bir elemenin sonucu (detaylar: `app/rag/generate.py` docstring'i):
  - **qwen3:4b** ilk seçimdi ve kaynağa sadık cevaplar verdi, ama Ollama'da "thinking" modu kapatılamadı (`think: false` ve `/no_think` ikisi de etkisiz) → bir cevap **185-320 saniye** sürdü. Kullanılamaz yavaşlıkta.
  - **qwen2.5:3b-instruct** (10-18s) doğrudan "kaynağı oku ve açıkla" görevinde tekrar tekrar **uydurma bilgi ekledi** (kaynakta olmayan tarih/isim). Daha katı sistem promptu ve düşük temperature ile de düzelmedi: küçük modeller "bunu ekleme" gibi negatif talimatları zayıf takip ediyor.
  - **Seçilen çözüm — model metin ÜRETMİYOR, cümle SEÇİYOR:** kaynak chunk'ların cümleleri numaralanıp modele veriliyor, model yalnızca numara seçiyor; cevabın metni koddaki gerçek kaynak listesinden alınıyor. Uydurma bu yüzden **yapısal olarak imkansız** (sahte bir cümlenin numarası olamaz). Ardından ikinci bir çağrı yalnızca seçilen gerçek cümleleri Türkçeye çeviriyor.
  - **Prompt injection savunması:** soru içine gömülü "talimatları unut, kendi bildiğini yaz" saldırısı tek-adımlı mimaride başarılı oluyordu; numaralı seçim mimarisinde model istismar edilse bile yalnızca gerçek cümleler arasından seçim yapabildiği için metin uyduramıyor (gerçek veriyle doğrulandı).
  - **Sonuç:** cevap süresi **25-50 saniye** (5-7x hızlanma), halüsinasyon yok, kaynak dışı sorularda doğru şekilde "bu bilgiye ulaşamadım" diyor.

### Model kademeleri (fast / balanced / quality)

Kademe kullanıcıya sorulmuyor, **göreve bağlanıyor** (`TASK_TIERS`): sohbet → `balanced`, ipucu → `fast`, quiz üretimi → `quality`. Gelişmiş ayardan `tier=` ile elle değiştirilebilir. Gerekçe: öğrenci "hangi modeli seçsem" diye düşünmek zorunda kalmasın ve 4 GB VRAM'de pahalı olan model takası gereksiz yere tetiklenmesin.

| Kademe | Model | Süre | Not |
|---|---|---|---|
| `fast` | qwen2.5:3b-instruct | 25-50s | Türkçesi zayıf (terimleri İngilizce bırakabiliyor), zayıf donanım için yedek |
| `balanced` (varsayılan) | gemma4:e4b, `think=False` | **23-56s** | En iyi Türkçe, hızı `fast` ile hemen hemen aynı |
| `quality` | gemma4:e4b, `think="medium"` | 166-279s | Yalnızca kullanıcıyı bekletmeyen arka plan işleri için |

**Kritik bulgu — Gemma 4'ün gizli "thinking" modu:** `gemma4:e4b` varsayılan olarak her yanıttan önce görünmez bir akıl yürütme adımı çalıştırıyor. Tek karakterlik (`"2"`) bir cevap için **244 token / 30.7 saniye** harcadı; `think: False` ile aynı cevap **2 token / 4.2 saniye**. Tam pipeline'da bu fark 166-279 saniyeyi **23-56 saniyeye** indirdi. Bu yüzden her kademede `think` açıkça belirtiliyor — varsayılana bırakılırsa model sessizce yavaşlıyor. (Gemma 4 ayrıca `low`/`medium`/`high`/`max` düşünme kademelerini destekliyor; qwen3:4b'de aynı parametre etkisizdi.)

**Elenen alternatifler:**
- **gemma3:4b tek başına:** Türkçesi iyi ve hızlı (71-78s) ama *seçim* adımında güvenilmez — kaynak dışı bir soruda "bulamadım" demek yerine alakasız cümleler seçti (Butterworth filtresi, elektron yörüngeleri). Projenin en kritik gereksinimini kırdığı için elendi.
- **qwen seçim + gemma3 çeviri (hibrit):** kalite iyiydi ama her istekte model takası gerektiği için 93-112s — tek modelli Gemma 4'ten hem yavaş hem daha düşük kaliteli.
- **Embedding ile ön eleme + `keep_alive`:** Gemma 4'ü hızlandırmak için denendi, **işe yaramadı** (cold 189s, warm 279s). Darboğazın prompt uzunluğu değil gizli thinking olduğu böyle anlaşıldı — 15 cümlelik kısa promptta bile seçim adımı 168 saniye sürüyordu.

**Bilinen sınırlama:** Gemma 4 (10 GB) bu makinede %82 CPU / %18 GPU çalışıyor; 4 GB VRAM'e sığmıyor. RTX 4050'li makinede belirgin şekilde daha hızlı olması bekleniyor.
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
