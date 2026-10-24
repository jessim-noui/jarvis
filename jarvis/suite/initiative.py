r"""Mission 16, étape 6 : « Jarvis remarque » — il prend des initiatives, SEULEMENT réversibles, SEULEMENT si l’utilisateur est là
(présent, site ouvert, pas en jeu : M13). Règles décidées par le code ; chaque action va dans le Journal avec Annuler
(outils_chef.noter) et compte dans le budget du Directeur (budget_appels de reglages.json → directeur, par jour).
Réglage « Initiative » : prudent (rien seul) · normal (défaut, la moitié du budget) · audacieux (tout le budget).
Règles :
  1. nouvelle offre « pour toi » sans lettre → brouillon de lettre vérifié (jamais envoyé ; l’utilisateur postule lui-même) ;
  2. question restée sans réponse (erreur ou délai, < 2 h) → réessayée autrement, la réponse va dans le Journal ;
  3. IA lente → la bascule existe déjà (M14, reparations.py) et l'incident s'affiche dans le fil : rien à refaire ici ;
  4. offre « pour toi » dont le lien est mort (expirée) → rangée dans la Corbeille, avec Remettre.
"""
import time
from pathlib import Path

import commun
from commun import DONNEES, lire_json, ecrire_json

REGLAGES = Path(__file__).with_name("reglages.json")
NIVEAUX = ("prudent", "normal", "audacieux")
ETAT = DONNEES / "initiative-etat.json"


def niveau():
    n = (lire_json(REGLAGES, {}).get("initiative") or "normal")
    return n if n in NIVEAUX else "normal"


def choisir(n):
    if n not in NIVEAUX:
        raise ValueError("niveau = prudent, normal ou audacieux")
    r = lire_json(REGLAGES, {})
    r["initiative"] = n
    ecrire_json(REGLAGES, r)
    return {"niveau": n}


def budget():
    """Appels d'IA permis par jour pour les initiatives : une part du budget du Directeur."""
    b = int((lire_json(REGLAGES, {}).get("directeur") or {}).get("budget_appels", 12))
    return {"prudent": 0, "normal": b // 2, "audacieux": b}[niveau()]


def peut_agir():
    import presence
    return niveau() != "prudent" and commun.peut_travailler() and presence.site_ouvert()


def _etat():
    e = lire_json(ETAT, {})
    if e.get("jour") != time.strftime("%Y-%m-%d"):
        e = {"jour": time.strftime("%Y-%m-%d"), "appels": 0, "lettres": [], "reessais": []}
    return e


def tour():
    """Un passage (planificateur, toutes les 10 min) : applique les règles dans l'ordre tant qu'il reste du budget."""
    if not peut_agir():
        return []
    e, fait = _etat(), []
    try:
        fait += [f"idée : {t}" for t in proposer_semaine()]
        fait += _offres_expirees()
        if e["appels"] < budget():
            fait += _reessayer(e)
        if e["appels"] < budget():
            fait += _lettres(e)
    finally:
        ecrire_json(ETAT, e)
    return fait


def _offres_expirees():
    import offres, outils_chef
    fait = []
    for o in [o for o in offres.liste() if o.get("etat") == "pour_toi" and o.get("lien_etat") == "casse" and not o.get("rangee")][:5]:
        outils_chef.ranger_offre(o["id"], "lien expiré, vu pendant une recherche")
        fait.append("offre expirée rangée")
    return fait


def _reessayer(e):
    """Une question du site en erreur (< 2 h), pas encore réessayée : reposée au chef, autrement. La réponse va dans le Journal."""
    import traces, jarvis, outils_chef
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7200))
    for t in reversed(traces.lire()):
        if t.get("route") != "/demander" or t.get("etat") != "erreur" or t.get("debut", "") < limite or t["id"] in e["reessais"]:
            continue
        q = traces.RATEES.pop(t["id"], None)
        e["reessais"].append(t["id"])
        if not q:
            continue
        e["appels"] += 3
        r = jarvis.traiter(q, autrement="la première fois tu n'as pas répondu (erreur ou délai)")
        outils_chef.noter(f"Ta question « {q[:80]} » avait échoué : je l'ai reposée. Réponse : {r.get('reponse', '')[:150]}", {"type": "rien"})
        return ["question réessayée"]
    return []


def _lettres(e):
    """Nouvelle offre « pour toi » sans lettre : un brouillon vérifié, une à la fois."""
    import offres, candidature, outils_chef
    lettres = lire_json(candidature.LETTRES, {})
    for rang, o in enumerate(offres.pour_toi(offres.liste()), 1):
        if o.get("nouvelle") and o["id"] not in lettres and o["id"] not in e["lettres"]:
            e["lettres"].append(o["id"])
            e["appels"] += 1
            outils_chef.preparer_lettre(rang)
            return ["brouillon de lettre"]
    return []


def proposer_semaine():
    """Étape 9 : chaque semaine, 1 à 3 améliorations dans la boîte à idées, avec les chiffres (justes, temps, 👍/👎). Code seulement."""
    e = lire_json(ETAT.with_name("ameliorations-semaine.json"), {})
    if time.time() - float(e.get("t") or 0) < 7 * 86400:
        return []
    import aiguillage
    from suite import idees, sante
    av = aiguillage.bilan_avis(7)
    temps = ((lire_json(sante.VIVE, {}).get("composants") or {}).get("chat") or {}).get("resume_temps", {}).get("total", {})
    ref = lire_json(DONNEES / "banc-reference.json", {})
    chiffres = (f"Semaine : {av['bien']} 👍, {av['mal']} 👎 ; réponse médiane {temps.get('mediane', '?')} s, 95 % sous {temps.get('p95', '?')} s ; "
                f"banc d'essai : {len(ref.get('justes', []))} questions du code justes.")
    idees_ = []
    r = av["raisons"]
    if r.get("trop long", 0) >= 2:
        idees_.append(("Des réponses plus courtes", f"{r['trop long']} réponses jugées trop longues cette semaine. {chiffres}"))
    if r.get("faux", 0) + r.get("pas compris", 0) >= 2:
        idees_.append(("Corriger les réponses à côté", f"{r.get('faux', 0)} fausses, {r.get('pas compris', 0)} pas comprises : je les ajoute au banc et je revois l'aiguillage. {chiffres}"))
    if (temps.get("p95") or 0) > 8:
        idees_.append(("Accélérer les réponses les plus lentes", f"5 % des réponses dépassent {temps['p95']} s. {chiffres}"))
    if not idees_:
        idees_.append(("Bilan de la semaine de Jarvis", f"Rien ne cloche assez pour changer quelque chose. {chiffres}"))
    semaine = time.strftime("%Y-s%V")
    faits = [t for k, (t, a) in enumerate(idees_[:3]) if idees.ajouter(f"m16-{semaine}-{k}", t, a, source="jarvis-semaine")]
    ecrire_json(ETAT.with_name("ameliorations-semaine.json"), {"t": time.time(), "idees": faits})
    return faits
