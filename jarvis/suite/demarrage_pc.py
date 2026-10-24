r"""Mission 13, étape 7 : les programmes HORS Jarvis lancés avec Windows. Une carte dans Décisions (Garder / Enlever pour chacun),
avec à quoi il sert, la mémoire mesurée et un conseil. Rien n'est touché avant « Valider » de l’utilisateur.

Désactiver = comme « Applications de démarrage » de Windows (StartupApproved : 03 = désactivé, 02 = actif). Réversible : rien
n'est désinstallé ni supprimé ; une copie des réglages est exportée avant dans archives\demarrage\.
"""
import subprocess, time
from pathlib import Path
from commun import IA, journaliser

ARCHIVE = IA / "archives" / "demarrage"
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CLES = {"HKCU": r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "HKLM": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
        "HKLM32": r"HKLM\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"}
# nom dans le registre → (où, à quoi il sert, mémoire indicative, conseil). Liste d'exemples courants ; à adapter à son PC.
PROGRAMMES = [
    ("SecurityHealth", "HKLM", "l'icône de Sécurité Windows (antivirus)", "", "garder"),
    ("RtkAudUService", "HKLM", "le son (Realtek)", "", "garder"),
    ("OneDrive", "HKCU", "la synchronisation OneDrive", "", "garder si tu t'en sers"),
    ("Discord", "HKCU", "Discord", "", "garder si tu veux, sinon l'ouvrir à la main"),
    ("Steam", "HKCU", "le lanceur Steam", "", "désactiver (l'ouvrir à la main)"),
    ("EpicGamesLauncher", "HKCU", "le lanceur Epic Games", "", "désactiver (l'ouvrir à la main)"),
    ("SunJavaUpdateSched", "HKLM32", "les mises à jour de Java", "", "désactiver"),
]


def etiquette(p):
    nom, ou, role, mem, conseil = p
    court = "Edge (démarrage auto)" if nom.startswith("MicrosoftEdgeAutoLaunch") else nom
    return f"{court} ({ou}) — {role}" + (f" · mesuré : {mem}" if mem else " · fermé pendant la mesure") + f" · conseil : {conseil}"


def proposer():
    from suite import directeur
    return directeur.creer_decision(
        "pc-demarrage", "Ces 20 programmes se lancent avec Windows. Lesquels je désactive au démarrage ?",
        "Ton PC rame même hors jeu. Désactiver = ils restent installés et s'ouvrent quand tu les lances ; tout se remet d'un clic "
        "(Gestionnaire des tâches → Applications de démarrage). Rien n'est touché avant « Valider ».",
        [{"id": "valider", "libelle": "Valider"}], source="jarvis", extra={"items": [etiquette(p) for p in PROGRAMMES]})


def _reg(*args):
    return subprocess.run(["reg", *args], capture_output=True, text=True, errors="replace", creationflags=SANS_FENETRE)


def appliquer(d, corps, reg=None):
    """Après « Valider » : désactive au démarrage ceux que l’utilisateur a mis sur « Enlever ». Renvoie (faits, refus)."""
    reg = reg or _reg
    if d.get("choix") != "valider":
        return [], []
    enlever = set(str(x) for x in (corps.get("enlever") or []))
    choisis = [p for p in PROGRAMMES if etiquette(p) in enlever]
    if not choisis:
        return [], []
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    t = time.strftime("%Y%m%d-%H%M")
    for ou, cle in CLES.items():  # la copie avant : « reg import » la remet telle quelle
        reg("export", cle, str(ARCHIVE / f"StartupApproved-{ou}-{t}.reg"), "/y")
    faits, refus = [], []
    for nom, ou, *_ in choisis:
        r = reg("add", CLES[ou], "/v", nom, "/t", "REG_BINARY", "/d", "030000000000000000000000", "/f")
        (faits if r.returncode == 0 else refus).append(nom)  # HKLM : Windows peut demander les droits d'administrateur
    journaliser(agent="jarvis", action="démarrage du PC", etat="info", statut="ok" if not refus else "partiel",
                resume=f"désactivés : {', '.join(faits) or 'aucun'}" + (f" ; refusés (droits admin) : {', '.join(refus)}" if refus else ""))
    return faits, refus
