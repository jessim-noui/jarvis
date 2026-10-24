"""Mesure du temps de réponse de l'IA locale (profil jarvis-prive, via le routeur) sur 5 questions.
Usage : py -3 tests/mesure_local.py avant|apres [--froid]
--froid : décharge d'abord le modèle (comme après 5 min sans servir), pour mesurer aussi le premier appel.
Résultats ajoutés à donnees/mesure_local.json."""
import sys, json, time, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from commun import demander, DONNEES, lire_json, ecrire_json  # noqa: E402

QUESTIONS = ["Explique en 2 phrases ce qu'est un VLAN.",
             "Donne 3 conseils pour un entretien de technicien support.",
             "Écris un message de 3 lignes pour remercier un recruteur.",
             "Quelle est la différence entre TCP et UDP, en 2 phrases ?",
             "Classe ces tâches par urgence : répondre à un recruteur, lire une veille, faire un exercice. Réponds en JSON."]


def decharger():
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": "qwen3:14b", "keep_alive": 0}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    phase = sys.argv[1] if len(sys.argv) > 1 else "mesure"
    if "--froid" in sys.argv:
        decharger()
        time.sleep(2)
    res = []
    for q in QUESTIONS:
        t = time.time()
        try:
            msg, modele = demander("jarvis-prive", q, timeout=300, max_tokens=400)
            res.append({"q": q[:40], "s": round(time.time() - t, 1), "modele": modele,
                        "reflexion": "<think>" in (msg.get("content") or "") or bool(msg.get("reasoning_content"))})
        except Exception as e:
            res.append({"q": q[:40], "s": round(time.time() - t, 1), "modele": "", "erreur": type(e).__name__})
        print(res[-1])
    ok = [r["s"] for r in res if r.get("modele")]
    bilan = {"phase": phase, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "froid": "--froid" in sys.argv,
             "moyenne_s": round(sum(r["s"] for r in res) / len(res), 1), "erreurs": sum(1 for r in res if not r.get("modele")),
             "moyenne_reussies_s": round(sum(ok) / len(ok), 1) if ok else None, "details": res}
    tout = lire_json(DONNEES / "mesure_local.json", [])
    ecrire_json(DONNEES / "mesure_local.json", tout + [bilan])
    print({k: v for k, v in bilan.items() if k != "details"})
