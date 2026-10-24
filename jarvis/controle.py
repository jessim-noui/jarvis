r"""Panneau de contrôle (mission 6) : les services et les scripts de Jarvis. LISTE BLANCHE seulement, jamais de commande libre.

Toute action passe par securite.executer("controle", origine humaine) : depuis le site (clic + confirmation), ou proposée
par Jarvis dans le chat (actions.proposer → bouton « Confirmer »). Rien ne s'installe, rien ne se supprime.
"""
import re, subprocess, sys, threading, time
from pathlib import Path
from commun import RACINE, DONNEES, lire_json, journaliser
import securite

SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
CATALOGUE = {  # id : (nom, type, actions permises)
    "routeur": ("Routeur d'IA", "service", ("demarrer", "arreter", "relancer")),
    "ollama": ("IA locale (Ollama)", "service", ("relancer",)),
    "telegram": ("Bot Telegram", "service", ()),
    "directeur": ("Directeur (site ouvert, toutes les 3 h au plus)", "service", ("activer", "desactiver", "lancer")),
    "veille": ("Découvertes du jour", "script", ("lancer",)),
    "offres": ("Recherche d'offres", "script", ("lancer",)),
    "candidatures": ("Suivi des candidatures", "script", ("lancer",)),
    "analyse-pc": ("Analyse du PC", "script", ("lancer",)),
    "diagnostic-pc": ("Diagnostic du PC (lecture seule : plantages, carte graphique, mémoire)", "script", ("lancer",)),
    "sauvegarde": ("Sauvegarde", "script", ("lancer",)),
    "tests": ("Tests", "script", ("lancer",)),
}
MOTS = {"demarrer": "démarrer", "arreter": "arrêter", "relancer": "relancer", "lancer": "lancer", "activer": "activer", "desactiver": "mettre en pause"}
SERVEUR = {}  # fonctions qui vivent dans serveur.py (état des services, tâches de fond), données par lui au démarrage


def valider(cible, action):
    if cible not in CATALOGUE or action not in CATALOGUE[cible][2]:
        raise securite.ActionRefusee("Action non autorisée dans le panneau de contrôle.")


def resume(cible, action):
    return f"{MOTS[action].capitalize()} : {CATALOGUE[cible][0]}"


def arreter_routeur():
    """Arrête le routeur (port 4000). Octets bruts : netstat écrit dans l'encodage de la console."""
    sortie = subprocess.run(["netstat", "-ano"], capture_output=True, creationflags=SANS_FENETRE).stdout.decode("ascii", "ignore")
    for ligne in sortie.splitlines():
        m = ligne.split()
        if len(m) >= 5 and m[1].endswith(":4000") and m[3] == "LISTENING":
            subprocess.run(["taskkill", "/PID", m[4], "/F", "/T"], capture_output=True, creationflags=SANS_FENETRE)


_relances = []  # mission 13 : heures des derniers démarrages du routeur (anti-boucle)


def demarrer_routeur():
    """Mission 13 : seulement l’utilisateur présent (un clic sur le site), et au plus 3 fois en 10 min ; ensuite plus rien, avec une alerte."""
    import commun
    if not commun.present():
        return False
    maintenant = time.time()
    _relances[:] = [t for t in _relances if maintenant - t < 600]
    if len(_relances) >= 3:
        import securite
        securite.alerter("routeur", "Le routeur a été relancé 3 fois en 10 min : Jarvis n'essaie plus (relance JARVIS.bat).", ["routeur"])
        return False
    _relances.append(maintenant)
    d = RACINE / "routeur"  # comme lancer.ps1 : run.bat dans une console cachée
    subprocess.Popen(["cmd.exe", "/c", str(d / "run.bat"), "cache"], cwd=d, creationflags=SANS_FENETRE)
    return True


def etat():
    s = SERVEUR["services"]()
    from suite import routes
    occupe = lambda k: bool(routes._occupe.get(k)) or s["taches"].get(k) == "en cours"
    cy = lire_json(DONNEES / "directeur-cycle.json", {})
    f = cy.get("fin", "")
    etats = {"routeur": "allumé" if s["routeur"] else "éteint", "ollama": "allumée" if s["ollama"] else "éteinte",
             "telegram": s["telegram"] or "?", "directeur": "en cours" if occupe("cycle") else ("actif quand le site est ouvert" if routes.mode_auto() else "en pause : rien ne se lance seul")
             + " · dernier cycle : " + (f"le {f[8:10]}/{f[5:7]} à {f[11:16]}, {cy.get('blocage') or cy.get('resume', '')}" if f else "jamais"),
             "veille": "en cours" if SERVEUR["veille_en_cours"]() else "prête"}
    out = []
    for k, (nom, genre, acts) in CATALOGUE.items():
        e = etats.get(k) or ("en cours" if occupe(k) else s["taches"].get(k) or "prêt")
        out.append({"id": k, "nom": nom, "genre": genre, "etat": e, "actions": [{"id": a, "nom": MOTS[a]} for a in acts]})
    return out


PAQUET = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{1,60}")


@securite.autoriser("installer")
def installer(nom, outil):
    """Mission 10 : « installe X » dans le chat → Jarvis DEMANDE ; ceci ne part qu'après le clic « Confirmer » de l’utilisateur.
    Un nom de paquet seul (jamais de commande libre), par pip ou winget."""
    if outil not in ("pip", "winget") or not PAQUET.fullmatch(nom or ""):
        raise securite.ActionRefusee("Nom de paquet invalide.")
    cmd = ([sys.executable, "-m", "pip", "install", nom] if outil == "pip" else
           ["winget", "install", nom, "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity", "--silent"])
    lance = SERVEUR["tache_de_fond"]("installation " + nom, cmd, RACINE)
    return {"ok": lance, "message": f"Installation de {nom} lancée ({outil}). Le résultat sera dans le journal."
            if lance else "Cette installation est déjà en cours."}


@securite.autoriser("controle")
def executer(cible, action):
    """Seul chemin vers une action du panneau (appelé par securite.executer, origine humaine obligatoire)."""
    valider(cible, action)
    from suite import routes, sauvegarde, sante
    py, jarvis = sys.executable, Path(__file__).resolve().parent
    faire = {
        ("routeur", "arreter"): arreter_routeur,
        ("routeur", "demarrer"): demarrer_routeur,
        ("routeur", "relancer"): lambda: (arreter_routeur(), demarrer_routeur()),
        ("ollama", "relancer"): SERVEUR["relancer_ollama"],
        ("directeur", "activer"): lambda: routes.regler_mode_auto(True),
        ("directeur", "desactiver"): lambda: routes.regler_mode_auto(False),
        ("directeur", "lancer"): lambda: routes._en_fond("cycle", __import__("suite.cycle", fromlist=["cycle"]).cycle),
        ("veille", "lancer"): SERVEUR["lancer_veille"],
        ("offres", "lancer"): lambda: routes._en_fond("offres", routes.chercher_offres),
        ("candidatures", "lancer"): lambda: SERVEUR["tache_de_fond"]("candidatures", [py, str(RACINE / "outils" / "candidatures" / "suivi_candidatures.py")],
                                                                     RACINE / "outils" / "candidatures"),
        ("analyse-pc", "lancer"): lambda: SERVEUR["tache_de_fond"]("analyse-pc", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                                                                  str(RACINE / "site" / "analyse-pc" / "analyser.ps1")], RACINE / "site" / "analyse-pc"),
        ("diagnostic-pc", "lancer"): lambda: SERVEUR["tache_de_fond"]("diagnostic-pc", ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                                                                     str(RACINE / "site" / "analyse-pc" / "diagnostic-pc.ps1")], RACINE / "site" / "analyse-pc"),
        ("sauvegarde", "lancer"): lambda: routes._en_fond("sauvegarde", sauvegarde.quotidienne_forcee),
        ("tests", "lancer"): lambda: routes._en_fond("tests", sante.lancer_tests),
    }
    from commun import arret_actif
    if CATALOGUE[cible][1] == "script" and arret_actif():
        return {"ok": False, "message": "Arrêt d'urgence actif : relance les agents d'abord."}
    if CATALOGUE[cible][1] == "script":  # ces fonctions partent déjà en arrière-plan et disent si elles tournaient déjà
        lance = faire[(cible, action)]() is not False
    elif cible == "directeur":  # Pause / Actif / un cycle ponctuel : immédiat (le cycle part déjà en arrière-plan)
        lance = faire[(cible, action)]() is not False
    else:  # services : la page n'attend pas (relancer le routeur prend 20 s)
        threading.Thread(target=faire[(cible, action)], daemon=True).start()
        lance = True
    journaliser(agent="jarvis", action="panneau de contrôle", etat="info", statut="ok" if lance else "déjà en cours", resume=resume(cible, action))
    return {"ok": lance, "message": resume(cible, action) + (" : c'est lancé." if lance else " : déjà en cours.")}
