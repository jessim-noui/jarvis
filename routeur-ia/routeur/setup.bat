@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   INSTALLATION DU ROUTEUR D'IA
echo   (a relancer une 2e fois si Python vient d'etre installe)
echo ============================================================
echo.

set FRESH=0

echo [1/4] Verification de Python...
where py >nul 2>nul
if errorlevel 1 (
  echo    Python absent : installation...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  set FRESH=1
) else ( echo    Python OK. )

echo [2/4] Verification d'Ollama...
where ollama >nul 2>nul
if errorlevel 1 (
  echo    Ollama absent : installation...
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
  set FRESH=1
) else ( echo    Ollama OK. )

if "%FRESH%"=="1" (
  echo.
  echo  =====================================================
  echo   Des logiciels viennent d'etre installes.
  echo   FERME cette fenetre et DOUBLE-CLIQUE de nouveau sur
  echo   setup.bat pour terminer l'installation.
  echo  =====================================================
  pause & exit /b 0
)

echo [3/4] Telechargement du modele local llama3.1:8b (~5 Go, patiente)...
ollama pull llama3.1:8b

echo [4/4] Installation de LiteLLM...
py -3 -m pip install --upgrade pip
py -3 -m pip install "litellm[proxy]"

echo.
echo ============================================================
echo   TERMINE. Double-clique sur run.bat pour demarrer.
echo ============================================================
pause
