---
name: run-devre-analizi
description: Launch and drive the Devre Analizi education assistant (RAG + circuit solver)
---

# Run Devre Analizi

This skill runs the circuit analysis education assistant: a local-LLM RAG system that answers questions from textbooks, reads circuit topologies from PDFs, and solves DC/AC circuits from user uploads.

The app is **Streamlit** (frontend) + **FastAPI** (backend) + **Ollama** (local LLMs) + **ChromaDB** (vector index) + **ngspice** (circuit solver). It runs at `http://127.0.0.1:8501`.

## Prerequisites

- **Python 3.10+**
- **Ollama** — local LLM inference (requires `ollama serve` running)
- **Node.js** — for dependencies verification (optional)

Models needed in Ollama (downloaded on first use):
- `gemma4:e4b` — main reasoning (requires think mode disabled)
- `qwen2.5:3b-instruct` — fast fallback
- `bge-m3` — embeddings
- `minicpm-v4.5:8b` — vision/circuit reading

## Build

```bat
cd c:\Users\Furkan\Desktop\IT\devre-analizi-egitim-asistani

# One-time environment setup
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# One-time ngspice installation (required for circuit solving)
.venv\Scripts\pyspice-post-installation --install-ngspice-dll

# One-time vector index build (if not already built)
.venv\Scripts\python scripts\build_index.py --all
```

## Run (Agent path)

Use the included driver to verify services are up before launching:

```bat
cd c:\Users\Furkan\Desktop\IT\devre-analizi-egitim-asistani

# Start background services (open separate terminals)
ollama serve

# In another terminal
.venv\Scripts\chroma run --path data\indexes\chroma --port 8123

# In third terminal, run the health check driver
bash .claude/skills/run-devre-analizi/driver.sh

# Once driver succeeds, launch the app (same terminal as Streamlit is fine)
.venv\Scripts\streamlit run app\ui\streamlit_app.py
```

The driver exits with status 0 when the app is ready. The app then runs on `http://127.0.0.1:8501`.

**Main screens:**
- **Soru Sor** (Ask a question) — RAG-based answers from textbooks
- **Topolojiyi Oku** (Read topology) — parse and solve circuits from PDF figures
- **Kendi Devren** (Your own circuit) — upload a photo, VLM reads it, solve it

## Run (Human path)

1. Open two terminals.
2. Terminal 1: `ollama serve`
3. Terminal 2: `.venv\Scripts\chroma run --path data\indexes\chroma --port 8123`
4. Terminal 3: `.venv\Scripts\streamlit run app\ui\streamlit_app.py`
5. Browser opens automatically to `http://127.0.0.1:8501`

Stop: `Ctrl+C` in the Streamlit terminal. Services keep running in background (stop with `Ctrl+C` in their terminals separately).

## Test

```bat
.venv\Scripts\python -m pytest tests/ -v
```

The test suite includes:
- RAG retrieval (22/22 textbook questions answered correctly)
- Circuit solving (DC/AC, three-phase, with Tellegen power balance checks)
- VLM circuit reading (element and value extraction)
- Figure topology reading from PDFs (deterministic, vector-based)

## Gotchas

1. **ngspice.dll is not installed by pip.** The PySpice package alone won't work. You must run `pyspice-post-installation --install-ngspice-dll` — it's a one-time step. Without it, all circuit-solving tests fail with "cannot load library ngspice.dll".

2. **ChromaDB binds to localhost:8123, not 0.0.0.0.** Must be started as a separate HTTP server (not embedded mode), because embedded mode has historically corrupted the index on this machine. Always use `chroma run --path data\indexes\chroma --port 8123`.

3. **Ollama takes time on first download.** The first question you ask will trigger model downloads if they're not cached. `gemma4:e4b` (~4.5 GB) takes a few minutes depending on network. Cached models respond in ~1-2 seconds.

4. **VLM circuit reading returns raw element dicts, not solved circuits.** The pipeline is VLM → parse → user edits → solve. If the VLM misreads topology (e.g., missing connections), the Streamlit `st.data_editor` form lets you fix it before solving.

5. **ngspice node names are case-insensitive, but the app normalizes to lowercase.** Node names in VLM output may be uppercase (e.g., "A", "B", "GND"); the solver converts them to lowercase to match ngspice's internal representation.

6. **Sympy may be slow on first symbolic solve.** The first DC circuit with dependent sources may take 5-10 seconds (Sympy sympy ics compilation). Cached solves are fast.

7. **PDF path for Sadiku textbook** — the bundled Sadiku PDF is detected via env var `SADIKU_PDF` (default: looks in standard location). If you move the PDF, set the env var before running.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "cannot load library ngspice.dll" | Run `.venv\Scripts\pyspice-post-installation --install-ngspice-dll` |
| Streamlit port already in use | Kill any other Streamlit processes, or use `--server.port 8502` |
| Chroma connection refused | Check that `chroma run` is actually running in its terminal (not exited) |
| "Models not found" when asking a question | Ollama is not running, or models haven't downloaded. Run `ollama pull gemma4:e4b` manually to pre-fetch. |
| RAG returns out-of-domain answers | Vector index may not be built. Run `scripts\build_index.py --all` and restart. |
| Figure topology reading says "no elements found" | The PDF may not be indexed, or the figure isn't on the selected page. Check the PDF path in Sadiku_pdf.py. |
| VLM circuit reading crashes on units ("1.9 mA") | Parsing bug — the VLM returns values with units, but the app expects plain numbers. Remove units before solving or submit as an issue. |
