# Devre Analizi Eğitim Asistanı

Devre Analizi 1 ve Devre Analizi 2 konularında, açık lisanslı ders kitaplarından beslenen, tamamen local çalışan (Ollama/LM Studio) bir RAG (Retrieval-Augmented Generation) eğitim asistanı.

## Durum

Uçtan uca çalışıyor: PDF → chunk + metadata → embedding/vektör index → soru-cevap → arayüz.

- 4 kitap işlendi (Fiore DC/AC, Sadiku 1-2), **2174 chunk** index'lendi.
- Türkçe soru sorulur, İngilizce kaynaklardan kaynak göstererek cevaplanır.
- Kaynakta olmayan soruda uydurmaz, "bu bilgiye ulaşamadım" der.
- Cevap süresi ~20-40 sn (bu donanımda: GTX 1650, 4 GB VRAM).
- Kalite regresyon seti: **22/22** (`scripts/evaluate_rag.py`).

Henüz yok: quiz, ipucu sistemi, devre görseli okuma, simülatör, FastAPI backend.

## Planlanan Özellikler

- Konu anlatımı (kaynaklı, seviyeye uygun)
- Basitten zora örnek üretimi
- 5 soruluk quiz oluşturma
- Öğrenci cevabını değerlendirme
- Kademeli ipucu sistemi (3 seviye)
- Kaynak gösterme (kitap, bölüm, sayfa)

## Kısıtlar

- Fine-tuning yok.
- Harici/ücretli LLM API yok — yalnızca local LLM (Ollama veya LM Studio).
- Ana model 4B-20B parametre aralığında.

## Kurulum

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

Ollama kurulu olmalı (ollama.com/download) ve şu modeller çekilmeli:

```bat
ollama pull gemma4:e4b          :: cevap üretimi
ollama pull qwen2.5:3b-instruct :: hızlı kademe
ollama pull bge-m3              :: embedding (çok dilli)
```

## Çalıştırma

**Kolay yol:** `baslat.bat` dosyasına çift tıklayın. Gerekli üç servisi
(Ollama, Chroma, arayüz) açar — zaten çalışanları tekrar başlatmaz — ve
tarayıcıda http://localhost:8501 adresini açar.

> Masaüstüne kısayol: `baslat.bat` üzerine sağ tık → **Kısayol oluştur**,
> kısayolu masaüstüne taşıyın. Başlat menüsüne sabitlemek için kısayola
> sağ tık → **Başlangıç ekranına sabitle**.

### Elle çalıştırma

İki arka plan servisi (ayrı terminallerde, açık kalmalı):

```bat
ollama serve
.venv\Scripts\chroma run --path data\indexes\chroma --port 8123
```

Veriyi hazırla (bir kez):

```bat
.venv\Scripts\python scripts\download_books.py            :: açık kitaplar
.venv\Scripts\python scripts\parse_books.py --book fiore_dc
.venv\Scripts\python scripts\chunk_books.py --book fiore_dc
.venv\Scripts\python scripts\build_index.py --all
```

Arayüz:

```bat
.venv\Scripts\streamlit run app\ui\streamlit_app.py
```

→ http://localhost:8501 (yalnızca bu makineden erişilebilir)

Komut satırından tek soru: `.venv\Scripts\python scripts\ask.py "Kirchhoff akım yasası nedir?"`

Mimari ve tasarım kararları: `docs/architecture.md`, `docs/vision.md`.
Telifli Sadiku PDF'leri repoda yoktur; `--path` ile kendi kopyanızı verirsiniz.
