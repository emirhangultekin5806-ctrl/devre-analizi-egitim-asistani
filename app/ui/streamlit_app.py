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

import base64
import sys
import tempfile
import time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from app.circuit.ac import solve_ac  # noqa: E402
from app.circuit.solve import (  # noqa: E402
    SolverError,
    element_results,
    power_balance,
    solve_dc,
)
from app.hints.generate import (  # noqa: E402
    MAX_HINT_LEVEL,
    evaluate_answer,
    generate_hint,
    generate_question,
)
from app.quiz.generate import generate_quiz  # noqa: E402
from app.rag.generate import (  # noqa: E402
    CONCEPT_CONTENT_TYPES,
    TASK_TIERS,
    TIERS,
    answer_question,
)
from app.vision.pipeline_bridge import PipelineBridgeError, extract_circuit  # noqa: E402
from app.vision.vlm_read import (  # noqa: E402
    READABLE_KINDS,
    VLMReadError,
    draft_to_netlist,
    read_circuit_image,
)
from scripts.solve_from_extraction import SolveFromExtractionError, solve_extraction  # noqa: E402

EXAMPLE_CONTENT_TYPES = ["example", "practice_problem"]
CHUNKS_DIR = ROOT / "data" / "chunks"

NAVY = "#0d2149"
NAVY_LIGHT = "#1c3a6e"
ACCENT = "#2f6fb8"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


@st.cache_data
def hero_texture() -> str:
    """Başlık şeridinin arka planı: yatayda kusursuz döşenen devre dokusu.

    Yerel dosya CSS'ten okunamadığı için data URI olarak gömülür (~10 KB).
    """
    raw = base64.b64encode((ASSETS_DIR / "hero_circuit.webp").read_bytes()).decode()
    return f"data:image/webp;base64,{raw}"


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
      @keyframes da-drift {{
        from {{ background-position: 0 center; }}
        to   {{ background-position: -848px center; }}
      }}
      .da-title {{
        position: relative; overflow: hidden;
        background: {NAVY} url("{hero_texture()}") repeat-x;
        background-size: 848px 180px;
        animation: da-drift 120s linear infinite;
        color: #fff; padding: .9rem 1.2rem;
        border-radius: 10px; margin-bottom: 1.1rem;
      }}
      /* Devre dokusunun üstüne yazıyı okunur tutan lacivert perde. */
      .da-title::after {{
        content: ""; position: absolute; inset: 0;
        background: linear-gradient(90deg, {NAVY} 0%, rgba(13, 33, 73, .86) 40%,
                                    rgba(13, 33, 73, .58) 100%);
      }}
      .da-title > * {{ position: relative; z-index: 1; }}
      @media (prefers-reduced-motion: reduce) {{
        .da-title {{ animation: none; }}
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


_VERDICT_LABELS = {
    "dogru": ("✅ Doğru", st.success),
    "kismen_dogru": ("🟡 Kısmen doğru", st.warning),
    "yanlis": ("❌ Yanlış", st.error),
    "yetersiz": ("ℹ️ Yetersiz", st.info),
}


def screen_ipucu() -> None:
    header(
        "💡 İpucu ve Değerlendirme Modu",
        "Serbest cevap yaz; sistem doğru/kısmen doğru/yanlış/yetersiz diye değerlendirir, "
        "tam doğru değilse cevabı vermeden kademeli ipucu verir.",
    )

    with st.sidebar:
        st.markdown("### Ayarlar")
        top_k = st.slider("Getirilecek kaynak sayısı", 3, 10, 5)
        st.caption("İpucu modu `fast` kademesini kullanır (hızlı geri bildirim önceliği).")

    topic = st.text_input("Konu", placeholder="örn. Kirchhoff akım yasası")
    if st.button("Soru oluştur") and topic.strip():
        with st.spinner("Soru hazırlanıyor…"):
            try:
                question_data = generate_question(topic.strip(), top_k=top_k)
            except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                service_error(exc)
                return
        # Yeni soru = yeni oturum: önceki cevap/değerlendirme/ipucu sıfırlanır.
        st.session_state.hint_session = {
            "question_data": question_data,
            "evaluation": None,
            "hint_level": 0,
            "hints_shown": [],
        }

    session = st.session_state.get("hint_session")
    if not session:
        return
    question_data = session["question_data"]
    if not question_data["question"]:
        st.warning("Model bu konu için geçerli biçimde soru üretemedi. Konuyu biraz daha belirgin yazıp tekrar deneyin.")
        return

    st.markdown(f"#### Soru\n{question_data['question']}")
    student_answer = st.text_area("Cevabınız", key="hint_student_answer", height=120)

    if st.button("Cevabı gönder") and student_answer.strip():
        with st.spinner("Değerlendiriliyor…"):
            try:
                session["evaluation"] = evaluate_answer(
                    question_data["question"], question_data["source_sentences"], student_answer.strip()
                )
            except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                service_error(exc)
                return
        session["hint_level"] = 0
        session["hints_shown"] = []
        session["last_answer"] = student_answer.strip()

    evaluation = session.get("evaluation")
    if evaluation:
        label, renderer = _VERDICT_LABELS[evaluation["degerlendirme"]]
        renderer(f"**{label}** — {evaluation['aciklama']}")

        if evaluation["degerlendirme"] != "dogru":
            if session["hint_level"] < MAX_HINT_LEVEL:
                if st.button(f"İpucu iste (seviye {session['hint_level'] + 1}/{MAX_HINT_LEVEL})"):
                    with st.spinner("İpucu hazırlanıyor…"):
                        try:
                            hint = generate_hint(
                                question_data["question"],
                                question_data["source_sentences"],
                                session.get("last_answer", student_answer.strip()),
                                hint_level=session["hint_level"] + 1,
                            )
                        except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                            service_error(exc)
                            return
                    session["hint_level"] += 1
                    session["hints_shown"].append(hint)
            else:
                st.caption("Tüm ipucu seviyeleri gösterildi.")

        for i, hint in enumerate(session["hints_shown"], start=1):
            st.info(f"**İpucu {i}:** {hint}")

    render_sources(question_data["sources"])


def _render_dc_results(netlist, solution) -> None:
    results = element_results(netlist, solution)
    residual = power_balance(results)
    st.markdown("#### Sonuçlar")
    rows = [
        {
            "Eleman": r.name, "Tür": r.kind,
            "I (A)": round(r.current, 4), "V (V)": round(r.voltage, 4), "P (W)": round(r.power, 4),
        }
        for r in results.values()
    ]
    st.dataframe(rows, width="stretch", hide_index=True)
    total = sum(abs(r.power) for r in results.values()) or 1.0
    ok = abs(residual) / total < 1e-6
    st.caption(f"Güç dengesi (Tellegen): {residual:.2e} W → {'tutarlı ✅' if ok else 'TUTARSIZ ⚠️'}")


def _render_ac_results(solution) -> None:
    st.markdown("#### Sonuçlar (fazör)")
    rows = []
    for node in sorted(solution.node_voltages):
        magnitude, angle = solution.polar(solution.node_voltages[node])
        rows.append({"Düğüm": node, "|V| (V)": round(magnitude, 4), "∠ (°)": round(angle, 2)})
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_pipeline_results(out: dict) -> None:
    """`scripts.solve_from_extraction.solve_extraction`'un ciktisini gosterir.

    Iki farkli sekil dondurebilir (bkz. o fonksiyon): normal eleman sonuclari
    (DC ElementResult / AC ACElementResult -- ikisi de .describe() ile ayni
    arayuzu paylasir, DC/AC ayrimini burada TEKRAR yazmamak icin CLI'daki
    gibi dogrudan kullanilir) ya da kaynaksiz devrede tek bir Rₑq sayisi.
    """
    st.markdown("#### Sonuçlar")
    results = out["results"]
    if "esdeger_direnc_ohm" in results:
        a, b = results["terminals"]
        st.metric(f"R_eşdeğer ({a}–{b})", f"{results['esdeger_direnc_ohm']:.4g} Ω")
        return
    for r in results.values():
        st.text(r.describe())
    st.caption(f"Güç dengesi (Tellegen, 0 olmalı): {out['power_balance']!s}")


def screen_kendi_devren() -> None:
    header(
        "📷 Kendi Devreni Yükle",
        "Kendi devre görselini yükle; sistem okumaya çalışır, sen onaylar/düzeltirsin, sonra çözülür.",
    )

    uploaded = st.file_uploader("Devre görseli (PDF'ten kırpma da olur)", type=["png", "jpg", "jpeg"])

    col1, col2, col3 = st.columns(3)
    with col1:
        pipeline_clicked = st.button(
            "🔍 Pipeline ile oku (önerilen)", disabled=uploaded is None,
            help="YOLO ile bileşen/bağlantı tespiti + OCR/VLM ile değer okuma -- topoloji halüsinasyon riski taşımaz.",
        )
    with col2:
        read_clicked = st.button(
            "VLM ile oku (deneysel)", disabled=uploaded is None,
            help="Bütün görüntüyü tek seferde VLM'e verir -- topolojide halüsinasyon görülebilir, bkz. uyarı.",
        )
    with col3:
        manual_clicked = st.button("Elle gir")

    if pipeline_clicked and uploaded is not None:
        # Kirpma/scratch dosyalari kalici -- solve_extraction daha sonra
        # (kullanici "Coz" butonuna basinca) bu yoldaki crop'lari VLM'e
        # gonderecek, o yuzden burada SILINMEZ (bkz. modul yorumu asagida).
        tmp_dir = Path(tempfile.mkdtemp(prefix="own_circuit_"))
        image_path = tmp_dir / f"upload{Path(uploaded.name).suffix or '.png'}"
        image_path.write_bytes(uploaded.getvalue())
        with st.spinner("YOLO + connectivity + OCR ile işleniyor…"):
            try:
                extraction = extract_circuit(image_path, tmp_dir / "extract")
            except PipelineBridgeError as exc:
                st.error(f"İşlenemedi: {exc}")
                return
            except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                service_error(exc)
                return
        st.session_state.own_pipeline_extraction = extraction
        st.session_state.own_circuit = None

    if read_clicked and uploaded is not None:
        st.warning(
            "VLM devre okuması özellikle kaynak polaritesinde (+/- ucu) güvenilir değil "
            "(bkz. `docs/vlm-karsilastirma-sonuclari.md`) — aşağıdaki tabloyu görselle "
            "karşılaştırıp MUTLAKA kontrol et, çözmeden önce."
        )
        image_b64 = base64.b64encode(uploaded.getvalue()).decode("ascii")
        with st.spinner("Görsel okunuyor (VLM birkaç dakika sürebilir)…"):
            try:
                draft = read_circuit_image(image_b64)
            except VLMReadError as exc:
                st.error(f"Okuma başarısız: {exc}")
                if exc.raw:
                    with st.expander("VLM'in ham yanıtı"):
                        st.text(exc.raw)
                return
            except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                service_error(exc)
                return
        st.session_state.own_circuit = {"rows": draft["elements"], "frequency_hz": draft["frequency_hz"]}
        st.session_state.own_pipeline_extraction = None
        if draft["notlar"]:
            st.info(f"VLM notu: {draft['notlar']}")

    if manual_clicked:
        st.session_state.own_circuit = {"rows": [], "frequency_hz": None}
        st.session_state.own_pipeline_extraction = None

    extraction = st.session_state.get("own_pipeline_extraction")
    if extraction:
        st.markdown("#### Tespit edilen bileşenler (YOLO + connectivity)")
        comp_rows = [
            {"Ad": name, "Tür": c["kind"], "Netler": c["nets"]}
            for name, c in extraction["components"].items()
        ]
        st.dataframe(comp_rows, width="stretch", hide_index=True)
        for w in extraction.get("warnings", []):
            st.warning(w)

        reference = st.text_input(
            "Referans (toprak) düğüm adı — şemada toprak sembolü YOKSA gerekli (örn. n0)",
            key="own_pipeline_reference",
        ).strip() or None
        if st.button("Çöz (pipeline)"):
            with st.spinner("Değerler okunuyor ve çözülüyor (VLM birkaç dakika sürebilir)…"):
                try:
                    out = solve_extraction(extraction, reference=reference, verbose=False)
                except SolveFromExtractionError as exc:
                    st.error(f"Çözülemedi: {exc}")
                    return
                except Exception as exc:  # noqa: BLE001 - arayüz sınırı
                    service_error(exc)
                    return
            _render_pipeline_results(out)
        return

    session = st.session_state.get("own_circuit")
    if not session:
        return

    st.markdown("#### Devre elemanları (gerekirse düzelt)")
    st.caption(
        "Yönsüz elemanlarda (direnç/kapasitör/bobin) uç sırası önemsiz. Kaynaklarda "
        "düğüm A = + ucu, düğüm B = − ucu. Toprak varsa düğüm adı \"gnd\" olmalı. "
        "Bağımlı kaynaklar (VCVS/CCVS) bu tablodan desteklenmiyor."
    )
    edited = st.data_editor(
        session["rows"],
        num_rows="dynamic",
        width="stretch",
        column_config={
            "kind": st.column_config.SelectboxColumn("tür", options=sorted(READABLE_KINDS), required=True),
            "name": st.column_config.TextColumn("ad", required=True),
            "value": st.column_config.NumberColumn("değer"),
            "node_a": st.column_config.TextColumn("düğüm A (+ ise)", required=True),
            "node_b": st.column_config.TextColumn("düğüm B (− ise)", required=True),
            "phase_degrees": st.column_config.NumberColumn("faz (derece)"),
        },
        key="own_circuit_editor",
    )
    session["rows"] = edited

    needs_frequency = any((row.get("phase_degrees") or 0) != 0 for row in edited)
    frequency = session.get("frequency_hz")
    if needs_frequency:
        frequency = st.number_input(
            "Frekans (Hz) — bir kaynağın fazı 0 değil, AC çözüm gerekiyor",
            min_value=0.0, value=frequency or 60.0,
        )
        session["frequency_hz"] = frequency

    if st.button("Çöz") and edited:
        try:
            netlist = draft_to_netlist(edited)
        except (ValueError, TypeError) as exc:
            st.error(f"Devre geçersiz: {exc}")
            return

        try:
            if needs_frequency:
                if not frequency:
                    st.error("Frekans girilmeli.")
                    return
                solution = solve_ac(netlist, frequency)
                _render_ac_results(solution)
            else:
                reference = None if "gnd" in netlist.nodes() else min(netlist.nodes())
                if reference:
                    st.caption(f"Şekilde toprak yok; referans düğüm olarak {reference} seçildi.")
                solution = solve_dc(netlist, reference=reference)
                _render_dc_results(netlist, solution)
        except SolverError as exc:
            st.error(f"Çözülemedi: {exc}")


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
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "Telifli kaynak (Sadiku) yalnızca bu makinede işlenir, paylaşılmaz — bkz. docs/kaynaklar.md."
    )


SCREENS = {
    "📖 Konu Anlatımı": screen_konu_anlatimi,
    "📝 Quiz": screen_quiz,
    "📚 Kaynaklar": screen_kaynaklar,
    "💡 İpucu Modu": screen_ipucu,
    "⚡ Devre Simülatörü": lambda: not_built(
        "⚡ Devre Simülatörü",
        "Kullanıcının elle devre kurup üzerinde oynayabildiği interaktif ekran; "
        "çözüm ngspice/PySpice ile deterministik olarak hesaplanır.",
        "simülasyon motoru + çizim arayüzü",
    ),
    "📷 Kendi Devreni Yükle": screen_kendi_devren,
}


with st.sidebar:
    st.markdown("## ⚡ Devre Analizi\n### Asistanı")
    choice = st.radio("Ekran", list(SCREENS), label_visibility="collapsed")
    st.divider()

SCREENS[choice]()

with st.sidebar:
    st.divider()
    st.caption("Ollama ve Chroma sunucusu çalışıyor olmalı.")
