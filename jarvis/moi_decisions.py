r"""Mission 12 : ce que l’utilisateur confirme lui-même sur sa page Moi, via Décisions (rien n'est changé avant son clic).

- « moi-competences » : une carte qui liste les compétences de moi.json, Garder / Enlever pour chacune.
- « moi-magazine:2 » et « moi-magazine:3 » : les textes des pages 2 et 3 du magazine, modifiables, affichés seulement après « Valider ».
Avant chaque modification, l'ancien moi.json est copié dans donnees/moi-avant.json.
"""
from commun import DONNEES, lire_json, ecrire_json

MOI = DONNEES / "moi.json"
VALIDER = [{"id": "valider", "libelle": "Valider"}]


def _sauver(m):
    ecrire_json(DONNEES / "moi-avant.json", lire_json(MOI, {}))
    ecrire_json(MOI, m)


def proposer_competences():
    from suite import directeur
    items = [i for d in lire_json(MOI, {}).get("competences", []) for i in d.get("items", [])]
    return directeur.creer_decision(
        "moi-competences", "Ces compétences sont sur ta page Moi : lesquelles sais-tu vraiment utiliser ?",
        "Tes lettres ne citent que ce qui est sur ta page Moi. Garde seulement ce dont tu peux parler en entretien.",
        VALIDER, source="moi", extra={"items": items})


def proposer_magazine(page, titre, texte):
    from suite import directeur
    return directeur.creer_decision(
        f"moi-magazine:{page}", f"Page {page} du magazine de ta page Moi (« {titre} ») : ce texte te va ?",
        "Il sera affiché sur ta page Moi seulement après ton accord. Tu peux le modifier avant de valider.",
        VALIDER, source="moi", extra={"texte": texte, "titre": titre})


def appliquer(d, corps):
    """Après « Valider » dans Décisions : applique le choix de l’utilisateur (compétences enlevées, texte du magazine)."""
    if d.get("choix") != "valider":
        return
    m = lire_json(MOI, {})
    if d["sujet"] == "moi-competences":
        enlever = {str(x) for x in (corps.get("enlever") or [])[:100]}
        for dom in m.get("competences", []):
            dom["items"] = [i for i in dom.get("items", []) if i not in enlever]
        m["competences"] = [dom for dom in m.get("competences", []) if dom["items"]]
        m["competences_confirmees"] = True
    elif d["sujet"].startswith("moi-magazine:"):
        page = d["sujet"].split(":", 1)[1]
        texte = str(corps.get("texte") or d.get("texte") or "").strip()[:3000]
        m.setdefault("magazine", {})[page] = {"titre": d.get("titre", ""), "texte": texte}
    else:
        return
    _sauver(m)
