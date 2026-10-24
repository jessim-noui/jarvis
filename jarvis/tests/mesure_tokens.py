"""Mesure des tokens par question : sans mémoire / historique complet (calculé) / avec la mémoire de Jarvis.
Usage : py -3 tests\\mesure_tokens.py   (fait de vrais appels au routeur ; résultat dans donnees\\mesure_tokens.json)
"""
import sys, time, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jarvis, memoire_db  # noqa: E402
from commun import USAGE, DONNEES, lire_json, ecrire_json  # noqa: E402

QUESTIONS = [
    "Quelles offres d'emploi à Grenoble valent le coup en priorité ?",
    "Et parmi elles, laquelle propose du télétravail ?",
    "Écris un message court pour relancer une entreprise une semaine après ma candidature.",
    "Rends-le un peu plus chaleureux.",
    "Comment je vérifie en PowerShell qu'un port est ouvert sur mon PC ?",
    "Et pour le port 4100 précisément ?",
]


def tokens_depuis(t0):
    u = [e for e in lire_json(USAGE, []) if e["t"] >= t0]
    cloud = [e for e in u if e["fournisseur"] != "ollama_chat"]
    return (sum(e["tokens_entree"] for e in cloud), sum(e["tokens_sortie"] for e in cloud), len(u),
            sum(e["tokens_entree"] for e in u if e["fournisseur"] == "ollama_chat"))


def scenario(avec_memoire, conv):
    lignes, historique = [], 0
    for q in QUESTIONS:
        t0 = time.strftime("%Y-%m-%dT%H:%M:%S")
        time.sleep(1.1)
        r = jarvis.traiter(q, conversation=conv, avec_memoire=avec_memoire)
        time.sleep(12)  # laisse finir la mise à jour du résumé (en arrière-plan) : elle compte dans le coût
        entree, sortie, appels, local = tokens_depuis(t0)
        lignes.append({"question": q, "agent": r["agent"], "tokens_entree": entree, "tokens_sortie": sortie,
                       "tokens_locaux": local,
                       "appels": appels, "tokens_memoire": r.get("tokens_memoire", 0),
                       "historique_si_tout_renvoye": historique})
        historique += memoire_db.tokens(q) + memoire_db.tokens(r["reponse"])
    return lignes


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    import sqlite3
    with memoire_db.connexion() as c:
        c.execute("DELETE FROM resumes WHERE conversation LIKE 'mesure-%'")
    ancien = lire_json(DONNEES / "mesure_tokens.json", {})
    sans = ancien["sans_memoire"]["detail"] if "--avec-seulement" in sys.argv else scenario(False, "mesure-sans")
    avec = scenario(True, "mesure-avec")
    moy = lambda l, k: round(sum(x[k] for x in l) / len(l))
    res = {
        "date": time.strftime("%Y-%m-%d %H:%M"),
        "sans_memoire": {"moyenne_tokens_entree": moy(sans, "tokens_entree"), "detail": sans},
        "historique_complet_estime": {"moyenne_tokens_entree": moy(sans, "tokens_entree") + moy(sans, "historique_si_tout_renvoye") * 2,
                                      "note": "sans mémoire + tout l'historique renvoyé au chef ET à l'agent (2 appels)",
                                      "a_20_questions": moy(sans, "tokens_entree") + 2 * 20 * 300},
        "avec_memoire": {"moyenne_tokens_entree": moy(avec, "tokens_entree"),
                         "moyenne_tokens_memoire_injectes": moy(avec, "tokens_memoire"),
                         "moyenne_tokens_locaux_gratuits": moy(avec, "tokens_locaux"), "detail": avec},
        "premiere_mesure_avant_optimisation": ancien.get("avec_memoire", {}).get("moyenne_tokens_entree"),
    }
    ecrire_json(DONNEES / "mesure_tokens.json", res)
    for nom in ("sans_memoire", "historique_complet_estime", "avec_memoire"):
        print(nom, res[nom]["moyenne_tokens_entree"])
    for a, b in zip(sans, avec):
        print(f"{a['agent']:10} sans={a['tokens_entree']:6} avec={b['tokens_entree']:6} (mémoire {b['tokens_memoire']}) | {a['question'][:45]}")
