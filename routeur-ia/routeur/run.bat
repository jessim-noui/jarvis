@echo off
chcp 65001 >nul
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"
if not defined JARVIS_SECRETS set "JARVIS_SECRETS=%~dp0..\..\secrets"
set "CLES=%JARVIS_SECRETS%\cles.env"
if not exist "%CLES%" set "CLES=cles.env"
if not exist "%CLES%" ( echo Fichier cles.env manquant. & pause & exit /b 1 )
REM eol=# : les commentaires sont ignores par for /f lui-meme (avant, un "->" dans un commentaire passe par echo creait des fichiers)
for /f "usebackq eol=# tokens=1,* delims==" %%a in ("%CLES%") do set "%%a=%%b"
REM Trouver le dossier Scripts du meme Python (ou est installe litellm.exe)
for /f "usebackq delims=" %%i in (`py -3 -c "import sysconfig;print(sysconfig.get_path('scripts'))"`) do set "SCRIPTS=%%i"
echo.
echo  Routeur d'IA sur http://localhost:4000
echo  (Ferme cette fenetre pour arreter le routeur.)
echo.
if exist "%SCRIPTS%\litellm.exe" (
  "%SCRIPTS%\litellm.exe" --config config.yaml --host 127.0.0.1 --port 4000
) else (
  echo litellm.exe introuvable dans %SCRIPTS%
  echo On tente via le module de secours...
  py -3 -m litellm.proxy.proxy_cli --config config.yaml --host 127.0.0.1 --port 4000
)
REM "cache" = lance sans fenetre par Jarvis : pas de pause (sinon un cmd cache reste ouvert pour rien)
if /i not "%~1"=="cache" pause
