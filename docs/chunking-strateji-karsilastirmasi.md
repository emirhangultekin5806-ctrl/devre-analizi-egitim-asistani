# Chunking Strateji Karşılaştırması

Spec §16'nın sert kısıtı: *"yalnızca sabit karakter sayısına dayanan chunking
nihai çözüm olarak kabul edilmeyecektir"* ve *"en az iki farklı chunking
stratejisi karşılaştırılmalıdır"*. Bu doküman, üretim pipeline'ında
(`scripts/chunk_books.py`) kullanılan yapı-farkında stratejiyi, spec'in
açıkça yasakladığı sabit-karakter yaklaşımına karşı gerçek veride ölçüp bu
kısıtı belgeliyor.

## Karşılaştırılan iki strateji

**1. Naive (sabit karakter) — `app/chunking/naive_chunker.py`, yalnızca bu
karşılaştırma için var, üretimde kullanılmıyor.**
Kitabın tüm `clean_text`'ini tek bir akışta birleştirip sabit uzunlukta
(2000 karakter ≈ 500 token) pencerelere böler. Section, paragraf, cümle,
hatta kelime sınırını hiç bilmez.

**2. Yapı-farkında (structure-aware) — `app/chunking/chunk_builder.py`,
üretimde kullanılan strateji.**
Önce section sınırlarını (`segment.py`), sonra content_type sınırlarını
(`classify.py`) korur; yalnızca bunların İÇİNDE token bütçesine göre paketler
(Adım 1-2, bkz. ilgili commit'ler).

## Sonuçlar (4 kitabın tamamında, gerçek veri)

| Kitap | Naive: chunk / ort. token / section-sınırı ihlali | Yapı-farkında: chunk / ort. token / ihlal |
|---|---|---|
| fiore_dc | 296 / 499 / **71 (%24.0)** | 361 / 408 / **0** |
| fiore_ac | 270 / 498 / **57 (%21.1)** | 364 / 368 / **0** |
| sadiku_1 | 427 / 499 / **115 (%26.9)** | 821 / 258 / **0** |
| sadiku_2 | 381 / 499 / **68 (%17.8)** | 627 / 302 / **0** |

Naive stratejide chunk'ların **%18-27'si iki farklı section'ın metnini aynı
chunk'a karıştırıyor** — spec kural #2'yi ("bölüm/alt bölüm sınırları
korunmalı") doğrudan ihlal ediyor. Yapı-farkında stratejide bu yapısal
olarak imkansız (0/2173, tüm kitaplarda).

Ölçüm yöntemi: `scripts/compare_chunking_strategies.py --book <id>` —
`build_page_char_spans()` her sayfanın (chapter, section) etiketini
karakter aralığıyla eşler, bir naive chunk'ın aralığı birden fazla farklı
(chapter, section) çiftiyle kesişiyorsa "ihlal" sayılır.

## Somut örnek: bir Example'ın ortadan kesilmesi (fiore_dc, chunk 39)

Naive chunk 39 şöyle bitiyor:

> "...100 watt incandescent light bulb is left on for 24"

Chunk 40 şöyle başlıyor:

> " hours. If the cost of electricity is 15 cents per kWh, determine the cost to run the light. Cost = P× t × rate..."

`Example 2.8`'in soru cümlesi kelimenin ortasından ("24" | " hours") ikiye
bölünmüş: chunk 39'u tek başına okuyan biri sorunun ne olduğunu bile
göremiyor, chunk 40'ı okuyan ise hangi örneğin çözümü olduğunu bilmiyor. Bu,
sabit-karakter yaklaşımının RAG bağlamında neden kabul edilemez olduğunun
somut kanıtı — yalnızca section sınırı değil, bir kavramsal birimin
(worked example) bütünlüğü de rastgele kesiliyor.

## Karar

Üretim pipeline'ı (`scripts/chunk_books.py`) yapı-farkında stratejiyi
kullanıyor (zaten öyleydi — Adım 1-2). `naive_chunker.py` yalnızca bu
karşılaştırmayı tekrarlanabilir kılmak için repoda tutuluyor, üretim
kodunun bir parçası değil.

**Bilinen sınırlama (yapı-farkında strateji için de geçerli):** Bir
paragrafın kendisi `MAX_TOKENS` (650) sınırını aşarsa (`_pack_paragraphs`,
`chunk_builder.py`), tek bir paragraf yine de bölünmeden tek chunk'a
alınıyor — section sınırı asla ihlal edilmiyor ama token tavanı nadiren
aşılabiliyor. Gerçek veride bunun pratik etkisi düşük (bkz. commit'lerdeki
max-token ölçümleri, en yükseği ~1091 token, chapter_summary'de tek bir
uzun paragraf durumu).
