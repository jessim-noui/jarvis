r"""Pause Ollama (« mode jeu ») : quand tu joues à un jeu sur ton PC, l'IA locale (Ollama) libère la mémoire et Jarvis ne la réveille plus tant que tu joues.

  py -3 outils\mode_jeu.py diagnostic   → LECTURE SEULE : mémoire du PC, ce qui la prend, modèles Ollama chargés,
                                          et qui a réveillé l'IA locale ces dernières 24 h (journal de Jarvis)
  py -3 outils\mode_jeu.py on           → vide la mémoire d'Ollama, arrête Ollama, et Jarvis le laisse éteint
  py -3 outils\mode_jeu.py off          → Jarvis peut de nouveau utiliser l'IA locale (il l'allume au 1er besoin, site ouvert)
  py -3 outils\mode_jeu.py              → bascule on/off (c'est ce que fait PAUSE_OLLAMA.bat)

Pendant le mode jeu : les mails, la sécurité et les priorités du jeu (tâches privées, 100 % locales) attendent ;
le chat et les IA en ligne marchent toujours. Rien n'est installé, supprimé ou envoyé. Aucune donnée privée n'est lue.
"""
import collections, csv, ctypes, io, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import commun  # noqa: E402
from commun import LOCAUX, lire_json, mode_jeu  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
APP_OLLAMA = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama app.exe"
Go = 1024 ** 3


def _ollama(chemin, corps=None, timeout=5):
    req = urllib.request.Request(OLLAMA + chemin, data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def modeles_charges():
    """[(nom, taille en Go, part sur la carte graphique en Go)] ; None si Ollama est éteint."""
    try:
        return [(m.get("name", "?"), m.get("size", 0) / Go, m.get("size_vram", 0) / Go) for m in _ollama("/api/ps").get("models", [])]
    except OSError:
        return None


def memoire():
    """(total en Go, utilisée en %) ; None si inconnu."""
    if os.name == "nt":
        class M(ctypes.Structure):
            _fields_ = [("l", ctypes.c_ulong), ("charge", ctypes.c_ulong), ("total", ctypes.c_ulonglong), ("libre", ctypes.c_ulonglong),
                        ("a", ctypes.c_ulonglong), ("b", ctypes.c_ulonglong), ("c", ctypes.c_ulonglong), ("d", ctypes.c_ulonglong),
                        ("e", ctypes.c_ulonglong)]
        m = M()
        m.l = ctypes.sizeof(M)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return m.total / Go, m.charge
        return None
    try:
        info = {l.split(":")[0]: int(l.split()[1]) * 1024 for l in Path("/proc/meminfo").read_text().splitlines()}
        return info["MemTotal"] / Go, round(100 * (1 - info["MemAvailable"] / info["MemTotal"]))
    except (OSError, KeyError, ValueError):
        return None


def gros_programmes(n=8):
    """Les programmes qui prennent le plus de mémoire (Windows : tasklist), additionnés par nom. [(nom, Go)]"""
    if os.name != "nt":
        return []
    try:
        sortie = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, errors="replace",
                                timeout=20, creationflags=SANS_FENETRE).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return lire_tasklist(sortie)[:n]


def lire_tasklist(sortie):
    total = collections.Counter()
    for ligne in csv.reader(io.StringIO(sortie)):
        if len(ligne) >= 5:
            ko = "".join(c for c in ligne[4] if c.isdigit())
            if ko:
                total[ligne[0]] += int(ko) * 1024 / Go
    return total.most_common()


def carte_graphique():
    """(nom, utilisée Go, totale Go) via nvidia-smi s'il existe."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        l = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=10, creationflags=SANS_FENETRE).stdout.strip().splitlines()[0]
        nom, utilise, total = [x.strip() for x in l.split(",")]
        return nom, int(utilise) / 1024, int(total) / 1024
    except (OSError, subprocess.SubprocessError, IndexError, ValueError):
        return None


def reveils_ia_locale(heures=24):
    """Qui a appelé l'IA locale récemment, d'après donnees\\usage.json (profil + heure, aucun contenu)."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - heures * 3600))
    appels = [e for e in lire_json(commun.DONNEES / "usage.json", []) if e.get("t", "") >= limite and est_local(e)]
    par_heure = collections.Counter(e["t"][11:13] + " h" for e in appels)
    par_profil = collections.Counter(e.get("profil", "?") for e in appels)
    return len(appels), par_heure, par_profil


def est_local(e):
    m = (e.get("modele") or "").lower()
    return e.get("profil") in LOCAUX or "ollama" in m or m.startswith(("qwen3:", "llama3", "e-local"))


def diagnostic():
    lignes, conseils = ["DIAGNOSTIC (lecture seule)"], []
    mem = memoire()
    if mem:
        lignes.append(f"Mémoire du PC : {mem[0]:.0f} Go, {mem[1]} % utilisés")
        if mem[1] >= 85:
            conseils.append("La mémoire est presque pleine : c'est la cause classique des freezes en jeu.")
    gpu = carte_graphique()
    if gpu:
        lignes.append(f"Carte graphique : {gpu[0]}, {gpu[1]:.1f} / {gpu[2]:.0f} Go utilisés")
    modeles = modeles_charges()
    if modeles is None:
        lignes.append("Ollama : éteint (il ne prend rien)")
    elif not modeles:
        lignes.append("Ollama : allumé, aucun modèle en mémoire (il prend très peu)")
    else:
        for nom, taille, vram in modeles:
            sur_ram = max(0.0, taille - vram)
            lignes.append(f"Ollama : {nom} chargé, {taille:.1f} Go (dont {sur_ram:.1f} Go dans la mémoire du PC)")
        total = sum(t for _, t, _ in modeles)
        conseils.append(f"Ollama garde {total:.1f} Go réservés. En jeu, la carte graphique est prise par le jeu : le modèle "
                        "déborde dans la mémoire du PC → freezes. Lance « mode_jeu.py on » avant de jouer.")
    gros = gros_programmes()
    if gros:
        lignes.append("Ce qui prend le plus de mémoire : " + ", ".join(f"{n} {g:.1f} Go" for n, g in gros))
    n, par_heure, par_profil = reveils_ia_locale()
    if n:
        lignes.append(f"L'IA locale a été appelée {n} fois en 24 h, par : "
                      + ", ".join(f"{p} ({c})" for p, c in par_profil.most_common()))
        lignes.append("  à ces heures : " + ", ".join(f"{h} ({c})" for h, c in sorted(par_heure.items())))
        conseils.append("Chaque appel charge le modèle et le garde 2 min en mémoire. Depuis la mission 13, Jarvis n'utilise "
                        "l'IA locale que si tu es sur le site et qu'aucun jeu ne tourne.")
    lignes.append(f"Mode jeu : {'ACTIF' if mode_jeu() else 'désactivé'}")
    return "\n".join(lignes + ([""] + ["→ " + c for c in conseils] if conseils else []))


def activer():
    commun.MODE_JEU.parent.mkdir(parents=True, exist_ok=True)
    commun.MODE_JEU.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
    liberes = []
    for nom, taille, _ in modeles_charges() or []:  # keep_alive 0 = Ollama vide ce modèle de la mémoire tout de suite
        try:
            _ollama("/api/generate", {"model": nom, "keep_alive": 0}, timeout=30)
            liberes.append(f"{nom} ({taille:.1f} Go)")
        except OSError:
            pass
    if os.name == "nt":  # puis on arrête Ollama : plus rien ne peut recharger un modèle tant que le mode jeu est actif
        for exe in ("ollama app.exe", "ollama.exe"):
            subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, creationflags=SANS_FENETRE)
    return "MODE JEU ACTIF : " + (("mémoire libérée : " + ", ".join(liberes)) if liberes else "aucun modèle n'était chargé") + \
        ". Ollama est arrêté ; Jarvis ne le relancera pas. Pour revenir : mode_jeu.py off (ou PAUSE_OLLAMA.bat)."


def desactiver():
    """La pause n'est levée QUE par l’utilisateur (ce script, PAUSE_OLLAMA.bat ou le bouton du site). Mission 13 : Ollama n'est pas relancé
    ici ; Jarvis l'allumera lui-même au premier besoin, seulement si l’utilisateur est sur le site et ne joue pas."""
    commun.MODE_JEU.unlink(missing_ok=True)
    return "Mode jeu désactivé : Jarvis peut de nouveau utiliser l'IA locale (mails, sécurité) quand tu es sur le site."


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    choix = sys.argv[1] if len(sys.argv) > 1 else ("off" if mode_jeu() else "on")
    print({"diagnostic": diagnostic, "on": activer, "off": desactiver}.get(choix, lambda: __doc__)())


if __name__ == "__main__":
    main()
