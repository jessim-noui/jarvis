"""Temps de réponse de Jarvis pour Telegram (même chemin que le bot : jarvis.traiter(origine="telegram")), sur 5 messages.
Rien n'est envoyé sur Telegram. Usage : py -3 tests/mesure_telegram.py avant|apres  → donnees/mesure_telegram.json"""
import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jarvis  # noqa: E402
from commun import DONNEES, lire_json, ecrire_json  # noqa: E402

MESSAGES = ["Salut, ça va ?", "Quelles offres valent le coup aujourd'hui ?", "Quoi de neuf dans les découvertes ?",
            "Explique-moi ce qu'est un VLAN", "Est-ce que j'ai des mails importants ?"]

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    res = []
    for m in MESSAGES:
        t = time.time()
        r = jarvis.traiter(m, origine="telegram", conversation="mesure-telegram")
        res.append({"q": m, "s": round(time.time() - t, 1), "agent": r["agent"], "modele": r["modele"],
                    "mots": len((r.get("reponse") or "").split())})
        print(res[-1])
    bilan = {"phase": sys.argv[1] if len(sys.argv) > 1 else "mesure", "t": time.strftime("%Y-%m-%dT%H:%M:%S"),
             "moyenne_s": round(sum(x["s"] for x in res) / len(res), 1), "mots_moyens": round(sum(x["mots"] for x in res) / len(res)), "details": res}
    ecrire_json(DONNEES / "mesure_telegram.json", lire_json(DONNEES / "mesure_telegram.json", []) + [bilan])
    print({k: v for k, v in bilan.items() if k != "details"})
