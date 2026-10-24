r"""Mission 16, étape 3 : quelles IA des chaînes gèrent bien l'appel d'outils ? (Labo)
Pour chaque IA : 4 questions qui exigent un outil précis ; on note si elle appelle le BON outil, et en combien de temps.
Résultat dans donnees\labo-outils.json. Usage : py -3 outils\labo_outils.py [e-nemotron-ultra e-gemini-flash ...]
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from commun import DONNEES, ecrire_json, demander  # noqa: E402
import jarvis, outils_chef  # noqa: E402

CAS = [("quelles sont mes compétences réseau ?", "moi"), ("combien d'offres support dans ma zone ?", "offres"),
       ("que dit la ligne 20 de commun.py ?", "lire_code"), ("qu'as-tu fait seul aujourd'hui ?", "journal")]
IA = sys.argv[1:] or ["e-nemotron-ultra", "e-gemini-flash", "e-nemotron-super", "e-gpt-oss-120b", "e-qwen-groq", "e-mistral-medium"]


def main():
    outils = jarvis.OUTILS_CHEF + outils_chef.OUTILS
    res = {}
    for ia in IA:
        bons, temps = 0, []
        for q, attendu in CAS:
            t = time.time()
            try:
                msg, _ = demander(ia, [{"role": "system", "content": jarvis.SYSTEME_CHEF}, {"role": "user", "content": q}],
                                  tools=outils, tool_choice="auto", max_tokens=400, timeout=40)
                noms = [a["function"]["name"] for a in msg.get("tool_calls") or []]
            except Exception as e:  # noqa: BLE001
                noms = [f"erreur {type(e).__name__}"]
            temps.append(round(time.time() - t, 1))
            time.sleep(4)  # quotas gratuits : pas de rafale (sinon le routeur met les IA en pause 60 s)
            bons += attendu in noms
            print(f"{ia:20} {q[:40]:40} → {noms} ({temps[-1]} s)", flush=True)
        res[ia] = {"bons": bons, "sur": len(CAS), "temps_median": sorted(temps)[len(temps) // 2]}
    ecrire_json(DONNEES / "labo-outils.json", {"t": time.strftime("%Y-%m-%dT%H:%M"), "resultats": res})
    for ia, r in sorted(res.items(), key=lambda x: (-x[1]["bons"], x[1]["temps_median"])):
        print(f"{ia}: {r['bons']}/{r['sur']} bons outils, médiane {r['temps_median']} s")


if __name__ == "__main__":
    main()
