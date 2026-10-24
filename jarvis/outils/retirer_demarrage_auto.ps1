# Mission 11 : Jarvis et Ollama ne démarrent plus avec Windows.
# Sauvegardes (pour remettre) : sauvegardes\demarrage-avant-m11\
#   tâche : Register-ScheduledTask -TaskName Jarvis-Veille -Xml (Get-Content ...\Jarvis-Veille.xml -Raw)
#   Ollama : recopier Ollama.lnk dans shell:startup
foreach ($nom in 'Jarvis-Demarrage', 'Jarvis-Veille') {
    if (Get-ScheduledTask -TaskName $nom -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $nom -Confirm:$false
        "Tâche $nom retirée"
    }
}
$lnk = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup\Ollama.lnk"
if (Test-Path $lnk) { Remove-Item $lnk; "Ollama ne démarre plus avec Windows" }
"Fini."
