r"""Mission 12 : les vraies données de l'arbre céleste (page Pilote). Rien de simulé.

- Agents : l'équipe de jarvis.py (+ Vidéo) ; consigne = leur rôle ; compétences = suite/skills_agents.json.
- IA : donnees/usage.json (30 jours) pour le profil de l'agent → modèle réellement utilisé, nombre d'appels, réussite.
- Tâches : le journal (début / fin) ; « en cours » = un début sans fin depuis moins de 5 min = un vrai travail envoyé par Jarvis
  (ou par le Directeur si une de ses missions tourne). Code : aussi les brouillons délégués par Claude (delegations.json).
- Chiffres du jour : usage.json d'aujourd'hui pour son profil.
"""
import collections, time
from commun import DONNEES, JOURNAL, lire_json

EN_COURS_MAX = 300


def _age(t):
    try:
        return time.time() - time.mktime(time.strptime(t, "%Y-%m-%dT%H:%M:%S"))
    except (TypeError, ValueError):
        return 1e9


def _nom_ia(modele):
    m = (modele or "").split("/")[-1]
    return m + (" (ton PC)" if (modele or "").startswith("ollama") else "")


def arbre():
    import jarvis
    from suite import directeur, skills_agents
    journal = lire_json(JOURNAL, [])
    usage = lire_json(DONNEES / "usage.json", [])
    table = skills_agents.table()
    aujourdhui = time.strftime("%Y-%m-%d")
    mission = next((m for m in directeur.tableau()["missions"] if m.get("etat") == "running"), None)
    ouverts = {}
    for e in journal:
        if e.get("etat") == "debut":
            ouverts[e.get("id")] = e
        elif e.get("etat") == "fin":
            ouverts.pop(e.get("id"), None)
    agents = []
    for ident in [*jarvis.EQUIPE, "video"]:
        profil = jarvis.AGENTS.get(ident, {}).get("profil", "")
        u = [x for x in usage if profil and x.get("profil") == profil]
        par_ia = collections.defaultdict(lambda: [0, 0])
        for x in u:
            r = par_ia[_nom_ia(x.get("modele"))]
            r[0] += 1
            r[1] += not x.get("erreur")
        ias = sorted(([n, a, f"{round(100 * ok / a)} %"] for n, (a, ok) in par_ia.items() if n), key=lambda r: -r[1])[:4]
        cours = next((e for e in ouverts.values() if e.get("agent") == ident and _age(e.get("t")) < EN_COURS_MAX), None)
        taches = []
        if cours:
            taches.append([cours["t"][11:16], cours.get("action", ""), "en cours", _nom_ia(cours.get("modele"))])
        for e in reversed(journal):
            if len(taches) >= 5:
                break
            if e.get("agent") == ident and e.get("etat") != "debut":
                quand = e["t"][11:16] if e.get("t", "").startswith(aujourdhui) else e.get("t", "")[8:10] + "/" + e.get("t", "")[5:7]
                taches.append([quand, " ".join((e.get("resume") or e.get("action") or "").replace("`", "").replace("**", "").split())[:90],
                               "erreur" if e.get("statut") == "erreur" else "fini", _nom_ia(e.get("modele"))])
        if ident == "code":
            for d in reversed(lire_json(DONNEES / "delegations.json", [])[-2:]):
                taches.append([d.get("t", "")[8:10] + "/" + d.get("t", "")[5:7], "Brouillon " + d.get("sortie", ""), "fini (pour Claude)",
                               _nom_ia(d.get("modele"))])
        jour = [x for x in u if str(x.get("t", "")).startswith(aujourdhui)]
        duree = [x.get("duree") or 0 for x in jour]
        etat = "travail" if cours else ("erreur" if taches and taches[0][2] == "erreur" else "repos")
        agents.append({
            "id": ident, "nom": jarvis.NOMS.get(ident, ident), "etat": etat,
            "tache": cours.get("action", "") if cours else (f"A fini : {taches[0][1]}" if taches else "Libre"),
            "de": ((f"Directeur · mission « {mission['titre']} »" if mission else "Jarvis") + f" · il y a {round(_age(cours['t']))} s") if cours else "",
            "prompt": jarvis.ROLES.get(ident) or jarvis.AGENTS.get(ident, {}).get("role", ""),
            "profil": profil, "partage": [a for a in jarvis.EQUIPE if a != ident and profil and jarvis.AGENTS.get(a, {}).get("profil") == profil],
            "ias": ias, "taches": taches, "skills": table.get(ident, []) + table.get("tous", []),
            "stats": [["appels aujourd'hui", str(len(jour))],
                      ["tokens", f"{round(sum((x.get('tokens_entree') or 0) + (x.get('tokens_sortie') or 0) for x in jour) / 1000)} k"],
                      ["temps moyen", f"{sum(duree) / len(duree):.1f} s".replace(".", ",") if duree else "—"],
                      ["erreurs", str(sum(1 for x in jour if x.get("erreur")))]]})
    return {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "agents": agents}
