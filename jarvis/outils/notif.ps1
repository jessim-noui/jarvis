# Petite notification Windows (toast natif, rien à installer). Usage : powershell -File notif.ps1 "Titre" "Texte"
param([string]$Titre = 'Jarvis', [string]$Texte = '')
$e = { param($s) [Security.SecurityElement]::Escape($s) }
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
$x = New-Object Windows.Data.Xml.Dom.XmlDocument
$x.LoadXml("<toast><visual><binding template=`"ToastGeneric`"><text>$(& $e $Titre)</text><text>$(& $e $Texte)</text></binding></visual></toast>")
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))
