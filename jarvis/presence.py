r"""Mission 11 : Jarvis ne travaille que quand l’utilisateur est là, et l'IA locale ne tourne que pendant une vraie tâche.
Mission 13 : complété, pas remplacé.

- Chaque page du site envoie « je suis là » toutes les 30 s (app.js → POST /site/ouvert), avec « onglet visible ou non », et un
  dernier « caché » quand la page se ferme (pagehide).
- L’utilisateur est là = un onglet visible a parlé il y a moins de 90 s, le PC a servi dans les 10 dernières minutes, AUCUN JEU ne tourne
  (gardien_memoire.jeu_en_cours, vérifié au plus toutes les 30 s) et pas de pause « mode jeu ». C'est ce qui manquait le 20/10 :
  site ouvert + un jeu = Jarvis se croyait là et allumait Ollama.
- Dès que l’utilisateur n'est plus là (jeu, page cachée, PC inutilisé) : Ollama est vidé puis arrêté, les tâches attendent.
- Plus aucun signal pendant 10 min → tout s'arrête (Ollama, Telegram, routeur, serveur). Pour revenir : JARVIS.bat.
- L'état est écrit dans donnees/presence.json (présent / en pause : raison / depuis quand) pour le site, les scripts et le MCP.
- Ollama : lancé par Jarvis seulement quand une tâche locale en a besoin (`ollama serve` sans fenêtre, un seul modèle, gardé 2 min),
  2 démarrages RATÉS de suite au plus (un succès remet le compte à zéro, mission 14), puis une alerte et plus rien.
Hors serveur (tests, scripts), ACTIF reste faux : la() répond toujours vrai et rien ne change.
"""
import ctypes, os, subprocess, threading, time, urllib.request, json
from pathlib import Path

ACTIF = False          # mis à vrai par serveur.py (__main__) : la présence n'est suivie que dans le vrai serveur
VISIBLE = 90           # s : un onglet visible a parlé depuis moins de 90 s
FERME = 600            # s sans aucun « je suis là » = site fermé → tout s'arrête (choix de l’utilisateur, 20/10 : 10 min)
INACTIF = 600          # s sans clavier ni souris = l’utilisateur n'est plus là
GRACE = 180            # s au démarrage pour laisser la page s'ouvrir
JEU_TOUS = 30          # s entre deux recherches de jeu (tasklist)
OLLAMA = "http://127.0.0.1:11434"
_onglets = {}          # id d'onglet -> (heure, visible)
_debut = time.time()
_absent_depuis = None
_jeu = {"t": 0.0, "raison": ""}
_verrou = threading.Lock()
ollama = {"lance": None, "essais": 0}  # Popen d'ollama serve lancé par Jarvis


class _Entree(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def inactif_s():
    """Secondes depuis la dernière touche ou le dernier mouvement de souris (Windows)."""
    try:
        e = _Entree(ctypes.sizeof(_Entree), 0)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(e)):
            return ((ctypes.windll.kernel32.GetTickCount() - e.dwTime) & 0xFFFFFFFF) / 1000
    except Exception:
        pass
    return 0


def signaler(onglet, visible):
    with _verrou:
        _onglets[str(onglet)[:40] or "?"] = (time.time(), bool(visible))
        for k in [k for k, (t, _) in _onglets.items() if time.time() - t > FERME]:
            del _onglets[k]
    if ACTIF:
        return ecrire_etat()["present"]  # mission 13 : le site voit tout de suite « en pause : … »
    return la()


def site_ouvert():
    return any(time.time() - t < FERME for t, _ in list(_onglets.values()))


def jeu():
    """Le jeu qui tourne ("" sinon), d'après le gardien de la mémoire (outils/gardien_memoire.py), au plus toutes les 30 s."""
    if time.time() - _jeu["t"] >= JEU_TOUS:
        try:
            outils = str(Path(__file__).resolve().parent / "outils")
            if outils not in __import__("sys").path:
                __import__("sys").path.insert(0, outils)
            import gardien_memoire
            r = gardien_memoire.jeu_en_cours()
        except Exception:
            r = ""
        _jeu.update(t=time.time(), raison=r)
    return _jeu["raison"]


def raison():
    """"" = l’utilisateur est là ; sinon la raison de la pause (affichée sur le site)."""
    if not ACTIF:
        return ""
    import commun
    if commun.mode_jeu():
        return "pause demandée (mode jeu)"
    if not any(v and time.time() - t < VISIBLE for t, v in list(_onglets.values())):
        return "tu n'es pas sur le site"
    if inactif_s() >= INACTIF:
        return "PC inutilisé depuis 10 min"
    j = jeu()
    return f"jeu détecté ({j})" if j else ""


def raison_refus():
    """Mission 14 : la vraie raison d'un refus d'Ollama, pour le message affiché (au lieu de « pas sur le site, ou un jeu »)."""
    import commun
    if commun.arret_actif():
        return "arrêt d'urgence actif"
    if os.environ.get("JARVIS_IA_LOCALE") == "0":
        return "IA locale coupée pour ce script"
    r = raison() if ACTIF else ("" if commun.present() else "tu n'es pas sur le site")
    if r:
        return "en pause : " + r
    if ollama["essais"] >= 2:
        return "Ollama n'a pas démarré 2 fois de suite (relance JARVIS.bat)"
    if not ACTIF:
        return "Ollama n'est pas lancé (seul le serveur Jarvis peut l'allumer)"
    return "Ollama absent ou n'a pas démarré"


def la():
    return not ACTIF or raison() == ""


def ecrire_etat(r=None):
    """donnees/presence.json : ce que le site affiche, et ce que lisent les scripts et le MCP (commun.present)."""
    global _absent_depuis
    import commun
    r = raison() if r is None else r
    if r and not _absent_depuis:
        _absent_depuis = time.time()
    elif not r:
        _absent_depuis = None
    etat = {"present": r == "", "raison": r, "epoque": time.time(), "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "depuis": time.strftime("%H:%M", time.localtime(_absent_depuis)) if _absent_depuis else ""}
    commun.ecrire_json(commun.PRESENCE, etat)
    return etat


def attendre():
    """Bloque une tâche de fond tant que l’utilisateur n'est pas là (vérifié toutes les 30 s)."""
    while not la():
        time.sleep(30)


# ---------- IA locale (Ollama) ----------

def ollama_repond():
    try:
        urllib.request.urlopen(OLLAMA + "/api/version", timeout=2)
        return True
    except Exception:
        return False


def demarrer_ollama():
    """N'appeler QUE par commun.ollama_pret() (le verrou : présence, pas de jeu, pas de pause). Allume Ollama pour une tâche locale.
    Déjà allumé (par l’utilisateur ou Jarvis) → rien. Mission 14 : seuls les démarrages ratés comptent (remis à zéro après un succès) ;
    2 ratés de suite → une alerte puis plus rien."""
    if not ACTIF:  # hors serveur (tests, scripts) : rien n'est lancé, on dit seulement s'il tourne
        return ollama_repond()
    if ollama_repond():
        ollama["essais"] = 0
        return True
    with _verrou:
        if ollama["essais"] >= 2:
            return False
        ollama["essais"] += 1
        env = {**os.environ, "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_KEEP_ALIVE": "2m", "OLLAMA_NUM_PARALLEL": "1"}
        exe = Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"
        if not exe.exists():  # mission 13 : jamais la commande « ollama » trouvée dans le PATH, seulement ce programme précis
            return False
        try:
            ollama["lance"] = subprocess.Popen([str(exe), "serve"], env=env,
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError:
            ollama["lance"] = None
    for _ in range(30):
        if ollama_repond():
            ollama["essais"] = 0
            return True
        time.sleep(1)
    if ollama["essais"] >= 2:
        import securite
        securite.alerter("ollama", "L'IA locale n'a pas démarré 2 fois de suite : Jarvis n'essaie plus (relance JARVIS.bat).", ["ollama"])
    return False


def decharger_modeles():
    try:
        with urllib.request.urlopen(OLLAMA + "/api/ps", timeout=3) as r:
            modeles = [m["name"] for m in json.loads(r.read()).get("models", [])]
        for m in modeles:
            req = urllib.request.Request(OLLAMA + "/api/generate", data=json.dumps({"model": m, "keep_alive": 0}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=30).read()
        return modeles
    except Exception:
        return []


def arreter_ollama():
    """Arrête Ollama seulement s'il a été lancé par Jarvis (celui de l’utilisateur, lancé à la main, reste)."""
    p = ollama["lance"]
    if p and p.poll() is None:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/F", "/T"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ollama["lance"] = None
        return True
    return False


# ---------- Le gardien (thread du serveur) ----------

def eteindre_ollama():
    """Vide puis arrête TOUT Ollama (le serveur et l'application) : rien ne doit rester en mémoire pendant un jeu."""
    d = decharger_modeles()
    arreter_ollama()
    for exe in ("ollama app.exe", "ollama.exe"):  # l'application d'abord : sinon elle relance son serveur
        subprocess.run(["taskkill", "/IM", exe, "/F"], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return d


def tour(tout_arreter, journaliser, etat_avant):
    """Un passage du gardien (testable) : écrit l'état, éteint Ollama dès que l’utilisateur n'est plus là, tout arrête après 10 min sans signal.
    Renvoie "arret" ou l'état « présent » courant."""
    if not site_ouvert() and time.time() - _debut > GRACE:
        ecrire_etat("site fermé")
        journaliser(agent="jarvis", action="site fermé", etat="info", statut="ok", resume="Plus aucun signal du site depuis 10 min : tout s'arrête.")
        tout_arreter(auto=True)
        return "arret"
    e = ecrire_etat()
    try:  # mission 16 : la dictée libère la carte graphique en jeu, absent, ou 10 min sans dictée
        __import__("suite.dictee").dictee.surveiller()
    except Exception:
        pass
    if not e["present"] and (etat_avant or ollama_repond()):  # il vient de partir, ou quelque chose a relancé Ollama pendant la pause
        d = eteindre_ollama()
        journaliser(agent="jarvis", action="pause", etat="info", statut="ok",
                    resume=f"En pause : {e['raison']}. Ollama vidé et arrêté" + (f" ({', '.join(d)})" if d else "") + ".")
    return e["present"]


def gardien(tout_arreter, journaliser, pas=15):
    """Thread du serveur : toutes les 15 s, un tour()."""
    etat = True
    while True:
        time.sleep(pas)
        etat = tour(tout_arreter, journaliser, etat)
        if etat == "arret":
            return
