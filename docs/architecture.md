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

## Henüz boş olan klasörler (planlanan, kodu yazılmamış)

Proje dokümanının önerdiği klasör yapısına göre önceden açıldı; her biri gelecekteki bir görevi temsil ediyor:

| Klasör | Gelecekteki rolü |
|---|---|
| `app/retrieval/` | Soruya göre doğru metin parçalarını (chunk) bulma |
| `app/reranking/` | Bulunan parçaları alaka düzeyine göre yeniden sıralama |
| `app/llm/` | Local LLM (Ollama) çağrıları |
| `app/rag/` | Retrieval + LLM'i birleştirip kaynaklı cevap üretme |
| `app/quiz/` | Quiz soruları üretimi |
| `app/hints/` | Kademeli (3 seviyeli) ipucu mantığı |
| `app/api/` | Backend endpoint'leri (FastAPI) |
| `app/ui/` | Kullanıcı arayüzü |

Ürün/özellik düzeyindeki vizyon için: `docs/vision.md`.
