@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

cd /d "%~dp0"

echo ==========================================
echo Starting Second Brain Terminal & Web Interface...
echo ==========================================

REM Install dependencies once in virtual environment
if not exist ".venv" (
    echo Creating Python virtual environment...
    python -m venv ".venv"
)

call ".venv\Scripts\activate.bat"

if not exist ".installed" (
    echo Installing requirements...
    python -m pip install -r requirements.txt
    echo done > ".installed"
)

echo Launching Local LLM (llama-server)...
taskkill /f /im llama-server.exe >nul 2>&1
if exist "D:\llama4\llama-server.exe" (
    start "Llama Server" /MIN cmd /c "D:\llama4\llama-server.exe --port 8081 -hf unsloth/gemma-4-E4B-it-GGUF:UD-Q4_K_XL -c 131072 -ngl 999 > llama-server.log 2>&1"
)

timeout /t 3 /nobreak >nul

echo Starting Second Brain Runtime...
start http://localhost:8000
python main.py

endlocal
