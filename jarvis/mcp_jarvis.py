r"""Serveur MCP de Jarvis (SDK MCP officiel, transport stdio).

Il expose les agents de Jarvis à un client MCP comme Claude Code : `claude mcp add jarvis -- py -3 jarvis\mcp_jarvis.py`
Outils : offres_du_jour, propositions_veille, demander_jarvis, etat_quotas.
Volontairement AUCUN outil d'envoi de mail, d'installation ni d'acceptation : ces actions restent des clics de l’utilisateur.
Le client MCP est une IA en ligne : rien de privé (mails, mémoire privée) ne lui est renvoyé.
"""
import sys, contextlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcp.server import MCPServer  # noqa: E402

mcp = MCPServer("jarvis", instructions="Les agents de Jarvis : offres d'emploi notées, veille et quotas. "
                                       "Lecture seule, sauf demander_jarvis qui délègue une question au chef d'orchestre.")


@contextlib.contextmanager
def silence():
    """En stdio, tout print parasite casserait le protocole : on redirige vers stderr."""
    with contextlib.redirect_stdout(sys.stderr):
        yield


@mcp.tool()
def offres_du_jour(nombre: int = 10, score_min: int = 0) -> list[dict]:
    """Les meilleures offres d'emploi déjà notées par l'IA (scripts Adzuna / France Travail), triées par score."""
    with silence():
        import serveur
        offres = serveur.offres()["offres"]
    import offres as mod_offres
    garde = ("score", "titre", "entreprise", "ville", "contrat", "experience", "experience_phrase", "salaire", "lien", "region", "nouvelle")
    return [{k: o.get(k) for k in garde} for o in mod_offres.pour_toi(offres) if (o.get("score") or 0) >= score_min][:max(1, min(nombre, 50))]


@mcp.tool()
def propositions_veille(toutes: bool = False) -> list[dict]:
    """Les fiches de la veille (par défaut : seulement celles qui attendent une décision de l’utilisateur)."""
    with silence():
        from commun import DONNEES, lire_json
        props = lire_json(DONNEES / "propositions.json", {}).get("propositions", [])
    garde = ("titre", "lien", "pour_toi", "categorie", "risque", "risque_raison", "effort", "avis", "statut", "date")
    return [{k: p.get(k) for k in garde} for p in props if toutes or p.get("statut") == "nouvelle"][:30]


@mcp.tool()
def demander_jarvis(question: str) -> dict:
    """Pose une question à Jarvis : il choisit l'agent (code, rédaction, emploi, veille…) et l'IA adaptée."""
    with silence():
        import jarvis
        r = jarvis.traiter(question[:4000], origine="mcp", conversation="mcp")
    if r["agent"] == "mails":  # le contenu des mails ne quitte pas le PC
        return {"agent": "mails", "reponse": "Les mails sont privés : ouvre le jeu (l'ordinateur) sur le PC de l’utilisateur.", "modele": "local"}
    return {"agent": r["agent"], "reponse": r["reponse"], "modele": r["modele"]}


@mcp.tool()
def etat_quotas(jours: int = 1) -> dict:
    """Appels, tokens et erreurs par fournisseur d'IA sur les N derniers jours, et état de l'arrêt d'urgence."""
    with silence():
        from commun import resume_usage, arret_actif
        return {"jours": jours, "par_fournisseur": resume_usage(max(1, min(jours, 30))), "arret_urgence": arret_actif()}


if __name__ == "__main__":
    mcp.run("stdio")
