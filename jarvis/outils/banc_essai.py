r"""Mission 16 : le banc d'essai de l’utilisateur (donnees\questions_test.json) posé au VRAI serveur (127.0.0.1:4100).
Pour chaque question : temps total, étape mémoire et IA (lus dans la trace), réponse juste ou non.
Brouillon de mistral-code-latest (deleguer.py), relu et corrigé par Claude.

Usage : py -3 outils\banc_essai.py [--ids a,b] [--sortie resultats.json]
"""
import argparse, json, statistics, sys, threading, time, unicodedata, urllib.error, urllib.request, uuid
from pathlib import Path

DONNEES = Path(__file__).resolve().parent.parent / "donnees"
URL = "http://127.0.0.1:4100/demander"


def normaliser(texte):
    """Minuscules, sans accents (« écrit » → « ecrit »), apostrophes droites."""
    texte = unicodedata.normalize("NFKD", (texte or "").lower().replace("’", "'"))
    return "".join(c for c in texte if not unicodedata.combining(c))


def juste(reponse, q, interdit_debut):
    r = normaliser(reponse).strip()
    return (any(normaliser(a) in r for a in q["attendu"])
            and not any(r.startswith(normaliser(i)) for i in interdit_debut)
            and not any(normaliser(i) in r for i in q.get("interdit_contenu", [])))


def poser(question, delai=300):
    """Renvoie (données JSON de la réponse, identifiant de trace, secondes)."""
    ident = uuid.uuid4().hex[:8]
    req = urllib.request.Request(URL, json.dumps({"question": question, "trace": ident}).encode(),
                                 {"Content-Type": "application/json", "Origin": "http://127.0.0.1:4100"}, method="POST")
    debut = time.time()
    try:
        with urllib.request.urlopen(req, timeout=delai) as r:
            d = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        d = {"erreur": f"HTTP {e.code} " + e.read(300).decode("utf-8", "replace")}
    except Exception as e:  # délai, serveur éteint
        d = {"erreur": type(e).__name__}
    return d, ident, round(time.time() - debut, 2)


def signaler_presence():
    """--present : comme une page ouverte et visible (sinon Jarvis est « en pause » et Ollama ne s'allume jamais)."""
    def boucle():
        while True:
            try:
                urllib.request.urlopen(urllib.request.Request(URL.replace("/demander", "/site/ouvert"),
                                       json.dumps({"onglet": "banc", "visible": True}).encode(),
                                       {"Content-Type": "application/json", "Origin": "http://127.0.0.1:4100"}, method="POST"), timeout=10)
            except Exception:
                pass
            time.sleep(20)
    threading.Thread(target=boucle, daemon=True).start()
    time.sleep(1)


def etapes(ident):
    t = next((t for t in json.loads((DONNEES / "traces.json").read_text(encoding="utf-8")) if t.get("id") == ident), None)
    if not t:
        return None, None, ""
    memoire = next((e["s"] for e in t["etapes"] if e["nom"] == "mémoire"), None)
    ia = round(sum(e.get("duree", 0) for e in t["etapes"] if e["nom"] == "ia"), 2)
    chemin = next((e.get("chemin", "") for e in t["etapes"] if e["nom"] == "chemin"), "")
    return memoire, ia, chemin


REFERENCE = DONNEES / "banc-reference.json"


def verifier_regression():
    """Étape 9 : après un changement de consigne, d'IA ou d'aiguillage (redemarrer_serveur.py), le banc repasse — seulement les
    questions répondues par le code (rapides, sans IA). Moins de justes que la référence = régression : le changement est annulé.
    Renvoie (ok, phrase)."""
    data = json.loads((DONNEES / "questions_test.json").read_text(encoding="utf-8"))
    qs = [q for q in data["questions"] if str(q.get("outil", "")).startswith("code:") or q["id"] == "age"]
    justes = sorted(q["id"] for q in qs if juste((poser(q["question"], 30)[0].get("reponse") or ""), q, data["interdit_debut"]))
    ref = json.loads(REFERENCE.read_text(encoding="utf-8")) if REFERENCE.exists() else None
    if ref is None or len(justes) >= len(ref["justes"]):
        REFERENCE.write_text(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M"), "justes": justes}, ensure_ascii=False), encoding="utf-8")
        return True, f"banc d'essai : {len(justes)}/{len(qs)} justes"
    perdues = sorted(set(ref["justes"]) - set(justes))
    return False, f"banc d'essai en recul : {len(justes)}/{len(qs)} justes au lieu de {len(ref['justes'])} (perdu : {', '.join(perdues)})"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ids", default="")
    p.add_argument("--sortie", default="")
    p.add_argument("--present", action="store_true")
    a = p.parse_args()
    if a.present:
        signaler_presence()
    data = json.loads((DONNEES / "questions_test.json").read_text(encoding="utf-8"))
    ids = set(filter(None, a.ids.split(",")))
    res = []
    for q in data["questions"]:
        if ids and q["id"] not in ids:
            continue
        d, ident, total = poser(q["question"])
        texte = d.get("reponse") or d.get("erreur") or ""
        memoire, ia, chemin = etapes(ident)
        res.append({"id": q["id"], "question": q["question"], "total": total, "memoire": memoire, "ia": ia, "chemin": chemin,
                    "max_s": q["max_s"], "juste": "erreur" not in d and juste(texte, q, data["interdit_debut"]),
                    "debut_reponse": " ".join(texte.split())[:100]})
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("| Question | Mémoire | IA | Total | Juste | Début de la réponse |\n|---|---|---|---|---|---|")
    for r in res:
        print(f"| {r['question']} | {r['memoire']} | {r['ia']} | {r['total']} s | {'oui' if r['juste'] else 'NON'} | {r['debut_reponse'][:60]} |")
    if res:
        totaux = sorted(r["total"] for r in res)
        print(f"\nBilan : {sum(r['juste'] for r in res)}/{len(res)} justes · médiane {statistics.median(totaux)} s · max {totaux[-1]} s"
              f" · dans le temps max : {sum(r['total'] <= r['max_s'] for r in res)}/{len(res)}")
    if a.sortie:
        Path(a.sortie).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
