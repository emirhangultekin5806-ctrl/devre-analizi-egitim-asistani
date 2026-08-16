# Teknik Rapor

> `docs/gun5-demo.md` bootcamp'in 5. gününe özel bir günlük kaydı, elle
> dokunulmadı. Bu doküman onun yerine, projenin **tamamını** güncel haliyle
> özetleyen teslim raporu — `docs/vision.md`'nin "teslim edilecekler"
> listesindeki "teknik rapor" maddesini karşılar. Detaya inmek gerektiğinde
> her bölüm ilgili dokümana referans veriyor; burada tekrarlanmıyor.

## 1. Amaç ve kapsam

Devre Analizi 1 (DC) ve Devre Analizi 2 (AC/ileri konular) için, tamamen
local çalışan (Ollama) bir RAG eğitim asistanı. Sabit kısıtlar: harici LLM
API yok, fine-tuning yok, telifli kaynak (Sadiku) repoda paylaşılmaz.
Detay: proje kökündeki `CLAUDE.md`.

## 2. Uçtan uca mimari

```
PDF → çıkarım (app/ingestion) → yapı tespiti → chunking (app/chunking)
    → embedding + Chroma index (app/retrieval)
    → RAG (app/rag) ────────────┬── Quiz (app/quiz)
                                 └── İpucu/Değerlendirme (app/hints)

Devre çözücü (app/circuit, ngspice/PySpice) ── bağımsız katman, hem
    kitap şekli okumada (app/vision, vektör geometri) hem kullanıcının
    kendi yüklediği devrede (app/vision/vlm_read.py, VLM) kullanılıyor

Arayüz: app/ui/streamlit_app.py (6 ekran, aşağıda durum tablosu)
```

Adım adım veri akışı ve her modülün gerekçesi: `docs/architecture.md`.

## 3. Temel tasarım kararları (özet)

Her biri gerçek veride ölçülüp elenen alternatiflerle birlikte
`docs/vision.md`'de tam belgeli; burada yalnızca sonuç:

- **RAG, 4 adımlı mimari** (sorgu çevirisi → arama → numaralı-cümle-seçimi
  → sentez). Model **metin üretmiyor, cümle SEÇİYOR** — seçilen her cümle
  koddaki gerçek kaynak listesinden birebir alınıyor, uydurma yapısal
  olarak imkansız. Üç önceki tek-adımlı deneme (qwen3:4b, qwen2.5:3b
  serbest, qwen2.5 alıntı-doğrulama) sırasıyla elendi: yavaşlık,
  halüsinasyon, tutarsız talimat takibi.
- **Chunking yapı-farkında** — section/content_type sınırlarını asla
  ihlal etmiyor (naive/sabit-karakter alternatifiyle ölçülü karşılaştırma:
  `docs/chunking-strateji-karsilastirmasi.md`, naive'de %18-27 ihlal, bu
  stratejide 0).
- **Kitap şekilleri VLM'siz okunuyor** — PDF'in vektör verisi (çizim
  komutları) geometrik olarak ayrıştırılıyor (`app/vision/pdf_figure.py`,
  `schematic.py`), deterministik ve kesin. VLM yalnızca kullanıcının kendi
  yüklediği RASTER görsel için gerekiyor (`app/vision/vlm_read.py`).
- **Devre çözümü ngspice/PySpice ile** — fizik yeniden icat edilmiyor.
  DC, AC (fazör), süperpozisyon/Thevenin-Norton, geçici rejim (RC/RL/RLC),
  üç fazlı sistemler, bağımlı kaynaklar (VCVS/CCVS) destekleniyor.
- **VLM okuması asla doğrudan güvenilmiyor** — hem bu projede ölçülen hem
  literatürde (SINA, arXiv:2607.01609) raporlanan bilinen bir zaaf
  (kaynak polaritesi) yüzünden, kullanıcı onay/düzeltme adımı tasarımın
  zorunlu parçası, sonradan eklenen bir güvenlik önlemi değil.

## 4. Model karşılaştırması

**Dil modeli** (`docs/vision.md` §"Model kademeleri"): `gemma4:e4b`
(varsayılan, `think=False` kritik — açık bırakılırsa 5-7x yavaşlıyor),
`qwen2.5:3b-instruct` (hızlı yedek), ikisi de `bge-m3` embedding ile.

**Görsel-dil modeli** (`docs/vlm-karsilastirma-sonuclari.md`):
`minicpm-v4.5:8b` seçildi — `qwen3-vl` ailesi (2b/4b) bu makinede bir
Ollama entegrasyon hatası yüzünden (gizli "thinking" modunda takılıp boş
dönüyor) kullanılamaz çıktı. **Not:** oradaki süre ölçümleri (516s/67.7s)
ilk geliştirme makinesine (GTX 1650, 4GB VRAM) ait; proje RTX 4050/6GB
VRAM'e taşındıktan sonra yeniden ölçülmedi — güncel donanımda muhtemelen
daha hızlı, ama bu henüz doğrulanmadı.

## 5. Değerlendirme sonuçları (bu makinede, 2026-08-16 itibarıyla)

| Ölçüt | Sonuç |
|---|---|
| Birim/entegrasyon testleri | **347/347 geçti**, 0 atlandı |
| RAG kalite regresyonu (`scripts/evaluate_rag.py`) | **22/22** — tanım soruları, kaynak-dışı reddetme, prompt injection |
| Baseline vs geliştirilmiş RAG (`scripts/compare_rag_baseline.py`) | Baseline 20/22, Geliştirilmiş **22/22** (bkz. `docs/rag-baseline-karsilastirmasi.md`) |
| Index | 2230 chunk (Fiore DC 361, Fiore AC 364, Sadiku 1505) |
| Lint (`ruff check .`) | Temiz |

**Şekilden-çözüme uçtan uca doğrulama** (kitabın PDF'inden okunup elle
hiç dokunulmadan çözülen, kitabın basılı cevabıyla birebir tutan örnekler):
Figure 2.36 (Req=6Ω), Figure 2.37 (Rab=11.2Ω, indirgeme adımları da
birebir), Figure 3.3 (akım kaynaklı, v1=13.333V/v2=20V), Figure 3.18
(gerilim kaynaklı, I1=I2=1A/I3=0), Figure 2.23/2.24 (VCVS bağımlı
kaynak), Figure 3.20 (CCVS, 4 düğümlü köprü, Io=1.5A), Figure 2.52
(köprü devresi, Y-Δ gerektiriyor, Rab=9.632Ω/i=12.458A), Figure 7.43
(SPDT anahtar + kapasitör, RC geçici rejim). Tam liste ve ölçüm
detayları: `docs/vision.md`.

## 6. Bilinen sınırlamalar

- VLM devre okuması kaynak polaritesinde güvenilmez — bu yüzden onay
  adımı zorunlu (bkz. §3). Bağımlı kaynaklar (VCVS/CCVS) VLM tarafından
  hiç okunmuyor, yalnızca elle eklenebiliyor.
- "Kendi Devreni Yükle" ekranının VLM yolu kodlandı ve doğrulama
  katmanı test edildi (`tests/test_vlm_read.py`) ama henüz GERÇEK bir
  görselle uçtan uca denenmedi — yalnızca elle-giriş yolu gerçek bir
  Streamlit oturumunda doğrulandı (`tests/test_streamlit_own_circuit.py`).
- Onaylanan devre şu an bir simülatöre değil, doğrudan çözüp sonuç
  göstermeye gidiyor — "Devre Simülatörü" ekranı henüz yok.
- Paralel RLC için netlist-entegre otomatik türetim yok (yalnızca
  formül-seviyesi fonksiyon var); L/C'nin komşu olmadığı genel topolojiler
  açık hatayla durur, sessizce yanlış hesaplamaz.

## 7. Kalan işler

1. **Devre Simülatörü** — interaktif çizim arayüzü (backend hazır,
   yalnızca frontend eksik; Streamlit'in doğal bir çözüm olmadığı not
   edilmiş, özel bir canvas/SVG bileşeni gerekebilir).
2. **VLM yolunun gerçek görsel(ler)le doğrulanması.**
3. **VLM karşılaştırma ölçümlerinin RTX 4050'de tekrarlanması** (isteğe
   bağlı — mevcut karar donanım-bağımsız bir hataya dayandığı için acil
   değil).
4. Demo videosu (proje spec'inin "teslim edilecekler" listesinde).
5. Araştırma hattı (bu rapor kapsamı dışında, ayrı bir bağımsız proje
   olarak yürütülüyor): `Desktop\IT\devre-yolo-dedektor` — VLM'in zayıf
   olduğu sembol/polarite tespiti için küçük bir YOLO tabanlı doğrulama
   katmanı, kullanıcının kendi fikri, henüz erken aşamada (ortam kuruldu,
   sentetik veri üretimi/eğitim başlamadı).

## 8. Referans dokümanlar

- Mimari detay: `docs/architecture.md`
- Ürün vizyonu + tüm model/tasarım kararları: `docs/vision.md`
- Kaynak lisansları: `docs/kaynaklar.md`
- Chunking karşılaştırması: `docs/chunking-strateji-karsilastirmasi.md`
- VLM karşılaştırması: `docs/vlm-karsilastirma-sonuclari.md`
- Baseline karşılaştırması: `docs/rag-baseline-karsilastirmasi.md`
- Kurulum/komutlar: proje kökü `README.md`, `CLAUDE.md`
