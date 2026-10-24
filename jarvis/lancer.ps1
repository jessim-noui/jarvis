# Lanceur unique de Jarvis, appelé SEULEMENT par JARVIS.bat (clic de l’utilisateur). Mission 11 : plus aucun lancement au démarrage de Windows.
# Mission 14 (démarrage rapide) : le serveur Jarvis d'abord (0,4 s) et la page tout de suite ; le routeur LiteLLM ensuite, en arrière-plan
# (avant, la page attendait jusqu'à 90 s le routeur). Le voyant du site dit « Routeur en démarrage » puis « IA disponible ».
# Un 2e clic pendant un lancement ne lance rien en double (verrou du lanceur) ; un serveur gelé est reconnu grâce à son verrou
# d'instance (donnees\serveur.lock : pid + heure de lancement) ; un verrou dont le programme n'existe plus (plantage) est ignoré.
# Ollama n'est PAS lancé ici : Jarvis l'allume quand une tâche locale en a besoin et l'arrête ensuite. Site fermé 10 min = tout s'arrête.
$ErrorActionPreference = 'SilentlyContinue'
$IA = Split-Path $PSScriptRoot -Parent
$pyw = (Get-Command pyw.exe).Source
$verrou = "$IA\jarvis\donnees\serveur.lock"

function Repond($url, $secondes = 1) {
  try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec $secondes | Out-Null; return $true } catch { return $false }
}
function Attendre($url, $secondes) {
  $chrono = [Diagnostics.Stopwatch]::StartNew()   # durée réelle : un essai raté peut lui-même prendre du temps
  while ($chrono.Elapsed.TotalSeconds -lt $secondes) { if (Repond $url) { return $true }; Start-Sleep 1 }
  return $false
}

# 0. Un 2e clic pendant qu'un lancement est en cours : on ouvre seulement la page
$lanceur = New-Object Threading.Mutex($false, 'Local\JarvisLanceur')
if (-not $lanceur.WaitOne(0)) {
  if (Attendre 'http://127.0.0.1:4100/ping' 40) { Start-Process 'http://127.0.0.1:4100/accueil.html' }
  exit
}

# Le bouton « Relancer Jarvis » du site (lien jarvis-relance:) lance CE fichier, rien d'autre (aucun argument n'est utilisé).
$cle = 'HKCU:\Software\Classes\jarvis-relance'
if (-not (Test-Path "$cle\shell\open\command")) {
  New-Item -Path "$cle\shell\open\command" -Force | Out-Null
  Set-ItemProperty -Path $cle -Name '(default)' -Value 'URL:Relancer Jarvis'
  Set-ItemProperty -Path $cle -Name 'URL Protocol' -Value ''
  Set-ItemProperty -Path "$cle\shell\open\command" -Name '(default)' -Value "`"$env:WINDIR\System32\cmd.exe`" /c `"$IA\JARVIS.bat`""
}

# 1. Serveur Jarvis + bot Telegram (pyw = sans console). Muet 3 s : en démarrage (< 60 s) on attend, sinon il est gelé → arrêté.
if (-not (Repond 'http://127.0.0.1:4100/ping' 3)) {
  $v = Get-Content $verrou -Raw | ConvertFrom-Json
  $p = $null
  if ($v) { $p = Get-Process -Id $v.pid | Where-Object { $_.ProcessName -like 'python*' } }
  if ($p -and ([DateTimeOffset]::Now.ToUnixTimeSeconds() - [double]$v.debut) -lt 60) { Attendre 'http://127.0.0.1:4100/ping' 40 | Out-Null }
  elseif ($p) { Stop-Process -Id $v.pid -Force; Start-Sleep 1 }
  if (-not (Repond 'http://127.0.0.1:4100/ping')) {
    Start-Process -FilePath $pyw -ArgumentList '-3', 'serveur.py' -WorkingDirectory "$IA\jarvis"
    Attendre 'http://127.0.0.1:4100/ping' 40 | Out-Null
  }
}

# 2. Une seule page, tout de suite : l'accueil, avec Jarvis au milieu
if (Repond 'http://127.0.0.1:4100/ping') { Start-Process 'http://127.0.0.1:4100/accueil.html' }
else { Start-Process "$IA\routeur-ia\site\accueil.html" }   # serveur absent : la page dit clairement ce qui manque

# 3. Routeur LiteLLM en arrière-plan (run.bat dans une console cachée), seulement s'il ne tourne pas et ne démarre pas déjà
$litellm = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'litellm' }
if (-not (Repond 'http://127.0.0.1:4000/health/liveliness') -and -not $litellm) {
  Start-Process -FilePath "$env:WINDIR\System32\cmd.exe" -ArgumentList '/c', "`"$IA\routeur-ia\routeur\run.bat`"", 'cache' -WorkingDirectory "$IA\routeur-ia\routeur" -WindowStyle Hidden
  Attendre 'http://127.0.0.1:4000/health/liveliness' 120 | Out-Null   # le verrou du lanceur reste pris pendant ce temps
}
$lanceur.ReleaseMutex()
