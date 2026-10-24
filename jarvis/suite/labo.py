r"""Mission 9 — Le Laboratoire : Jarvis PROUVE qu'une idée est meilleure au lieu de l'affirmer.

Une expérience compare une version actuelle (« référence ») et une variante (autre IA, autre consigne, autre limite)
sur le MÊME petit jeu de tâches (suite\labo_taches.json : des tâches inventées, aucune donnée perso, aucun envoi).
On mesure : réussite (vérifications écrites AVANT le test), temps, tokens, erreurs ; et on liste les tâches où la
variante est MOINS bonne. Avec peu d'essais, la confiance reste « faible » : on ne prétend pas à de la science.

Le labo ne change jamais la version active. S'il gagne, il fabrique un « patch candidat » sur suite\reglages.json,
qui passe ensuite par la politique (politique.py) : intégré seul si c'est un simple réglage et que les tests passent.
"""
import difflib, json, re, sys, threading, time, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import DONNEES, lire_json, ecrire_json, journaliser, arret_actif  # noqa: E402

ICI = Path(__file__).resolve().parent
TACHES = ICI / "labo_taches.json"
REGLAGES = ICI / "reglages.json"
EXPERIENCES = DONNEES / "labo.json"
_annuler = set()
_verrou = threading.Lock()
LIMITE_SECONDES = 600
LIMITE_APPELS = 40
BATTERIES = {"rapide": (2, 1), "regulier": (4, 1), "complet": (8, 1)}


def options_batteries():
    """Niveaux prédéfinis ; chaque paire tâche/répétition appelle les deux variantes."""
    catalogue = [t for t in lire_json(TACHES, []) if isinstance(t, dict) and t.get("id")]
    return [{"id": nom, "taches": min(nb, len(catalogue)), "repetitions": repetitions,
             "appels": min(nb, len(catalogue)) * repetitions * 2,
             "appels_avec_equipe": min(nb, len(catalogue)) * repetitions * 4}
            for nom, (nb, repetitions) in BATTERIES.items()]


def verifier(texte, verifs):
    """Vérifications fixées à l'avance. Renvoie (ok, [raisons des échecs])."""
    t = texte or ""
    rate = []
    for v in verifs:
        k, val = v.get("type"), v.get("valeur")
        if k not in {"contient", "ne_contient_pas", "max_mots", "min_mots", "regex", "json"}:
            rate.append(f"vérification inconnue ({k or 'sans type'})")
            continue
        if k == "contient" and str(val).lower() not in t.lower():
            rate.append(f"ne contient pas « {val} »")
        elif k == "ne_contient_pas" and str(val).lower() in t.lower():
            rate.append(f"contient « {val} »")
        elif k == "max_mots" and len(t.split()) > int(val):
            rate.append(f"trop long ({len(t.split())} mots > {val})")
        elif k == "min_mots" and len(t.split()) < int(val):
            rate.append(f"trop court ({len(t.split())} mots)")
        elif k == "regex" and not re.search(str(val), t, re.I | re.S):
            rate.append(f"forme attendue absente ({val})")
        elif k == "json":
            try:
                json.loads(re.sub(r"^```(json)?|```$", "", t.strip()).strip())
            except ValueError:
                rate.append("JSON invalide")
    return (not rate), rate


def appeler_routeur(variante, consigne):
    """Appel réel par le routeur (commun.demander). Renvoie (texte, modèle, tokens, durée, erreur)."""
    from commun import demander, USAGE
    t = time.time()
    try:
        if variante.get("equipe"):
            avis, modeles, tokens = [], [], 0
            systeme = "Réponds uniquement à la consigne de test, sans consulter ni utiliser de données du PC. " + variante.get("systeme", "")
            for profil, role in (("jarvis-rapide", "Réponse indépendante"), ("jarvis-code", "Relecture indépendante")):
                msg, modele = demander(profil, [{"role": "system", "content": f"{role}. {systeme}"},
                                                {"role": "user", "content": consigne}],
                                       max_tokens=int(variante.get("max_tokens", 500)), temperature=float(variante.get("temperature", 0.2)))
                u = (lire_json(USAGE, []) or [{}])[-1]
                tokens += u.get("tokens_entree", 0) + u.get("tokens_sortie", 0)
                avis.append(msg.get("content") or "")
                modeles.append(modele)
            msg, modele = demander("jarvis", [{"role": "system", "content": "Tu es le synthétiseur. N'utilise que les avis reçus, suis la consigne de test et n'ajoute aucune donnée. " + systeme},
                                              {"role": "user", "content": f"Consigne : {consigne}\nAvis :\n- " + "\n- ".join(avis)}],
                                   max_tokens=int(variante.get("max_tokens", 500)), temperature=float(variante.get("temperature", 0.2)))
            u = (lire_json(USAGE, []) or [{}])[-1]
            tokens += u.get("tokens_entree", 0) + u.get("tokens_sortie", 0)
            return msg.get("content") or "", "+".join([*modeles, modele]), tokens, time.time() - t, ""
        msgs = ([{"role": "system", "content": variante["systeme"]}] if variante.get("systeme") else []) + [{"role": "user", "content": consigne}]
        msg, modele = demander(variante["profil"], msgs, max_tokens=int(variante.get("max_tokens", 500)),
                               temperature=float(variante.get("temperature", 0.2)))
        u = (lire_json(USAGE, []) or [{}])[-1]
        return msg.get("content") or "", modele, u.get("tokens_entree", 0) + u.get("tokens_sortie", 0), time.time() - t, ""
    except Exception as e:
        return "", "", 0, time.time() - t, type(e).__name__


def nouvelle(question, hypothese, reference, variante, taches=None, repetitions=1, metriques=None, batterie=None):
    """Crée l'expérience (état « en_attente »). Les métriques sont fixées ici, avant tout résultat."""
    catalogue = [t["id"] for t in lire_json(TACHES, []) if isinstance(t, dict) and t.get("id")]
    disponibles = set(catalogue)
    if batterie is not None:
        if batterie not in BATTERIES:
            raise ValueError("Batterie inconnue : choisir rapide, regulier ou complet.")
        nb, repetitions = BATTERIES[batterie]
        taches = catalogue[:nb]
    taches = list(dict.fromkeys(taches or catalogue))
    if not taches:
        raise ValueError("Aucune tâche de test n'est définie.")
    inconnues = [tid for tid in taches if not isinstance(tid, str) or tid not in disponibles]
    if inconnues:
        raise ValueError("Tâche(s) de test inconnue(s) : " + ", ".join(str(tid)[:60] for tid in inconnues[:5]))
    repetitions = max(1, min(5, int(repetitions)))
    appels_prevus = len(taches) * repetitions * (int(reference.get("appels", 1)) + int(variante.get("appels", 1)))
    if appels_prevus > LIMITE_APPELS:
        raise ValueError(f"Cette comparaison dépasserait la limite de {LIMITE_APPELS} appels (prévision : {appels_prevus}).")
    e = {"id": "x-" + uuid.uuid4().hex[:8], "question": question[:200], "hypothese": hypothese[:300],
         "reference": reference, "variante": variante, "taches": taches, "repetitions": repetitions,
         "batterie": batterie,
         "metriques": metriques or ["reussite", "temps", "tokens", "erreurs"], "etat": "en_attente",
         "cree": time.strftime("%Y-%m-%dT%H:%M:%S"), "resultats": [], "resume": {}, "decision": ""}
    with _verrou:
        d = lire_json(EXPERIENCES, [])
        d.append(e)
        ecrire_json(EXPERIENCES, d[-50:])
    return e


def _sauver(e):
    with _verrou:
        d = lire_json(EXPERIENCES, [])
        ecrire_json(EXPERIENCES, [e if x["id"] == e["id"] else x for x in d])


def annuler(ident):
    _annuler.add(ident)


def lancer(ident, appeler=appeler_routeur):
    """Exécute l'expérience (référence puis variante, tâche par tâche), dans la limite de temps et d'appels."""
    e = next((x for x in lire_json(EXPERIENCES, []) if x["id"] == ident), None)
    if not e or e["etat"] not in ("en_attente", "bloquee"):
        return e
    taches = {t["id"]: t for t in lire_json(TACHES, [])}
    e["etat"], debut, appels = "en_cours", time.time(), 0
    _sauver(e)
    for rep in range(e["repetitions"]):
        for tid in e["taches"]:
            t = taches.get(tid)
            if not t:
                e["etat"] = "bloquee"
                e["resume"] = resumer(e)
                e["resume"]["arret"] = f"tâche de test absente : {tid}"
                _sauver(e)
                return e
            for cote in ("reference", "variante"):
                deja_fait = any(r.get("tache") == tid and r.get("rep") == rep and r.get("cote") == cote for r in e["resultats"])
                if deja_fait:
                    continue
                appels_cote = max(1, int(e[cote].get("appels", 1)))
                __import__("presence").attendre()  # mission 11 : en pause quand l’utilisateur n'est pas là
                if ident in _annuler or arret_actif():
                    e["etat"] = "annulee"
                    _sauver(e)
                    return e
                if time.time() - debut > LIMITE_SECONDES or appels + appels_cote > LIMITE_APPELS:
                    e["etat"] = "bloquee"
                    e["resume"] = resumer(e)
                    e["resume"]["arret"] = "limite de temps ou d'appels atteinte"
                    _sauver(e)
                    return e
                texte, modele, tokens, duree, err = appeler(e[cote], t["consigne"])
                appels += appels_cote
                ok, raisons = (False, [f"erreur : {err}"]) if err else verifier(texte, t.get("verifs", []))
                e["resultats"].append({"tache": tid, "rep": rep, "cote": cote, "ok": ok, "raisons": raisons, "modele": modele,
                                       "appels": appels_cote, "tokens": tokens, "duree": round(duree, 2), "erreur": err, "extrait": texte[:200]})
    e["etat"] = "terminee"
    e["resume"] = resumer(e)
    e["decision"] = e["resume"]["recommandation"]
    _sauver(e)
    journaliser(agent="jarvis", action="labo", etat="info", statut="ok", resume=f"{e['question'][:80]} → {e['decision']}")
    return e


def resumer(e):
    def stats(cote):
        r = [x for x in e["resultats"] if x["cote"] == cote]
        n = len(r) or 1
        return {"essais": len(r), "appels": sum(x.get("appels", 1) for x in r),
                "reussite": round(100 * sum(x["ok"] for x in r) / n), "temps": round(sum(x["duree"] for x in r) / n, 2),
                "tokens": round(sum(x["tokens"] for x in r) / n), "tokens_total": sum(x["tokens"] for x in r),
                "erreurs": sum(bool(x["erreur"]) for x in r)}
    a, b = stats("reference"), stats("variante")
    par_tache = {}
    for x in e["resultats"]:
        par_tache.setdefault(x["tache"], {"reference": [], "variante": []})[x["cote"]].append(x["ok"])
    gagne, perd = [], []
    for tid, v in par_tache.items():
        ra, rb = sum(v["reference"]) / max(1, len(v["reference"])), sum(v["variante"]) / max(1, len(v["variante"]))
        (gagne if rb > ra else perd if rb < ra else []).append(tid)
    n = min(a["essais"], b["essais"])
    confiance = "faible" if n < 10 else "moyenne" if n < 30 else "bonne"
    mieux = (b["reussite"] >= a["reussite"] + 10) or (b["reussite"] >= a["reussite"] and
                                                     (b["temps"] <= 0.8 * a["temps"] or b["tokens"] <= 0.8 * a["tokens"]))
    if perd and not mieux:
        reco = "ignorer"
    elif mieux and not perd:
        reco = "adopter" if confiance != "faible" else "retester (gain vu, mais peu d'essais)"
    elif mieux:
        reco = "modifier (meilleure en moyenne, mais régresse sur certaines tâches)"
    else:
        reco = "ignorer (pas de gain mesuré)"
    return {"reference": a, "variante": b, "gagne_sur": gagne, "regresse_sur": perd, "confiance": confiance, "recommandation": reco}


def patch_reglages(chemin_cle, valeur, titre):
    """Fabrique le diff git qui changerait suite\reglages.json (ex. ("telegram", "profil") → "jarvis-rapide").
    Le diff n'est PAS appliqué ici : il part dans boucle.traiter_proposition (bac à sable + politique)."""
    avant = REGLAGES.read_text(encoding="utf-8") if REGLAGES.exists() else "{}\n"
    d = json.loads(avant)
    cur = d
    for k in chemin_cle[:-1]:
        cur = cur.setdefault(k, {})
    cur[chemin_cle[-1]] = valeur
    apres = json.dumps(d, ensure_ascii=False, indent=2) + "\n"
    rel = "jarvis/suite/reglages.json"
    lignes = list(difflib.unified_diff(avant.splitlines(True), apres.splitlines(True), f"a/{rel}", f"b/{rel}"))
    return f"diff --git a/{rel} b/{rel}\n" + "".join(lignes), titre


def experiences():
    return list(reversed(lire_json(EXPERIENCES, [])))
