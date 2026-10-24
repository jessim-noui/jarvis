r"""Historique des conversations avec Jarvis (mission 5) : site, équipe et Telegram, par jour, avec l'IA qui a répondu.
Tout reste sur le PC (donnees\historique.json). Les échanges d'avant la mission 5 viennent des souvenirs de la mémoire
(question et réponse gardées, l'IA n'était pas notée). Lecture seule pour la page.
"""
import time, sqlite3, threading
from commun import DONNEES, lire_json, ecrire_json, nom_ia

FICHIER = DONNEES / "historique.json"
_verrou = threading.Lock()


def noter(origine, question, r):
    """r = la réponse de jarvis.traiter / parler_a / equipe (dict). On garde la question et la réponse complètes, en local."""
    reponse = r.get("reponse") or r.get("synthese") or ""
    if r.get("agent") == "mails":  # jamais le contenu d'un mail dans l'historique
        reponse = "brouillon préparé" if "brouillon" in reponse.lower() else "mail lu"
    if r.get("avis"):
        r = {**r, "avis": [{**a, "texte": "mail lu"} if a.get("agent") == "mails" else a for a in r["avis"]]}
        reponse += "\n\n" + "\n".join(f"{a['agent_nom']} : {a.get('texte') or '—'}" for a in r["avis"])
    e = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "origine": origine, "agent": r.get("agent_nom") or r.get("agent") or "Jarvis",
         "ia": nom_ia(r.get("modele", "")), "question": str(question)[:4000], "reponse": reponse[:8000]}
    with _verrou:
        h = lire_json(FICHIER, [])
        h.append(e)
        ecrire_json(FICHIER, h[-3000:])


def anciens():
    """Les échanges d'avant (souvenirs « echange:… » de la mémoire)."""
    try:
        c = sqlite3.connect(DONNEES / "memoire.db")
        lignes = c.execute("select source, texte, t from souvenirs where source like 'echange:%' and source != 'echange:mails' order by t").fetchall()
        c.close()
    except Exception:
        return []
    out = []
    for source, texte, t in lignes:
        q, _, rep = (texte or "").partition("\nR : ")
        q = q.split(" : ", 1)[-1] if q.startswith("Q") else q
        out.append({"t": t or "", "origine": "avant (mémoire)", "agent": source.split(":", 1)[-1], "ia": "non notée",
                    "question": q.strip(), "reponse": rep.strip()})
    return out


def lister(recherche=""):
    tout = anciens() + lire_json(FICHIER, [])
    if recherche:
        r = recherche.lower()
        tout = [e for e in tout if r in e["question"].lower() or r in e["reponse"].lower() or r in e["agent"].lower()]
    tout.sort(key=lambda e: e["t"], reverse=True)
    jours = {}
    for e in tout[:600]:
        jours.setdefault(e["t"][:10] or "date inconnue", []).append(e)
    return {"jours": [{"jour": j, "echanges": l} for j, l in jours.items()], "total": len(tout)}
