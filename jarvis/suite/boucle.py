r"""Mission 7 (et 9) — La boucle d'amélioration, de bout en bout, en vrai :

  observer → constat avec preuves → proposition (diff) → essai en bac à sable → classement →
  intégration auto (tests/doc/réglages) OU carte « Décisions pour moi » → mini-rapport → annulable.

Les propositions de diff viennent d'ameliorer.py (déjà en place) ou de Claude Code (boîte du Directeur).
Rien n'est inventé : chaque constat cite les chiffres lus dans usage.json, journal.json et alertes.json.
"""
import sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import DONNEES, lire_json, ecrire_json, journaliser  # noqa: E402
from suite import politique, directeur  # noqa: E402

ESSAIS = DONNEES / "ameliorations-suite.json"


def observer(jours=7):
    """Les problèmes qui reviennent, avec leurs preuves (aucun appel d'IA)."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    constats = []
    usage = [e for e in lire_json(DONNEES / "usage.json", []) if e.get("t", "") >= limite]
    par_profil = {}
    for e in usage:
        p = par_profil.setdefault(e.get("profil", "?"), {"n": 0, "err": 0, "duree": 0.0, "bascules": 0})
        p["n"] += 1
        p["err"] += bool(e.get("erreur"))
        p["duree"] += e.get("duree", 0)
        p["bascules"] += e.get("bascules", 0)
    for nom, p in par_profil.items():
        if p["n"] >= 5 and p["err"] / p["n"] >= 0.2:
            constats.append({"cle": f"erreurs:{nom}", "titre": f"L'IA « {nom} » échoue souvent",
                             "preuve": f"{p['err']} erreurs sur {p['n']} appels en {jours} jours", "gravite": 2})
        if p["n"] >= 5 and p["duree"] / p["n"] > 30:
            constats.append({"cle": f"lent:{nom}", "titre": f"L'IA « {nom} » est lente",
                             "preuve": f"{round(p['duree'] / p['n'])} s en moyenne sur {p['n']} appels", "gravite": 1})
        if p["n"] >= 5 and p["bascules"] / p["n"] >= 0.5:
            constats.append({"cle": f"bascule:{nom}", "titre": f"L'IA principale de « {nom} » répond rarement",
                             "preuve": f"{p['bascules']} bascules vers une IA de secours sur {p['n']} appels", "gravite": 1})
    journal = [e for e in lire_json(DONNEES / "journal.json", []) if e.get("t", "") >= limite]
    erreurs = Counter((e.get("agent"), e.get("action")) for e in journal if e.get("statut") == "erreur")
    for (agent, action), n in erreurs.items():
        if n >= 3:
            constats.append({"cle": f"outil:{agent}:{action}", "titre": f"« {action} » ({agent}) plante souvent",
                             "preuve": f"{n} erreurs dans le journal en {jours} jours", "gravite": 2})
    alertes = [a for a in lire_json(DONNEES / "alertes.json", []) if a.get("t", "") >= limite]
    if len(alertes) >= 5:
        constats.append({"cle": "alertes", "titre": "Beaucoup de messages douteux bloqués",
                         "preuve": f"{len(alertes)} alertes en {jours} jours (voir Alertes et problèmes)", "gravite": 1})
    return sorted(constats, key=lambda c: -c["gravite"])


def _essais():
    return lire_json(ESSAIS, {})


def traiter_proposition(diff, titre, probleme, preuve="", source="jarvis", classer=None):
    """Une proposition de changement entre ici. Renvoie ce qui s'est passé (et le mini-rapport ou la décision).
    `classer` (mission 8) : un autre classement que la politique, pour les demandes faites par l’utilisateur dans le chat (modifier.py)."""
    essai = politique.essayer(diff, titre)
    if classer and essai["classement"]["niveau"] != "interdit":
        essai["classement"] = classer(diff)
    essai.update(probleme=probleme, preuve=preuve, source=source, t=time.strftime("%Y-%m-%dT%H:%M:%S"), diff=diff[:20000])
    ok, raisons = politique.peut_promouvoir(essai["classement"], essai["tests_ok"])
    if essai["classement"]["niveau"] == "interdit" or not essai["applique"] or not essai["tests_ok"]:
        essai["statut"] = "rejete"
        directeur.mini_rapport(probleme=probleme, fait=f"Essai rejeté : {titre}",
                               pourquoi="; ".join(essai["classement"]["raisons"]) if essai["classement"]["niveau"] == "interdit"
                               else ("tests en échec" if essai["applique"] else "ne s'applique pas"),
                               tests="échec" if essai["applique"] else "non lancés", limites=essai["sortie"][-200:],
                               retour_arriere="rien à annuler : rien n'a été intégré", source=source)
    elif ok:
        r = politique.integrer(essai)
        essai["statut"] = "integre" if r["ok"] else "en_attente"
        if r["ok"]:
            essai["commit"] = r["commit"]
            directeur.mini_rapport(probleme=probleme, fait=f"Intégré automatiquement : {titre}",
                                   pourquoi="; ".join(essai["classement"]["raisons"]) + " ; tous les tests passent", tests="OK dans le bac à sable",
                                   fichiers=", ".join(essai["classement"]["fichiers"]), commit=r["commit"],
                                   retour_arriere=r["retour_arriere"], source=source)
        else:
            raisons = [r["raison"]]
    if essai.get("statut") not in ("rejete", "integre"):
        essai["statut"] = "en_attente"
        directeur.creer_decision(sujet=f"amelioration:{essai['id']}", question=f"Intégrer « {titre} » ?",
                                 pourquoi=f"{probleme} {preuve}".strip() + " — " + "; ".join(raisons),
                                 options=[{"id": "integrer", "libelle": "Intégrer", "avantages": "Les tests passent dans le bac à sable",
                                           "risques": "; ".join(essai["classement"]["raisons"])},
                                          {"id": "refuser", "libelle": "Refuser"}],
                                 recommande="", si_reporte="Rien ne change ; l'essai reste prêt.", source=source)
    e = _essais()
    e[essai["id"]] = essai
    ecrire_json(ESSAIS, dict(list(e.items())[-50:]))
    journaliser(agent="jarvis", action="amelioration", etat="info", statut=essai["statut"], resume=titre[:100])
    return essai


def apres_decision(decision):
    """Appelé quand l’utilisateur a répondu à une carte « amelioration:<id> » (depuis la page)."""
    ident = decision["sujet"].split(":", 1)[1]
    e = _essais()
    essai = e.get(ident)
    if not essai or essai.get("statut") != "en_attente":
        return None
    if decision["choix"] == "integrer":
        r = politique.integrer(essai)
        essai["statut"] = "integre" if r["ok"] else "echec_integration"
        if r["ok"]:
            essai["commit"] = r["commit"]
            directeur.mini_rapport(probleme=essai["probleme"], fait=f"Intégré avec ton accord : {essai['titre']}",
                                   tests="OK dans le bac à sable", fichiers=", ".join(essai["classement"]["fichiers"]),
                                   commit=r["commit"], retour_arriere=r["retour_arriere"], source=essai["source"])
    else:
        essai["statut"] = "refuse"
        politique.git("branch", "-D", essai["branche"])
    ecrire_json(ESSAIS, e)
    return essai
