"""Sayfa listesini (chapter_number, section_number) bloklarına ayırır
(spec §16 kural 2: "Bölüm ve alt bölüm sınırları korunmalı").

Yalnızca `chapter_number` dolu sayfalar dahil edilir — bu, TOC/ön-madde
ve (henüz bölüm ataması yapılmamış) cevap-anahtarı gibi bölgeleri
otomatik olarak dışlar (gerçek Sadiku verisinde doğrulandı: "Guided
Tour" tanıtım sayfaları `chapter_number=None` kalıyor, dolayısıyla
buradaki sahte `Example`/`Practice Problem` eşleşmeleri hiç segment'e
girmiyor).
"""


def build_segments(pages: list[dict]) -> list[dict]:
    """Dönen: [{chapter_number, chapter_title, section_number,
    section_title, paragraphs: [(text, page_number), ...]}, ...]

    Bir section birden çok sayfaya yayılsa bile tek bir eleman olarak
    kalır (section sınırı asla bir chunk'ın ortasında kesilmez, çünkü
    chunk_builder yalnızca bu fonksiyonun döndürdüğü paragraflar
    üzerinde çalışır — section'lar arası hiçbir birleştirme yapmaz).
    """
    content_pages = [p for p in pages if p.get("chapter_number") is not None]

    sections: list[dict] = []
    current = None
    current_key = None

    for page in content_pages:
        key = (page["chapter_number"], page.get("section_number"))
        if key != current_key:
            if current is not None:
                sections.append(current)
            current = {
                "chapter_number": page["chapter_number"],
                "chapter_title": page.get("chapter_title"),
                "section_number": page.get("section_number"),
                "section_title": page.get("section_title"),
                "paragraphs": [],
            }
            current_key = key

        for para in (page.get("clean_text") or "").split("\n\n"):
            para = para.strip()
            if para:
                current["paragraphs"].append((para, page["page_number"]))

    if current is not None:
        sections.append(current)

    return sections
