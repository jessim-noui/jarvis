r"""Mission 13 : un seul planificateur, plus aucune boucle à intervalle. Sans l’utilisateur (commun.peut_travailler), rien ne se lance.

- « quotidien » : 1 fois par jour, à la première présence du jour : recherche d'offres, lecture des nouvelles, liens vérifiés,
  Telegram « 3 meilleures », veille, Découvertes, sauvegarde. Étape par étape : si l’utilisateur part (jeu, page cachée), la tâche
  s'arrête à la fin de son étape et reprend à son retour, sans refaire ce qui est fait (donnees/planificateur.json).
- « mails » : à la première présence du jour, puis toutes les 2 h si l’utilisateur est là.
- « initiative » (mission 16) : toutes les 10 min si l’utilisateur est là, « Jarvis remarque » (suite/initiative.py).
Le planificateur ne fait que regarder toutes les 30 s ; il ne lance pas de modèle lui-même.
"""
import threading, time
import commun
from commun import DONNEES, lire_json, ecrire_json, journaliser

ETAT = DONNEES / "planificateur.json"
MAILS_TOUS = 2 * 3600
INITIATIVE_TOUS = 600
PAS = 30
_en_cours = set()
_verrou = threading.Lock()


def jour(t):
    return time.strftime("%Y-%m-%d", time.localtime(t))


def dues(etat, maintenant):
    q = etat.get("quotidien", {})
    out = []
    if q.get("jour") != jour(maintenant) or not q.get("fini"):
        out.append("quotidien")
    if etat.get("mails_jour") != jour(maintenant) or maintenant - float(etat.get("mails_t") or 0) >= MAILS_TOUS:
        out.append("mails")
    if maintenant - float(etat.get("initiative_t") or 0) >= INITIATIVE_TOUS:  # mission 16 : « Jarvis remarque »
        out.append("initiative")
    return out


def _en_fond(nom, fn):
    def tourne():
        try:
            fn()
        except Exception as e:
            journaliser(agent="jarvis", action="planificateur : " + nom, etat="info", statut="erreur", resume=type(e).__name__)
        finally:
            with _verrou:
                _en_cours.discard(nom)
    threading.Thread(target=tourne, daemon=True, name="plan-" + nom).start()


def tour(taches, maintenant=None, demarrer=None):
    """Un regard : lance ce qui est dû, seulement si l’utilisateur est là. Renvoie les noms lancés (testable sans fil)."""
    if not commun.peut_travailler():
        return []
    maintenant = maintenant or time.time()
    lances = []
    with _verrou:
        etat = lire_json(ETAT, {})
        for nom in dues(etat, maintenant):
            if nom not in taches or nom in _en_cours:
                continue
            if nom == "mails":  # noté au lancement : pas de 2e tri dans les 2 h, même si celui-ci échoue
                etat.update(mails_t=maintenant, mails_jour=jour(maintenant))
                ecrire_json(ETAT, etat)
            if nom == "initiative":
                etat["initiative_t"] = maintenant
                ecrire_json(ETAT, etat)
            _en_cours.add(nom)
            lances.append(nom)
    for nom in lances:
        (demarrer or _en_fond)(nom, taches[nom])
        if demarrer:
            _en_cours.discard(nom)
    return lances


def quotidien(etapes, maintenant=None):
    """Les étapes du jour, dans l'ordre ; s'arrête proprement si l’utilisateur part, reprend à son retour sans doublon."""
    d = jour(maintenant or time.time())
    with _verrou:
        etat = lire_json(ETAT, {})
        q = etat.get("quotidien", {})
        if q.get("jour") != d:
            q = {"jour": d, "faites": [], "fini": False}
    for nom, fn in etapes:
        if nom in q["faites"]:
            continue
        if not commun.peut_travailler():
            return False
        try:
            fn()
        except Exception as e:  # une étape ratée ne bloque pas les autres ; elle n'est pas refaite en boucle aujourd'hui
            journaliser(agent="jarvis", action="tâche du jour : " + nom, etat="info", statut="erreur", resume=type(e).__name__)
        q["faites"].append(nom)
        with _verrou:
            etat = lire_json(ETAT, {})
            etat["quotidien"] = q
            ecrire_json(ETAT, etat)
    q["fini"] = True
    with _verrou:
        etat = lire_json(ETAT, {})
        etat["quotidien"] = q
        ecrire_json(ETAT, etat)
    return True


def boucle(taches):
    """Thread du serveur : un regard toutes les 30 s."""
    while True:
        time.sleep(PAS)
        try:
            tour(taches)
        except Exception as e:
            journaliser(agent="jarvis", action="planificateur", etat="info", statut="erreur", resume=type(e).__name__)
