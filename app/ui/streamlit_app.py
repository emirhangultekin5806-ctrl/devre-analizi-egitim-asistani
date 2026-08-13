"""Streamlit arayüzü — soldan ekran seçmeli çok bölümlü uygulama.

Çalıştırma:
    .venv\\Scripts\\streamlit run app/ui/streamlit_app.py

Önkoşullar (ikisi de ayrı servis olarak çalışıyor olmalı):
    ollama serve
    chroma run --path data/indexes/chroma --port 8123

Ekranlar `docs/vision.md`'deki 6 ana ekranı temel alır. Henüz kodu
yazılmamış olanlar gizlenmiyor, "hazır değil" durumuyla gösteriliyor —
böylece ürünün tamamı görünür kalıyor ve neyin çalıştığı belirsiz olmuyor.

Her çalışan ekranda, `docs/vision.md`'nin "tüm modlarda ortak" şartı gereği
kaynak gösterimi ve boru hattı şeffaflığı ("Ne oldu?") bulunur.
"""

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.quiz.generate import generate_quiz  # noqa: E402
from app.rag.generate import (  # noqa: E402
    CONCEPT_CONTENT_TYPES,
    TASK_TIERS,
    TIERS,
    answer_question,
)

EXAMPLE_CONTENT_TYPES = ["example", "practice_problem"]
CHUNKS_DIR = ROOT / "data" / "chunks"

NAVY = "#0d2149"
NAVY_LIGHT = "#1c3a6e"
ACCENT = "#2f6fb8"

st.set_page_config(page_title="Devre Analizi Asistanı", page_icon="⚡", layout="wide")

st.markdown(
    f"""
    <style>
      .stApp {{ background: #ffffff; }}
      h1, h2, h3 {{ color: {NAVY}; }}
      section[data-testid="stSidebar"] {{ background: {NAVY}; }}
      section[data-testid="stSidebar"] * {{ color: #e8eef8 !important; }}
      section[data-testid="stSidebar"] h1,
      section[data-testid="stSidebar"] h2,
      section[data-testid="stSidebar"] h3 {{ color: #ffffff !important; }}
      .da-title {{
        background: {NAVY}; color: #fff; padding: .9rem 1.2rem;
        border-radius: 10px; margin-bottom: 1.1rem;
      }}
      .da-title p {{ margin: .25rem 0 0; color: #c9d8ef; font-size: .88rem; }}
      .da-chip {{
        display: inline-block; background: {NAVY_LIGHT}; color: #fff;
        padding: .18rem .6rem; border-radius: 999px; font-size: .75rem;
        margin-right: .35rem;
      }}
      .da-src {{
        border: 1px solid #dbe4f2; border-radius: 8px; padding: .6rem .9rem;
        margin-bottom: .5rem; background: #fafcff;
      }}
      .da-src-title {{ color: {NAVY}; font-weight: 600; font-size: .9rem; }}
      .da-src-meta {{ color: #64748b; font-size: .78rem; margin-top: .15rem; }}
      div.stButton > button {{
        background: {NAVY}; color: #fff; border: 0; border-radius: 8px;
        padding: .5rem 1.4rem; font-weight: 600;
      }}
      div.stButton > button:hover {{ background: {ACCENT}; color: #fff; }}
    </style>
    """,
    unsafe_allow_html=True,
)


# --- ortak parçalar ---------------------------------------------------------


def header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="da-title"><h1 style="color:#fff;margin:0;font-size:1.45rem;">{title}</h1>'
        f"<p>{subtitle}</p></div>",
        unsafe_allow_html=True,
    )


def render_sources(sources: list[dict]) -> None:
    st.markdown("##### Kullanılan kaynaklar")
    for i, src in enumerate(sources, start=1):
        page = f" · s.{src['printed_page']}" if src.get("printed_page") else ""
        section = f" · {src['section_number']}" if src.get("section_number") else ""
        extra = ""
        if src.get("distance") is not None:
            extra = f" · yakınlık {1 - src['distance']:.2f}"
        st.markdown(
            f'<div class="da-src"><div class="da-src-title">{i}. {src["book_title"]}</div>'
            f'<div class="da-src-meta">Bölüm {src["chapter_number"]} — '
            f"{src['chapter_title']}{section}{page}{extra}</div></div>",
            unsafe_allow_html=True,
        )


def service_error(exc: Exception) -> None:
    st.error(
        f"İstek başarısız: {type(exc).__name__} — {exc}\n\n"
        "Ollama (`ollama serve`) ve Chroma "
        "(`chroma run --path data/indexes/chroma --port 8123`) çalışıyor mu?"
    )


def not_built(title: str, description: str, needs: str) -> None:
    header(title, "Bu ekran henüz geliştirilmedi")
    st.info(f"**Planlanan:** {description}")
    st.caption(f"Gereken altyapı: {needs}")


# --- ekranlar ---------------------------------------------------------------


def screen_konu_anlatimi() -> None:
    header("📖 Konu Anlatımı", "Sorular yalnızca ders kitaplarından yanıtlanır; kaynakta yoksa uydurulmaz.")

    with st.sidebar:
        st.markdown("### Ayarlar")
        task = st.selectbox("Görev", list(TASK_TIERS), index=list(TASK_TIERS).index("chat"))
        st.caption(f"Otomatik kademe: **{TASK_TIERS[task]}**")
        override = st.checkbox("Kademeyi elle seç (gelişmiş)")
        tier = st.selectbox("Kademe", list(TIERS), disabled=not override) if override else None
        top_k = st.slider("Getirilecek kaynak sayısı", 3, 10, 5)
        search_examples = st.checkbox(
            "Çözümlü örneklerde ara",
            help="Kapalıyken yalnızca konu anlatımı taranır (tanım soruları için önerilir).",
        )

    question = st.text_input("Sorunuz", placeholder="örn. Kirchhoff akım yasası nedir?")
    if not (st.button("Sor") and question.strip()):
        return

    started = time.perf_counter()
    with st.spinner("Kaynaklar taranıyor ve cevap hazırlanıyor…"):
        try:
            result = answer_question(
                question.strip(),
                top_k=top_k,
                tier=tier if override else None,
                task=task,
                content_types=EXAMPLE_CONTENT_TYPES if search_examples else CONCEPT_CONTENT_TYPES,
            )
        except Exception as exc:  # noqa: BLE001 - arayüz sınırı, çökmemeli
            service_error(exc)
            return
    elapsed = time.perf_counter() - started

    st.markdown("#### Cevap")
    with st.container(border=True):
        st.markdown(result["answer"])

    cfg = result["tier"]
    st.markdown(
        f'<div style="margin:.6rem 0 1rem;"><span class="da-chip">{cfg["model"]}</span>'
        f'<span class="da-chip">düşünme: {cfg["think"]}</span>'
        f'<span class="da-chip">{elapsed:.1f} sn</span></div>',
        unsafe_allow_html=True,
    )

    render_sources(result["sources"])

    with st.expander("Ne oldu? (adım adım)"):
        t = result["timings"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Kaynak arama", f"{t['retrieval']:.1f} sn")
        c2.metric("Cümle seçimi", f"{t['selection']:.1f} sn")
        c3.metric("Cevap üretimi", f"{t['synthesis']:.1f} sn")
        st.caption(f"Arama sorgusu (İngilizceye çevrildi): _{result['search_query']}_")
        st.caption(
            f"{result['candidate_sentence_count']} aday cümle bulundu, "
            f"benzerliğe göre en iyi {result['ranked_candidate_count']} tanesi modele verildi, "
            f"{len(result['selected_sentences'])} tanesi seçildi:"
        )
        for sentence in result["selected_sentences"]:
            st.markdown(f"- {sentence}")


def screen_quiz() -> None:
    header("📝 Quiz", "Sorular kitaptaki cümlelerden üretilir; her sorunun kaynak kanıtı gösterilir.")

    with st.sidebar:
        st.markdown("### Ayarlar")
        question_count = st.slider("Soru sayısı", 3, 8, 5)
        top_k = st.slider("Getirilecek kaynak sayısı", 3, 10, 5)
        st.caption("Quiz `quality` kademesini kullanır (arka plan üretimi).")

    topic = st.text_input("Konu", placeholder="örn. Kirchhoff yasaları")
    if st.button("Quiz oluştur") and topic.strip():
        with st.spinner("Sorular hazırlanıyor… (1-2 dakika sürebilir)"):
            try:
                st.session_state.quiz = generate_quiz(
                    topic.strip(), question_count=question_count, top_k=top_k
                )
            except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                service_error(exc)
                return

    quiz = st.session_state.get("quiz")
    if not quiz:
        return
    if not quiz["questions"]:
        st.warning(
            "Model bu konu için geçerli biçimde soru üretemedi. "
            "Konuyu biraz daha belirgin yazıp tekrar deneyin."
        )
        return

    st.markdown(f"#### {quiz['topic']} — {len(quiz['questions'])} soru")
    answers: dict[int, str] = {}
    for i, item in enumerate(quiz["questions"], start=1):
        with st.container(border=True):
            st.markdown(f"**{i}. {item['soru']}**")
            answers[i] = st.radio(
                "Cevabınız",
                list(item["secenekler"]),
                format_func=lambda k, it=item: f"{k}) {it['secenekler'][k]}",
                key=f"quiz_q{i}",
                index=None,
            )

    if st.button("Cevapları kontrol et"):
        correct = 0
        for i, item in enumerate(quiz["questions"], start=1):
            given = answers.get(i)
            if given == item["dogru"]:
                correct += 1
                st.success(f"{i}. Doğru — {item['dogru']}) {item['secenekler'][item['dogru']]}")
            else:
                verdict = "Boş bırakıldı" if given is None else f"Yanlış (seçilen: {given})"
                st.error(
                    f"{i}. {verdict} — Doğru cevap: "
                    f"{item['dogru']}) {item['secenekler'][item['dogru']]}"
                )
            if item["kanit"]:
                st.caption(f"Kaynak: _{item['kanit']}_")
        st.markdown(f"### Sonuç: {correct}/{len(quiz['questions'])}")

    render_sources(quiz["sources"])


def screen_kaynaklar() -> None:
    header("📚 Kaynaklar", "Sisteme yüklenmiş ders kitapları ve işlenmiş içerik.")

    import json

    rows, total = [], 0
    for path in sorted(CHUNKS_DIR.glob("*.jsonl")):
        types: dict[str, int] = {}
        title = path.stem
        count = 0
        with path.open(encoding="utf-8") as f:
            for line in f:
                chunk = json.loads(line)
                count += 1
                title = chunk.get("book_title", title)
                types[chunk.get("content_type", "?")] = types.get(chunk.get("content_type", "?"), 0) + 1
        total += count
        rows.append(
            {
                "Kitap": title,
                "Dosya": path.stem,
                "Chunk": count,
                "Anlatım": types.get("concept", 0),
                "Örnek": types.get("example", 0),
                "Alıştırma": types.get("practice_problem", 0),
                "Özet": types.get("chapter_summary", 0),
            }
        )

    if not rows:
        st.warning("Henüz işlenmiş içerik yok. `scripts/chunk_books.py` çalıştırılmalı.")
        return

    st.metric("Toplam chunk", total)
    st.dataframe(rows, use_container_width=True, hide_index=True)
    st.caption(
        "Telifli kaynak (Sadiku) yalnızca bu makinede işlenir, paylaşılmaz — bkz. docs/kaynaklar.md."
    )


SCREENS = {
    "📖 Konu Anlatımı": screen_konu_anlatimi,
    "📝 Quiz": screen_quiz,
    "📚 Kaynaklar": screen_kaynaklar,
    "💡 İpucu Modu": lambda: not_built(
        "💡 İpucu ve Değerlendirme Modu",
        "Öğrenci serbest cevap yazar; sistem doğru/kısmen doğru/yanlış diye değerlendirir ve "
        "cevabı doğrudan vermeden 3 kademeli ipucu verir.",
        "`app/hints/` modülü",
    ),
    "⚡ Devre Simülatörü": lambda: not_built(
        "⚡ Devre Simülatörü",
        "Kullanıcının elle devre kurup üzerinde oynayabildiği interaktif ekran; "
        "çözüm ngspice/PySpice ile deterministik olarak hesaplanır.",
        "simülasyon motoru + çizim arayüzü",
    ),
    "📷 Kendi Devreni Yükle": lambda: not_built(
        "📷 Kendi Devreni Yükle",
        "Kullanıcı devre fotoğrafı yükler; sistem devreyi okur ve 'böyle mi anladım?' onay "
        "adımıyla doğrulatır, sonra simülatöre aktarır.",
        "`app/vision/` görsel okuma + onay akışı (VLM'ler topolojiyi güvenilir okuyamıyor, "
        "bkz. docs/vlm-karsilastirma-sonuclari.md)",
    ),
}


with st.sidebar:
    st.markdown("## ⚡ Devre Analizi\n### Asistanı")
    choice = st.radio("Ekran", list(SCREENS), label_visibility="collapsed")
    st.divider()

SCREENS[choice]()

with st.sidebar:
    st.divider()
    st.caption("Ollama ve Chroma sunucusu çalışıyor olmalı.")
