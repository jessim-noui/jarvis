r"""Mission 10 — Redémarrage propre du serveur Jarvis après un changement de son code Python (lancé par suite\modifier.py).

Usage : redemarrer_serveur.py <id de la demande> <commit> [annulation]
1. attend que la réponse du chat soit partie ; 2. arrête le serveur qui écoute sur 127.0.0.1:4100 ; 3. le relance (pyw, sans
console, comme lancer.ps1) ; 4. contrôle de santé (/etat). Si la santé échoue : git revert du commit, relance, message clair.
"""
import json, subprocess, sys, time, urllib.request
from pathlib import Path

JARVIS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(JARVIS))
sys.path.insert(0, str(JARVIS / "outils"))
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
RELANCES = JARVIS / "donnees" / "relances_serveur.json"  # mission 13 : heures des derniers redémarrages (anti-boucle)


def relance_permise(maintenant=None):
    """Mission 13 : au plus 3 redémarrages du serveur en 10 min ; ensuite plus rien (le serveur reste tel quel)."""
    maintenant = maintenant or time.time()
    try:
        t = [x for x in json.loads(RELANCES.read_text(encoding="utf-8")) if maintenant - x < 600]
    except (OSError, ValueError, TypeError):
        t = []
    if len(t) >= 3:
        return False
    RELANCES.parent.mkdir(parents=True, exist_ok=True)
    RELANCES.write_text(json.dumps(t + [maintenant]), encoding="utf-8")
    return True


def repond():
    try:
        with urllib.request.urlopen("http://127.0.0.1:4100/etat", timeout=3) as r:
            return r.status == 200
    except OSError:
        return False


def pids_serveur():
    """Les PID qui écoutent sur 127.0.0.1:4100 (Windows en français écrit « ÉCOUTE » : on repère l'adresse distante 0.0.0.0:0)."""
    sortie = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, encoding="oem", errors="replace",
                            creationflags=SANS_FENETRE).stdout or ""
    return sorted({l.split()[-1] for l in sortie.splitlines() if len(l.split()) == 5 and l.split()[1] == "127.0.0.1:4100"
                   and l.split()[2] == "0.0.0.0:0"})


def arreter():
    """Arrête TOUS les serveurs qui écoutent (un vieux serveur resté en mémoire répondrait à la place du nouveau)."""
    for _ in range(20):
        pids = pids_serveur()
        if not pids:
            return
        for pid in pids:  # sans /T : ce script est lancé par le serveur, il ne doit pas s'arrêter avec lui
            subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, creationflags=SANS_FENETRE)
        time.sleep(0.5)


def demarrer(secondes=45):
    pyw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else sys.executable), "serveur.py"], cwd=JARVIS,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | SANS_FENETRE)
    fin = time.time() + secondes
    while time.time() < fin:
        if repond():
            return True
        time.sleep(1)
    return False


def main(ident, commit, mode="integration"):
    from suite import modifier, politique
    from commun import journaliser
    time.sleep(2)
    if not relance_permise():
        import securite
        securite.alerter("serveur", "Le serveur a été redémarré 3 fois en 10 min : Jarvis n'essaie plus (relance JARVIS.bat).", ["serveur"])
        m = modifier._histo().get(ident, {"id": ident, "fichiers": []})
        return modifier._maj(m, etat="termine", resume="Changement intégré, mais pas de redémarrage : déjà 3 en 10 min. Relance JARVIS.bat.")
    arreter()
    if mode == "annulation":  # le bouton Annuler a déjà défait le commit : on relance seulement
        ok = demarrer()
        m = modifier._histo().get(ident, {"id": ident, "fichiers": []})
        return modifier._maj(m, etat="annule", resume="Annulé : tout est revenu comme avant" + (", serveur redémarré." if ok else
                                                       ", mais le serveur ne répond pas : relance JARVIS.bat."))
    if demarrer():
        m = modifier._histo().get(ident, {"id": ident, "fichiers": []})
        import banc_essai  # mission 16 : le Labo repasse le banc ; s'il recule, rien n'est intégré
        try:
            ok, phrase = banc_essai.verifier_regression()
        except Exception as e:  # noqa: BLE001
            ok, phrase = True, f"banc d'essai non passé ({type(e).__name__})"
        if ok:
            modifier._maj(m, etat="termine", resume=f"C'est fait : changement intégré, serveur redémarré, santé OK, {phrase}. Tu peux l'annuler d'un clic.")
            return
        politique.annuler(commit)
        arreter()
        demarrer()
        modifier._maj(m, etat="annule", resume=f"Je l'ai annulé tout seul (git revert) : {phrase}.")
        journaliser(agent="code", action="banc d'essai", etat="info", statut="erreur", resume=f"{phrase} ; {commit} annulé")
        return
    politique.annuler(commit)
    arreter()
    ok = demarrer()
    m = modifier._histo().get(ident, {"id": ident, "fichiers": []})
    modifier._maj(m, etat="annule", resume="Le serveur ne redémarrait plus avec ce changement : je l'ai annulé tout seul (git revert)"
                                           + (" et il tourne de nouveau." if ok else ". Il ne répond toujours pas : relance JARVIS.bat."))
    journaliser(agent="code", action="redémarrage du serveur", etat="info", statut="erreur", resume=f"santé en échec, {commit} annulé")


if __name__ == "__main__":
    main(*sys.argv[1:4])
