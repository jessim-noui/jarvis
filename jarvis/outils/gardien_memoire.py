r"""Gardien de la mémoire (Mission 13) : protège le PC de l’utilisateur, même quand Jarvis est éteint et qu'il joue.

Tout petit : aucune IA, aucun Internet, aucune clé lue (n'importe PAS commun.py). Vérifie la mémoire toutes les 5 s.
  ≥ 80 %            → note ce qui prend la mémoire (donnees\gardien.json) et vide la mémoire d'Ollama s'il tourne.
  ≥ 90 % pendant 10 s → ferme Ollama, puis Jarvis (serveur, routeur, bot), notification Windows, et note avant/après.
Choix de l’utilisateur (20/10) : il ne ferme RIEN d'autre (ni le jeu, ni Chrome, ni Discord) ; il dit seulement qui prend la place.
Il sert aussi à Jarvis pour savoir si un jeu tourne (jeu_en_cours).

  pyw -3 outils\gardien_memoire.py            → surveille (une seule copie à la fois), sans fenêtre
  py -3 outils\gardien_memoire.py --etat      → mémoire, jeu détecté, dernières alertes (lecture seule)
"""
import collections, csv, ctypes, io, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

IA = Path(os.environ.get("JARVIS_IA", Path(__file__).resolve().parents[2]))
DONNEES = IA / "jarvis" / "donnees"
JOURNAL = DONNEES / "gardien.json"
VERROU = DONNEES / "gardien.pid"
REGLAGES = IA / "jarvis" / "suite" / "reglages.json"
OLLAMA = "http://127.0.0.1:11434"
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
Go = 1024 ** 3

ANALYSE, CRITIQUE, DUREE_CRITIQUE, PAUSE = 80, 90, 10, 5
PROCESSUS_OLLAMA = ("ollama app.exe", "ollama.exe")
# Seulement ces programmes de Jarvis (pas mcp_jarvis.py de Claude Code, pas les tests, pas un autre Python) :
CIBLES_JARVIS = re.compile(r"serveur\.py|suivi_candidatures|analyser_offres|tout_chercher|veille\.py|litellm|routeur\\run\.bat", re.I)
# Jeux connus (le processus du JEU, pas le lanceur : Steam ou Epic restent ouverts en fond sans qu'on joue)
JEUX_CONNUS = {"cs2.exe", "valorant-win64-shipping.exe", "league of legends.exe", "fortniteclient-win64-shipping.exe",
               "gta5.exe", "gta5_enhanced.exe", "rocketleague.exe", "r5apex.exe", "overwatch.exe", "eldenring.exe",
               "minecraft.windows.exe", "fifa.exe", "fc25.exe", "fc26.exe", "rainbowsix.exe", "destiny2.exe",
               "cod.exe", "dota2.exe", "witcher3.exe", "cyberpunk2077.exe", "bg3.exe", "hogwartslegacy.exe"}


# ---------- Mesures (lecture seule) ----------

def memoire():
    """(total en Go, utilisée en %) ; None si inconnu."""
    if os.name == "nt":
        class M(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("charge", ctypes.c_ulong)] + [(c, ctypes.c_ulonglong) for c in "tfabcde"]
        m = M()
        m.l = ctypes.sizeof(M)
        return (m.t / Go, m.charge) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)) else None
    try:
        info = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines()}
        return info["MemTotal"] / Go, round(100 * (1 - info["MemAvailable"] / info["MemTotal"]))
    except (OSError, KeyError, ValueError):
        return None


def lire_tasklist(sortie):
    """Sortie CSV de « tasklist /FO CSV /NH » → [(nom, Go)] additionnés par nom, du plus gros au plus petit."""
    total = collections.Counter()
    for ligne in csv.reader(io.StringIO(sortie)):
        if len(ligne) >= 5:
            ko = "".join(c for c in ligne[4] if c.isdigit())
            if ko:
                total[ligne[0]] += int(ko) * 1024 / Go
    return total.most_common()


def programmes():
    if os.name != "nt":
        return []
    try:
        return lire_tasklist(subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace",
                                            timeout=20, creationflags=SANS_FENETRE).stdout)
    except (OSError, subprocess.SubprocessError):
        return []


def _plein_ecran():
    """Vrai si la fenêtre au premier plan couvre tout son écran (jeu, vidéo plein écran), hors bureau Windows."""
    if os.name != "nt":
        return False
    try:
        u = ctypes.windll.user32
        h = u.GetForegroundWindow()
        if not h:
            return False
        classe = ctypes.create_unicode_buffer(64)
        u.GetClassNameW(h, classe, 64)
        if classe.value in ("Progman", "WorkerW", "Shell_TrayWnd"):
            return False

        class R(ctypes.Structure):
            _fields_ = [(c, ctypes.c_long) for c in ("g", "h", "d", "b")]

        class I(ctypes.Structure):
            _fields_ = [("taille", ctypes.c_ulong), ("ecran", R), ("travail", R), ("drap", ctypes.c_ulong)]
        f, i = R(), I()
        i.taille = ctypes.sizeof(I)
        u.GetWindowRect(h, ctypes.byref(f))
        if not u.GetMonitorInfoW(u.MonitorFromWindow(h, 2), ctypes.byref(i)):
            return False
        e = i.ecran
        return f.g <= e.g and f.h <= e.h and f.d >= e.d and f.b >= e.b
    except (AttributeError, OSError):
        return False


def _carte_graphique_occupee(seuil=60):
    if not shutil.which("nvidia-smi"):
        return False
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, creationflags=SANS_FENETRE)
        return any(int(x) >= seuil for x in r.stdout.split())
    except (OSError, subprocess.SubprocessError, ValueError):
        return False


def memoire_carte():
    """« utilisée/totale Go » de la carte graphique (nvidia-smi), "" si inconnue. Lu seulement quand le gardien note une alerte."""
    if not shutil.which("nvidia-smi"):
        return ""
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, creationflags=SANS_FENETRE)
        u, tot = [int(x) for x in r.stdout.splitlines()[0].split(",")]
        return f"{u / 1024:.1f}/{tot / 1024:.0f} Go"
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return ""


def jeux_perso():
    try:
        return {n.lower() for n in json.loads(REGLAGES.read_text(encoding="utf-8")).get("jeux", [])}
    except (OSError, ValueError, AttributeError):
        return set()


def jeu_en_cours(noms=None):
    """La raison si un jeu tourne (sinon "") : un jeu connu ou ajouté par l’utilisateur, une fenêtre plein écran,
    ou la carte graphique très occupée hors Ollama."""
    noms = {n.lower() for n, _ in programmes()} if noms is None else {n.lower() for n in noms}
    trouve = sorted(noms & (JEUX_CONNUS | jeux_perso()))
    if trouve:
        return "jeu : " + trouve[0]
    if _plein_ecran():
        return "application en plein écran"
    if _carte_graphique_occupee() and not (noms & set(PROCESSUS_OLLAMA)):
        return "carte graphique très occupée"
    return ""


# ---------- Actions (seulement Ollama et Jarvis) ----------

def _ollama(chemin, corps=None, timeout=5):
    req = urllib.request.Request(OLLAMA + chemin, data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def vider_ollama():
    """Ollama garde ses modèles mais les sort de la mémoire (keep_alive 0). Renvoie les noms libérés."""
    liberes = []
    try:
        for m in _ollama("/api/ps").get("models", []):
            _ollama("/api/generate", {"model": m["name"], "keep_alive": 0}, timeout=20)
            liberes.append(m["name"])
    except (OSError, KeyError, ValueError):
        pass
    return liberes


def _tuer(*args):
    if os.name == "nt":
        subprocess.run(["taskkill", *args, "/F"], capture_output=True, creationflags=SANS_FENETRE)


def fermer_ollama():
    for exe in PROCESSUS_OLLAMA:
        _tuer("/IM", exe)


def processus_jarvis():
    """PID des programmes de Jarvis (serveur, routeur, scripts d'offres et de mails), jamais Claude Code ni un autre Python."""
    if os.name != "nt":
        return []
    cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.Name -match '^(pythonw?|pyw?|litellm|cmd)\\.exe$' -and "
           f"$_.CommandLine -match '{CIBLES_JARVIS.pattern}' }} | ForEach-Object {{ \"$($_.ProcessId)|$($_.CommandLine)\" }}")
    try:
        sortie = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, errors="replace",
                                timeout=30, creationflags=SANS_FENETRE).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return choisir_jarvis(sortie, os.getpid())


def choisir_jarvis(sortie, moi):
    pids = []
    for ligne in sortie.splitlines():
        pid, _, commande = ligne.partition("|")
        if pid.strip().isdigit() and int(pid) != moi and "gardien_memoire" not in commande and CIBLES_JARVIS.search(commande):
            pids.append(int(pid))
    return pids


def fermer_jarvis():
    pids = processus_jarvis()
    for pid in pids:
        _tuer("/PID", str(pid), "/T")
    return len(pids)


def notifier(titre, texte):
    script = IA / "jarvis" / "outils" / "notif.ps1"
    if os.name == "nt" and script.exists():
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), titre, texte],
                         creationflags=SANS_FENETRE)


def noter(entree):
    DONNEES.mkdir(parents=True, exist_ok=True)
    try:
        j = json.loads(JOURNAL.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        j = []
    j = (j + [entree])[-100:]
    tmp = JOURNAL.with_name(JOURNAL.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(j, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, JOURNAL)


# ---------- La boucle ----------

class Gardien:
    """Une décision par mesure : testable sans Windows (les actions sont des fonctions remplaçables)."""

    def __init__(self, actions=None):
        self.debut_critique = None
        self.derniere_analyse = 0.0
        self.derniere_critique = None
        self.a = {"programmes": programmes, "vider_ollama": vider_ollama, "fermer_ollama": fermer_ollama,
                  "fermer_jarvis": fermer_jarvis, "notifier": notifier, "noter": noter, "carte": memoire_carte, **(actions or {})}

    def mesure(self, pourcent, maintenant):
        if pourcent < ANALYSE:
            self.debut_critique = None
            return "ok"
        t = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(maintenant))
        top = [(n, round(g, 1)) for n, g in self.a["programmes"]()[:8]]
        if pourcent >= CRITIQUE:
            self.debut_critique = self.debut_critique or maintenant
            recent = self.derniere_critique is not None and maintenant - self.derniere_critique < 900  # 15 min
            if maintenant - self.debut_critique >= DUREE_CRITIQUE and not recent:
                self.a["vider_ollama"]()
                self.a["fermer_ollama"]()
                n = self.a["fermer_jarvis"]()
                self.a["noter"]({"t": t, "niveau": "critique", "memoire": pourcent, "carte": self.a["carte"](), "programmes": top,
                                 "fait": f"Ollama fermé, Jarvis fermé ({n} programme(s))"})
                autres = ", ".join(f"{nom} {g} Go" for nom, g in top[:3])
                self.a["notifier"]("Mémoire critique", f"J'ai fermé Ollama et Jarvis. Ce qui prend le plus : {autres}")
                self.debut_critique = None
                self.derniere_analyse = maintenant
                self.derniere_critique = maintenant
                return "critique"
        if maintenant - self.derniere_analyse >= 300:  # une analyse toutes les 5 min au plus : le gardien ne pèse rien
            liberes = self.a["vider_ollama"]()
            self.a["noter"]({"t": t, "niveau": "analyse", "memoire": pourcent, "carte": self.a["carte"](), "programmes": top,
                             "fait": ("mémoire d'Ollama vidée : " + ", ".join(liberes)) if liberes else "rien à faire côté Jarvis"})
            self.derniere_analyse = maintenant
            return "analyse"
        return "attente"


def une_seule_copie():
    DONNEES.mkdir(parents=True, exist_ok=True)
    try:
        ancien = int(VERROU.read_text())
        if os.name == "nt":
            vivant = str(ancien) in subprocess.run(["tasklist", "/FI", f"PID eq {ancien}", "/NH"], capture_output=True,
                                                    text=True, creationflags=SANS_FENETRE).stdout
        else:
            os.kill(ancien, 0)
            vivant = True
        if vivant and ancien != os.getpid():
            return False
    except (OSError, ValueError, ProcessLookupError):
        pass
    VERROU.write_text(str(os.getpid()))
    return True


def surveiller():
    if not une_seule_copie():
        return
    g = Gardien()
    while True:
        m = memoire()
        if m:
            g.mesure(m[1], time.time())
        time.sleep(PAUSE)


def etat():
    m = memoire()
    try:
        alertes = json.loads(JOURNAL.read_text(encoding="utf-8"))[-5:]
    except (OSError, ValueError):
        alertes = []
    lignes = [f"Mémoire : {m[1]} % de {m[0]:.0f} Go" if m else "Mémoire : inconnue",
              f"Jeu détecté : {jeu_en_cours() or 'non'}"]
    lignes += [f"{a['t']} · {a['niveau']} · {a['memoire']} % · {a['fait']}" for a in alertes]
    return "\n".join(lignes)


if __name__ == "__main__":
    if "--etat" in sys.argv:
        sys.stdout.reconfigure(encoding="utf-8")
        print(etat())
    else:
        surveiller()
