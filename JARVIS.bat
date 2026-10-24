@echo off
rem Jarvis : la seule porte d entree (mission 13). Lance le routeur et Jarvis (avec Telegram), puis ouvre la page.
rem Ollama n est PAS lance ici : Jarvis l allume seulement quand tu es sur le site et que tu ne joues pas.
start "" /min powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0jarvis\lancer.ps1"
