"""Mission 15 : le fil de Jarvis (la pastille d'activité de la barre du haut).
Des phrases ÉCRITES PAR LE CODE (modèles fixes, pas d'IA) à partir du journal, des délégations et des tâches de fond.
On n'utilise jamais le champ « resume » du journal ni la consigne d'une délégation : ni contenu de message, ni de mail, ni secret.
Le serveur ne fait rien tout seul : la page demande /fil (toutes les 5 s, page visible et peut_travailler())."""
import time

import commun

QUI = {"jarvis": "Jarvis", "veille": "Découvertes", "emploi": "Emploi", "mails": "Mails", "code": "Code",
       "redaction": "Rédaction", "routeur": "Routeur", "directeur": "Directeur"}
# tâche de fond (routes._en_fond) → (qui, ce qu'il fait)
TACHES = {"decouvertes2": ("Découvertes", "cherche de nouvelles IA"), "labo": ("Labo", "compare des IA"),
          "offres": ("Emploi", "cherche des offres"), "tester": ("Santé", "teste tes IA"), "tests": ("Santé", "lance les tests"),
          "sauvegarde": ("Jarvis", "fait la sauvegarde"), "cycle": ("Directeur", "fait son tour"),
          "amelioration": ("Code", "essaie une amélioration"), "reparation": ("Jarvis", "répare une panne"),
          "proposition": ("Directeur", "prépare une proposition"), "question": ("Jarvis", "fait ce que tu as décidé")}
# action du journal → (ce qui s'est passé, pourquoi)
ACTIONS = {
    "pause": ("Je me suis mis en pause", "Tu n'étais pas sur le site : rien ne tourne."),
    "site fermé": ("J'ai tout arrêté", "Plus aucun signal du site depuis 10 min."),
    "labo": ("J'ai comparé des IA au Labo", "Pour garder la meilleure IA pour chaque tâche."),
    "comparer des modèles": ("J'ai comparé des modèles", "Pour choisir la meilleure IA pour chaque tâche."),
    "telegram": ("Telegram", "Le bot de ton téléphone."),
    "decision": ("Une décision a changé", "Ton choix, ou une proposition de la veille."),
    "panneau de contrôle": ("J'ai lancé une action du panneau", "Tu l'as demandé d'un clic."),
    "routage": ("J'ai choisi une IA", "Pour répondre à ta question."),
    "mission": ("Le Directeur a avancé une mission", "Il avance seul, par petites étapes."),
    "cycle du Directeur": ("Le Directeur a fait son tour", "Au plus toutes les 3 h, site ouvert."),
    "tout arrêter": ("J'ai tout arrêté", "Tu as cliqué « Tout arrêter »."),
    "arret d'urgence": ("Arrêt d'urgence", "Tu l'as demandé."),
    "relance ollama": ("J'ai relancé l'IA de ton PC", "Pour une tâche privée."),
    "question": ("Une question n'a pas abouti", "Le détail est dans le Journal."),
    "recherche d'offres": ("J'ai cherché des offres", "France Travail et Adzuna, ta zone et le Sud."),
    "pas pour moi": ("J'ai rangé une offre « Pas pour moi »", "Tu l'as demandé."),
    "amelioration": ("J'ai essayé une amélioration", "Dans une copie à part, avec les tests."),
    "modifier Jarvis": ("L'agent Code a proposé un changement", "Rien n'est gardé sans ton accord."),
    "démarrage du PC": ("J'ai regardé le démarrage du PC", "Pour qu'il ne ralentisse pas."),
    "exporter": ("J'ai préparé le zip du projet", "Sans clé ni donnée perso."),
    "chercher dans le projet": ("J'ai cherché dans le projet", "Pour répondre à ta question."),
    "decouvertes2": ("Découvertes a fait sa recherche", "C'est la recherche de la semaine."),
    "recherche ciblée": ("Découvertes a fait une recherche ciblée", "Tu l'as demandée."),
    "surveillance": ("La surveillance a eu un souci", "Le détail est dans Santé et alertes."),
    "restauration": ("J'ai remis une sauvegarde", "Tu l'as demandé."),
    "tâche bloquée": ("Une tâche bloquée a été arrêtée", "Elle dépassait son temps."),
    "envoi": ("Un mail est parti", "Après ton clic « Envoyer »."),
    "tri": ("J'ai trié les mails", "En local, rien ne sort du PC."),
    "notification": ("Je t'ai prévenu", "Un mail vaut une réponse."),
}
STATUT = {"erreur": "échec", "ok": "", "terminé": "", "terminee": "terminée", "creee": "créée", "refuse": "refusé",
          "annule": "annulé", "bloquee": "bloquée"}


def _epoque(t):
    try:
        return time.mktime(time.strptime(str(t)[:19], "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 0


def _ia(modele):
    """Juste le nom court de l'IA (ex. « mistral-code-latest »), jamais autre chose."""
    m = str(modele or "").split("/")[-1].replace(":free", "")
    return m[:40] if m.replace("-", "").replace(".", "").replace("_", "").replace(":", "").isalnum() else ""


def ligne_journal(e):
    action = str(e.get("action") or "")
    base = action.split(" : ")[0]
    quoi, pourquoi = ACTIONS.get(base) or ACTIONS.get(action) or (base.capitalize()[:40] or "Une action", "")
    st = STATUT.get(str(e.get("statut") or ""), "")
    if st:
        quoi += " · " + st
    return {"h": str(e.get("t", ""))[11:16], "t": e.get("t", ""), "qui": QUI.get(e.get("agent"), "Jarvis"),
            "quoi": quoi, "pourquoi": pourquoi, "ia": _ia(e.get("modele"))}


def lignes(n=3):
    """Les n dernières actions finies (journal + délégations), la plus récente d'abord. Les « pause » répétées n'en font qu'une."""
    out = []
    for e in commun.lire_json(commun.JOURNAL, []):
        if e.get("etat") == "debut":
            continue
        l = ligne_journal(e)
        if out and out[-1]["quoi"] == l["quoi"] and out[-1]["qui"] == l["qui"]:
            out[-1] = l
        else:
            out.append(l)
    for d in commun.lire_json(commun.DONNEES / "delegations.json", []):
        nom = str(d.get("sortie") or "")[:40]
        if nom.replace(".", "").replace("_", "").replace("-", "").isalnum():
            out.append({"h": str(d.get("t", ""))[11:16], "t": d.get("t", ""), "qui": "Claude",
                        "quoi": f"J'ai fait écrire {nom} par une IA gratuite", "pourquoi": "Délégation : elle écrit, Claude relit et teste.",
                        "ia": _ia(d.get("modele"))})
    out.sort(key=lambda l: l["t"])
    return out[-n:][::-1]


def en_cours(occupe, debuts):
    """La tâche qui tourne vraiment (rien de simulé) : nom, depuis combien de secondes."""
    noms = [k for k, v in occupe.items() if v]
    if not noms:
        return None
    k = min(noms, key=lambda k: debuts.get(k, time.time()))
    qui, quoi = TACHES.get(k.split("-")[0], ("Jarvis", "travaille"))
    if k.startswith("mission-"):
        qui, quoi = "Directeur", "avance une mission"
    return {"qui": qui, "quoi": quoi, "depuis": round(time.time() - debuts.get(k, time.time())), "autres": len(noms) - 1}


def fil(occupe, debuts):
    if not commun.peut_travailler():
        return {"actif": False, "en_cours": None, "lignes": []}
    return {"actif": True, "en_cours": en_cours(occupe, debuts), "lignes": lignes()}
