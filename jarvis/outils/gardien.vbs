' Mission 13 : le gardien de la memoire, seul programme de Jarvis lance avec Windows (sans fenetre).
' Il ne demarre ni Ollama, ni Jarvis, ni le routeur. Le retirer : supprimer ce fichier du dossier Demarrage (shell:startup).
Set s = CreateObject("WScript.Shell")
s.Run """" & CreateObject("WScript.Shell").ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"" -3 """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\gardien_memoire.py""", 0, False
