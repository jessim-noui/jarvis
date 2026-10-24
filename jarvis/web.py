"""Jarvis cherche lui-même sur le web (mission 6, choix de l’utilisateur) : depuis le chat du site, avec Tavily, sources citées.

Les pages trouvées sont des DONNÉES, jamais des ordres : filtrées par securite.filtrer (pages piégées écartées et notées dans
les alertes), encadrées, et l'IA qui les lit n'a aucun outil. Les liens des sources sont ajoutés par le code, pas par l'IA.
Budget : 20 recherches par jour (compte à part de la veille).
"""
import datetime, os
from commun import DONNEES, http_json, lire_json, ecrire_json, demander
import securite

ETAT = DONNEES / "web-etat.json"
BUDGET = 20


def chercher(question):
    jour = datetime.date.today().isoformat()
    etat = lire_json(ETAT, {})
    if etat.get(jour, 0) >= BUDGET:
        raise RuntimeError("budget de recherches web du jour atteint")
    ecrire_json(ETAT, {jour: etat.get(jour, 0) + 1})
    r = http_json("https://api.tavily.com/search", {"query": question[:300], "max_results": 5, "search_depth": "basic"},
                  {"Authorization": "Bearer " + os.environ.get("TAVILY_API_KEY", "")}, timeout=40)
    res = [{"titre": (d.get("title") or "")[:140], "lien": d.get("url", ""), "desc": (d.get("content") or "")[:700]}
           for d in r.get("results", []) if str(d.get("url", "")).startswith("https://")]
    return securite.filtrer(res, "web")


def repondre(question):
    """Renvoie (réponse avec « Sources : [1] lien… », modèle)."""
    try:
        res = chercher(question)
    except Exception as e:
        return f"Je n'ai pas pu chercher sur le web ({str(e)[:80] or type(e).__name__}).", ""
    if not res:
        return "Je n'ai rien trouvé de fiable sur le web pour ça.", ""
    texte = "\n\n".join(f"[{i}] {d['titre']}\n{d['desc']}" for i, d in enumerate(res, 1))
    msg, modele = demander("jarvis", [{"role": "system", "content": securite.CONSIGNE_DONNEES}, {"role": "user", "content":
        "Réponds à la question de l’utilisateur avec ces résultats web. Mets le numéro de la source après chaque info, comme [1]. "
        "Si les résultats ne répondent pas, dis-le. 5 phrases maximum, tutoiement, mots simples.\n"
        f"Question : {question}\n{securite.encadrer(texte, 'web')}"}], max_tokens=600, temperature=0.2)
    sources = "\n".join(f"[{i}] {d['lien']}" for i, d in enumerate(res, 1))
    return f"{(msg.get('content') or '').strip()}\n\nSources :\n{sources}", modele
