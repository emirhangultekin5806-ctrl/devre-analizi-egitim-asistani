"""Streamlit arayüzü — soru sor, kaynaklı cevabı ve ara adımları gör.

Çalıştırma:
    .venv\\Scripts\\streamlit run app/ui/streamlit_app.py

Önkoşullar (ikisi de ayrı servis olarak çalışıyor olmalı):
    ollama serve
    chroma run --path data/indexes/chroma --port 8123

Bu ilk sürüm bilinçli olarak sade: tek ekran, soru + cevap + "ne oldu"
paneli. Amaç, boru hattının her adımının (hangi chunk'lar getirildi, hangi
cümleler seçildi, hangi adım kaç saniye sürdü) görünür olması —
docs/vision.md'deki "getirilen kaynakları şeffaf gösterme" hedefi.
"""

import sys
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.rag.generate import TASK_TIERS, TIERS, answer_question  # noqa: E402

NAVY = "#0d2149"
NAVY_LIGHT = "#1c3a6e"
ACCENT = "#2f6fb8"

st.set_page_config(page_title="Devre Analizi Asistanı", page_icon="⚡", layout="wide")

st.markdown(
    f"""
    <style>
      .stApp {{ background: #ffffff; }}
      h1, h2, h3 {{ color: {NAVY}; }}
      .da-header {{
        background: {NAVY}; color: #ffffff; padding: 1.1rem 1.4rem;
        border-radius: 10px; margin-bottom: 1.2rem;
      }}
      .da-header p {{ margin: .3rem 0 0; color: #c9d8ef; font-size: .9rem; }}
      .da-answer {{
        background: #f5f8fd; border-left: 5px solid {ACCENT};
        padding: 1.1rem 1.3rem; border-radius: 8px; font-size: 1.05rem;
        line-height: 1.65; color: #16213d;
      }}
      .da-chip {{
        display: inline-block; background: {NAVY_LIGHT}; color: #fff;
        padding: .18rem .6rem; border-radius: 999px; font-size: .75rem;
        margin-right: .35rem;
      }}
      .da-src {{
        border: 1px solid #dbe4f2; border-radius: 8px; padding: .7rem .9rem;
        margin-bottom: .6rem; background: #fafcff;
      }}
      .da-src-title {{ color: {NAVY}; font-weight: 600; font-size: .92rem; }}
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

st.markdown(
    """
    <div class="da-header">
      <h1 style="color:#fff;margin:0;font-size:1.6rem;">⚡ Devre Analizi Asistanı</h1>
      <p>Sorularınız yalnızca seçilen ders kitaplarından yanıtlanır — kaynakta yoksa uydurulmaz.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### Ayarlar")
    task = st.selectbox(
        "Görev",
        list(TASK_TIERS),
        index=list(TASK_TIERS).index("chat"),
        help="Kademe göreve göre otomatik seçilir.",
    )
    st.caption(f"Otomatik kademe: **{TASK_TIERS[task]}**")

    override = st.checkbox("Kademeyi elle seç (gelişmiş)")
    tier = st.selectbox("Kademe", list(TIERS), disabled=not override) if override else None

    top_k = st.slider("Getirilecek kaynak sayısı", 3, 10, 5)

    st.divider()
    st.caption("Ollama ve Chroma sunucusu çalışıyor olmalı.")

question = st.text_input(
    "Sorunuz",
    placeholder="örn. Kirchhoff akım yasası nedir?",
    label_visibility="collapsed",
)
ask = st.button("Sor")

if ask and question.strip():
    started = time.perf_counter()
    with st.spinner("Kaynaklar taranıyor ve cevap hazırlanıyor…"):
        try:
            result = answer_question(
                question.strip(), top_k=top_k, tier=tier if override else None, task=task
            )
        # Arayüzün en dış sınırı: hangi hata olursa olsun çökmek yerine
        # kullanıcıya ne yapması gerektiğini söylemeli (servis kapalı,
        # index yok, model indirilmemiş vb. hepsi buraya düşer).
        except Exception as exc:  # noqa: BLE001
            st.error(
                f"İstek başarısız: {type(exc).__name__} — {exc}\n\n"
                "Ollama (`ollama serve`) ve Chroma "
                "(`chroma run --path data/indexes/chroma --port 8123`) çalışıyor mu?"
            )
            st.stop()

    elapsed = time.perf_counter() - started

    st.markdown("#### Cevap")
    st.markdown(f'<div class="da-answer">{result["answer"]}</div>', unsafe_allow_html=True)

    tier_cfg = result["tier"]
    st.markdown(
        f'<div style="margin-top:.7rem;">'
        f'<span class="da-chip">{tier_cfg["model"]}</span>'
        f'<span class="da-chip">düşünme: {tier_cfg["think"]}</span>'
        f'<span class="da-chip">{elapsed:.1f} sn</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    st.markdown("#### Kullanılan kaynaklar")
    for i, src in enumerate(result["sources"], start=1):
        page = f" · s.{src['printed_page']}" if src.get("printed_page") else ""
        section = f" · {src['section_number']}" if src.get("section_number") else ""
        st.markdown(
            f'<div class="da-src">'
            f'<div class="da-src-title">{i}. {src["book_title"]}</div>'
            f'<div class="da-src-meta">Bölüm {src["chapter_number"]} — '
            f"{src['chapter_title']}{section}{page} · {src.get('content_type', '')} · "
            f"yakınlık {1 - src['distance']:.2f}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

    with st.expander("Ne oldu? (adım adım)"):
        t = result["timings"]
        c1, c2, c3 = st.columns(3)
        c1.metric("Kaynak arama", f"{t['retrieval']:.1f} sn")
        c2.metric("Cümle seçimi", f"{t['selection']:.1f} sn")
        c3.metric("Çeviri", f"{t['translation']:.1f} sn")

        st.caption(
            f"{result['candidate_sentence_count']} aday cümleden "
            f"{len(result['selected_sentences'])} tanesi seçildi. "
            "Model metin üretmez, yalnızca gerçek cümleleri seçer — bu yüzden uydurma yapamaz."
        )
        for sentence in result["selected_sentences"]:
            st.markdown(f"- {sentence}")

        st.caption("Kaynak metinlerin tamamı:")
        for i, src in enumerate(result["sources"], start=1):
            with st.expander(f"{i}. {src['chunk_id']}"):
                st.text(src["text"])
