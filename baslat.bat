@echo off
REM Devre Analizi Asistani - tek tikla baslatici.
REM Gerekli uc servisi (Ollama, Chroma, Streamlit) acar ve tarayiciyi acar.
REM Zaten calisan bir servis varsa tekrar baslatilmaz.
setlocal
cd /d "%~dp0"

echo.
echo   Devre Analizi Asistani baslatiliyor...
echo.

REM --- Ollama (dil modelleri) ---
curl -s -o nul http://localhost:11434/api/version
if errorlevel 1 (
    echo   [1/3] Ollama baslatiliyor...
    start "Ollama" /min ollama serve
) else (
    echo   [1/3] Ollama zaten calisiyor.
)

REM --- Chroma (vektor veritabani) ---
REM Gomulu/dosya modu bu makinede index'i bozuyor, ayri sunucu sart.
curl -s -o nul http://localhost:8123/api/v2/heartbeat
if errorlevel 1 (
    echo   [2/3] Chroma baslatiliyor...
    start "Chroma" /min .venv\Scripts\chroma run --path data\indexes\chroma --port 8123
) else (
    echo   [2/3] Chroma zaten calisiyor.
)

REM --- Streamlit (arayuz) ---
curl -s -o nul http://localhost:8501
if errorlevel 1 (
    echo   [3/3] Arayuz baslatiliyor...
    start "Arayuz" /min .venv\Scripts\streamlit run app\ui\streamlit_app.py
) else (
    echo   [3/3] Arayuz zaten calisiyor.
)

echo.
echo   Servislerin hazir olmasi bekleniyor...

REM Arayuz cevap verene kadar bekle (en fazla ~60 sn)
set /a tries=0
:wait
ping -n 3 127.0.0.1 >nul
curl -s -o nul http://localhost:8501
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% lss 30 goto wait

echo.
echo   Arayuz baslatilamadi. Acilan pencerelerdeki hata mesajlarina bakin.
echo   (Sik neden: "pip install -r requirements.txt" calistirilmamis olmasi.)
pause
exit /b 1

:ready
echo   Hazir. Tarayici aciliyor: http://localhost:8501
start http://localhost:8501
ping -n 4 127.0.0.1 >nul
endlocal
