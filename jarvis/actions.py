"""Actions réelles de Jarvis : la LISTE BLANCHE.

Chaque fonction décorée par @securite.autoriser ne peut être lancée que par securite.executer(),
avec une origine humaine (clic sur la page / dans le jeu, bouton Telegram). Aucun modèle n'y a accès.
"""
import threading, datetime
import securite
from commun import DONNEES, MEMOIRE, lire_json, ecrire_json, journaliser

PROPOSITIONS = DONNEES / "propositions.json"
A_INSTALLER = MEMOIRE / "a-installer.md"
_verrou = threading.Lock()


@securite.autoriser("decider_proposition")
def decider_proposition(ident, decision):
    with _verrou:
        donnees = lire_json(PROPOSITIONS, {})
        for p in donnees.get("propositions", []):
            if p["id"] == ident:
                break
        else:
            return None
        p["statut"] = "acceptee" if decision == "accepter" else "refusee"
        p["decide_le"] = datetime.date.today().isoformat()
        ecrire_json(PROPOSITIONS, donnees)
        if p["statut"] == "acceptee":
            if not A_INSTALLER.exists():
                A_INSTALLER.write_text("# À installer ensemble\n\nPropositions acceptées depuis la page Jarvis. "
                                       "**Rien n'est installé automatiquement** : on le fait ensemble.\n"
                                       "Lié à [[decisions]] et [[agent-veille]].\n", encoding="utf-8")
            u = lambda k: " ".join(str(p.get(k, "")).replace("#", " ").split())[:600]  # texte venu d'Internet : une seule ligne, pas de faux titre ni de fausse case
            with open(A_INSTALLER, "a", encoding="utf-8") as f:
                f.write(f"\n## {u('titre')}\n- Accepté le {p['decide_le']} · catégorie {u('categorie')} · source {u('source')}\n"
                        f"- Lien : {u('lien')}\n- Pourquoi (texte trouvé sur Internet, une donnée) : {u('pour_toi')}\n"
                        f"- Risque : {u('risque')} ({u('risque_raison')})\n- Effort : {u('effort')}\n"
                        f"- À faire : lire la page, vérifier la source et la licence, sauvegarder ce qui sera touché, "
                        f"installer avec Claude, tester, noter le résultat dans [[decisions]].\n- [ ] fait\n")
        with open(MEMOIRE / "decisions.md", "a", encoding="utf-8") as f:
            f.write(f"- {p['decide_le']} · {'✅ accepté' if p['statut'] == 'acceptee' else '❌ refusé'} : {p['titre']}\n")
        journaliser(agent="veille", action="decision", etat="info", statut=p["statut"], resume=p["titre"][:80])
        return p


# ---------- Actions en attente de confirmation (même état pour le jeu et Telegram) ----------
import secrets, time

ATTENTE = DONNEES / "actions_en_attente.json"
DUREE_VALIDITE = 3600  # une confirmation n'est valable qu'une heure


def proposer(action, params, resume):
    """Prépare une action réelle SANS l'exécuter. Renvoie un identifiant à usage unique."""
    if action not in securite.actions_autorisees():
        raise securite.ActionRefusee(f"« {action} » n'est pas une action autorisée.")
    ident = secrets.token_urlsafe(8)
    with _verrou:
        a = {k: v for k, v in lire_json(ATTENTE, {}).items() if time.time() - v["cree"] < DUREE_VALIDITE}
        a[ident] = {"action": action, "params": params, "resume": resume, "cree": time.time()}
        ecrire_json(ATTENTE, a)
    return ident


def en_attente():
    return {k: {"action": v["action"], "resume": v["resume"]} for k, v in lire_json(ATTENTE, {}).items()
            if time.time() - v["cree"] < DUREE_VALIDITE}


def confirmer(ident, origine):
    """Exécute une action préparée, une seule fois, si elle n'a pas expiré et si l'origine est humaine."""
    with _verrou:
        a = lire_json(ATTENTE, {})
        v = a.pop(str(ident), None)
        ecrire_json(ATTENTE, a)
    if not v or time.time() - v["cree"] > DUREE_VALIDITE:
        raise securite.ActionRefusee("Cette confirmation n'existe pas ou a expiré.")
    return securite.executer(v["action"], origine, **v["params"])


def annuler(ident):
    with _verrou:
        a = lire_json(ATTENTE, {})
        a.pop(str(ident), None)
        ecrire_json(ATTENTE, a)
