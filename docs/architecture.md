# Mimari Harita

> Bu doküman, 2. Gün kapsamında soru-cevap yöntemiyle birlikte çıkarıldı. Proje ilerledikçe güncellenecektir.

## Şu ana kadar çalışan boru hattı (pipeline)

```
PDF dosyası (örn. data/raw/open/Fiore_DC_Electrical_Circuit_Analysis.pdf)
    │
    ▼
app/ingestion/pdf_extract.py → extract_pages()
    - PyMuPDF ile her sayfadan ham metni çeker
    - Her sayfa için: document_id, source_file, page_number, page_label,
      raw_text, char_count, extraction_method, needs_review
    - chapter_number / chapter_title / section_number / section_title
      henüz None (bu adımın işi değil)
    │
    ▼
app/ingestion/structure_detect.py → detect_structure_fiore()
    - Aynı sayfa listesini alır, chapter/section alanlarını doldurur
    - Kitaptaki başlıkların "iki kez art arda yazılma" desenini kullanarak
      hangi sayfanın hangi bölüme/alt bölüme ait olduğunu etiketler
    - Kendisi metin çıkarmaz, sadece var olan kayıtları etiketler
    │
    ▼
scripts/parse_books.py (orkestra şefi / CLI giriş noktası)
    - Komut satırı argümanını okur (--book fiore_dc)
    - extract_pages() → detect_structure_fiore() sırasıyla çağırır
    - Sonucu data/processed/<document_id>.jsonl olarak yazar
    - Özet istatistik basar (sayfa sayısı, needs_review, chapter kapsaması)
```

**Çıktı formatı:** `data/processed/<document_id>.jsonl` — her satır bir sayfayı temsil eden bir JSON kaydı (JSON Lines biçimi, tek büyük JSON değil).

**Neden `extraction_method` alanı var:** Şu an hep `"pymupdf"`, ama ileride bazı kitaplar (örn. taranmış olabilecek Sadiku PDF'leri) OCR gerektirebilir; bu alan hangi sayfanın hangi yöntemle çıkarıldığını iz olarak tutar.

## Test

`tests/test_pdf_extract.py` — Fiore DC üzerinde bir smoke test: sayfa sayısı doğru mu, metin okunabilir mi, temel alanlar dolu mu. Sadiku'ya bağımlı değil (o dosyalar repo dışında).

## Retrieval (embedding + vector arama)

```
data/chunks/<document_id>.jsonl (chunking asamasinin ciktisi)
    │
    ▼
app/retrieval/embed.py → embed_texts()
    - Ollama'nin /api/embed'ine (toplu istek) bge-m3 modeliyle istek atar
    - Cok dilli: Turkce soru -- Ingilizce kaynak eslesmesi icin secildi
    │
    ▼
app/retrieval/index.py → index_chunks()
    - Metadata'yi Chroma'nin kabul ettigi sekle indirger (None/liste alanlar)
    - HttpClient uzerinden calisan Chroma sunucusuna upsert eder
    │
    ▼
app/retrieval/search.py → search(query, top_k)
    - Soru metnini embed eder, cosine similarity ile en yakin chunk'lari doner
```

**Chroma sunucu modu (onemli):** ChromaDB'nin gomulu/dosya modu
(`PersistentClient`) bu makinede gercek indeksleme yukunde index
dosyalarini bozdu (bkz. `app/retrieval/index.py` docstring'i). Bu yuzden
Chroma, Ollama gibi ayri bir arka plan servisi olarak calistiriliyor:
`chroma run --path data/indexes/chroma --port 8123`. Uygulama HttpClient
ile bu sunucuya baglaniyor -- index dosyalarina yalnizca sunucu process'i
erisiyor.

**CLI:** `scripts/build_index.py --all` (chunk'lari sunucuya yazar,
`--book <id>` tek kitap icin).

## Cevap üretimi (RAG)

`app/rag/generate.py → answer_question()` dört adımda çalışır:

```
Türkçe soru
    │
    ▼ 1. Sorgu çevirisi (LLM)
"What is inductive reactance?"        ← kaynaklar İngilizce; kısa Türkçe
    │                                   sorgular çok kötü eşleşiyordu
    │                                   ("Direnç nedir?" 0.43 → "What is
    │                                   resistance?" 0.67). Soruya gömülü
    │                                   prompt injection de burada ayıklanır.
    ▼ 2. Arama (app/retrieval/search.py)
en yakın N chunk  (content_type ile filtrelenebilir)
    │
    ▼ 3. Cümle seçimi
chunk'ların cümleleri → embedding ile soruya yakınlığa göre sıralanır →
ilk 20 numaralanıp modele verilir → model yalnızca NUMARA döner.
Model bu adımda metin ÜRETMEZ; seçilen cümleler koddaki gerçek listeden
birebir alınır (bu adımda uydurma yapısal olarak imkansız).
    │
    ▼ 4. Sentez (LLM)
Seçilen gerçek cümlelerden kısa, formül odaklı Türkçe cevap (LaTeX).
Kaynakta cevap yoksa: "Seçilen ders kitaplarında bu bilgiye ulaşamadım."
```

**Model kademeleri:** göreve bağlı (`TASK_TIERS`) — sohbet `balanced`
(gemma4:e4b), ipucu `fast` (qwen2.5:3b), quiz `quality`. Gerekçeler ve
ölçümler: `docs/vision.md`. **Kritik ayar:** `think` her kademede açıkça
belirtilir; gemma4 varsayılanda gizli "thinking" çalıştırıp 3-5 kat
yavaşlıyor.

**Cevap kalitesi regresyon seti:** `scripts/evaluate_rag.py`
(vakalar: `data/eval/rag_cases.json`) — tanım soruları, kaynak-dışı
reddetme, prompt injection. Prompt/model değiştiren her turda çalıştırılır.

## Quiz

`app/quiz/generate.py → generate_quiz()` — konu bazlı çoktan seçmeli quiz.
RAG ile aynı zemini kullanır (sorgu çevirisi → arama → cümle sıralama), ama
quiz doğası gereği modelin metin üretmesini gerektirir. Bu yüzden koruma
"uydurma imkansız" değil, **sınırlandırılmış**:

- Sorular yalnızca kaynak cümlelerden üretilir.
- Çıktı JSON istenir ve `_parse_quiz` ile katı doğrulanır; biçime uymayan
  veya eksik seçenekli sorular sessizce atılır (8 birim testi).
- Her sorunun doğru cevabı için dayandığı kaynak cümle ("kanıt") kullanıcıya
  gösterilir, öğrenci doğrulayabilsin.

Ölçüm: 5 soru ≈ 160 sn (`balanced`). `quality` kademesiyle 3 soru 243 sn
sürüyordu — arayüzde kullanıcı beklediği için `TASK_TIERS["quiz"]`
`balanced` yapıldı, kalite farkı gözlenmedi.

## Arayüz

`app/ui/streamlit_app.py` — beyaz-lacivert, soldan ekran seçmeli.
`docs/vision.md`'deki 6 ana ekranı listeler; kodu yazılmamış olanlar
gizlenmez, "hazır değil" durumuyla gösterilir.

| Ekran | Durum |
|---|---|
| 📖 Konu Anlatımı | Çalışıyor (RAG) |
| 📝 Quiz | Çalışıyor |
| 📚 Kaynaklar | Çalışıyor (işlenmiş içerik istatistikleri) |
| 💡 İpucu Modu | Hazır değil (`app/hints/`) |
| ⚡ Devre Simülatörü | Hazır değil |
| 📷 Kendi Devreni Yükle | Hazır değil (`app/vision/` + onay akışı) |

Çalışan her ekranda kaynak gösterimi ve "Ne oldu?" şeffaflık paneli vardır
(getirilen kaynaklar, kaç adaydan kaçının seçildiği, adım süreleri, model).
`.streamlit/config.toml` sunucuyu `127.0.0.1`'e sabitler — telifli kaynak
dışarı açılmamalı.

## Henüz boş olan klasörler (planlanan, kodu yazılmamış)

| Klasör | Gelecekteki rolü |
|---|---|
| `app/reranking/` | Bulunan parçaları alaka düzeyine göre yeniden sıralama |
| `app/llm/` | Local LLM çağrıları (şu an `generate.py` içinde) |

| `app/hints/` | Kademeli (3 seviyeli) ipucu mantığı |
| `app/api/` | Backend endpoint'leri (FastAPI) |

Ürün/özellik düzeyindeki vizyon için: `docs/vision.md`.
