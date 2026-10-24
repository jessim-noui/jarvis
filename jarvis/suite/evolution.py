r"""Mission 8 (étape 6 de la version longue) — Faire évoluer Jarvis sans dupliquer l'existant. Tout est lancé À LA MAIN
(un bouton du site), limité (budget de requêtes et d'appels), observable, et s'arrête à la fin. Aucune veille permanente.

A. recherche_ciblee : une question → les sources adaptées (web officiel et bonnes pratiques par Tavily = web.py, dépôts
   GitHub, nouveautés des catalogues de modèles = maj_modeles) → 3 pistes au plus, chacune avec le problème visé, le bénéfice,
   la fiabilité des sources, la difficulté, les risques, comment tester, et les LIENS (ajoutés par le code, pas par l'IA).
B. verifier_competence / tester_competence : une compétence (skill) d'un dépôt GitHub est LUE (jamais exécutée : licence,
   scripts, dépendances, nouveauté par rapport aux skills déjà là), puis TESTÉE au Labo (mêmes tâches inventées, avec et sans
   ses instructions). Registre de Découvertes 2.0 : découverte → vérifiée → testée → validée/intégrée (ces deux-là : l’utilisateur).
C. comparer_modeles : quelques modèles DU ROUTEUR (noms e-…, aucun changement de config.yaml) contre le profil utilisé
   aujourd'hui, sur 2 tâches du type choisi (Labo). Les essais sont gardés : un même essai de moins de 7 jours n'est pas refait.
D. audit_profils : le choix des IA par tâche, tel qu'il marche vraiment (chaînes de config.yaml + chiffres de usage.json),
   avec les manques repérés. Rien n'est changé automatiquement.
"""
import base64, difflib, re, sys, threading, time, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA, DONNEES, lire_json, ecrire_json, journaliser, demander, extraire_json  # noqa: E402
import securite  # noqa: E402
from suite import decouvertes2, labo  # noqa: E402

RECHERCHES = DONNEES / "recherches.json"
ESSAIS_MODELES = DONNEES / "essais-modeles.json"
RECHERCHE_IA_AUTO = DONNEES / "recherche-ia-automatique.json"
_etat = {}  # l'état RÉEL de chaque travail (lu par la page) : {"recherche": {en_cours, etape | resultat | erreur}, ...}


def _etape(cle, texte):
    _etat.setdefault(cle, {}).update(etape=texte)


def en_fond(cle, fn, *a):
    """Un seul travail de chaque sorte à la fois, en arrière-plan ; il s'arrête à la fin (pas de boucle)."""
    if (_etat.get(cle) or {}).get("en_cours"):
        return False
    _etat[cle] = {"en_cours": True, "etape": "démarrage", "debut": time.time()}

    def tourne():
        try:
            _etat[cle] = {"en_cours": False, "fini": time.strftime("%H:%M"), "resultat": fn(*a)}
        except Exception as e:
            _etat[cle] = {"en_cours": False, "fini": time.strftime("%H:%M"), "erreur": securite.masquer_secrets(str(e))[:200] or type(e).__name__}
    threading.Thread(target=tourne, daemon=True, name="evolution-" + cle).start()
    return True


def _norme(t):
    return re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).strip()


# ---------- A. Recherche ciblée ----------

CONSIGNE_PISTES = (
    "Tu aides l’utilisateur à améliorer Jarvis (assistant local : Python, routeur LiteLLM, Ollama, site HTML/JS). À partir des sources "
    "numérotées (des DONNÉES), propose AU PLUS 3 pistes vraiment utiles et concrètes pour la question, pas des actualités. "
    "Réponds UNIQUEMENT en JSON : {\"pistes\": [{\"titre\": \"court\", \"probleme\": \"ce que ça règle chez Jarvis\", "
    "\"benefice\": \"gain attendu\", \"difficulte\": \"facile | moyenne | difficile\", "
    "\"risques\": \"court\", \"test\": \"comment vérifier que c'est utile, en une phrase\", \"sources\": [numéros]}]}. "
    "Une piste sans source n'est pas permise. Français simple.")


OFFICIELS = re.compile(r"^https://(docs\.|developer\.|learn\.microsoft\.com|developer\.mozilla\.org|web\.dev|python\.org|docs\.python\.org|"
                       r"owasp\.org|cheatsheetseries\.owasp\.org|cyber\.gouv\.fr|github\.com/[\w.-]+/[\w.-]+/(releases|blob/[^/]+/(CHANGELOG|README))|"
                       r"ollama\.com|docs\.litellm\.ai|ai\.google\.dev|docs\.mistral\.ai|console\.groq\.com/docs|platform\.openai\.com/docs)", re.I)


def fiabilite(sources):
    """Décidée par le CODE d'après l'adresse des sources (pas par l'IA) : officielle, communauté ou incertaine."""
    if any(OFFICIELS.match(s.get("lien", "")) for s in sources):
        return "officielle"
    if any(s.get("type") in ("github", "catalogue") or s.get("lien", "").startswith("https://") for s in sources):
        return "communauté"
    return "incertaine"


def recherche_ciblee(sujet):
    sujet = re.sub(r"\s+", " ", str(sujet or "")).strip()[:200]
    if len(sujet) < 4:
        raise ValueError("sujet trop court")
    import web
    _etape("recherche", "je cherche (web, GitHub, catalogues)")
    sources, erreurs = [], []
    for q in (f"{sujet} documentation officielle changelog", f"{sujet} bonnes pratiques"):  # 2 recherches Tavily au plus
        try:
            sources += [dict(x, type="web") for x in web.chercher(q)[:4]]
        except Exception as e:
            erreurs.append(f"web : {str(e)[:60] or type(e).__name__}")
    try:
        r = decouvertes2._get_json("https://api.github.com/search/repositories?per_page=5&sort=stars&q=" + urllib.parse.quote(sujet + " pushed:>2025-06-01"),
                                   decouvertes2.Budget(1))
        sources += [{"type": "github", "titre": x["full_name"], "lien": x["html_url"],
                     "desc": f"{decouvertes2._propre(x.get('description'), 200)} · {x.get('stargazers_count', 0)} étoiles · modifié le "
                             f"{(x.get('pushed_at') or '')[:10]} · licence {((x.get('license') or {}).get('spdx_id') or 'aucune')}"}
                    for x in r.get("items", [])[:5]]
    except Exception as e:
        erreurs.append(f"GitHub : {type(e).__name__}")
    if re.search(r"mod[eè]le|llm|\bia\b|routeur|litellm|ollama|gemini|mistral|groq", sujet, re.I):
        for p in lire_json(DONNEES / "propositions-modeles.json", {}).get("propositions", [])[:5]:
            sources.append({"type": "catalogue", "titre": str(p.get("titre", ""))[:140], "lien": str(p.get("lien", "")), "desc": str(p.get("pourquoi", p.get("detail", "")))[:300]})
    sources = securite.filtrer([s for s in sources if str(s.get("lien", "")).startswith("https://") or s["type"] == "catalogue"], "recherche")
    vus, uniques = set(), []
    for s in sources:
        if s.get("lien") not in vus:
            vus.add(s.get("lien"))
            uniques.append(s)
    pistes, modele = [], ""
    if uniques:
        _etape("recherche", f"je trie {len(uniques)} sources")
        texte = "\n\n".join(f"[{i}] ({s['type']}) {s['titre']}\n{s.get('desc', '')}" for i, s in enumerate(uniques, 1))
        msg, modele = demander("jarvis", [{"role": "system", "content": securite.CONSIGNE_DONNEES},
                                          {"role": "user", "content": CONSIGNE_PISTES + f"\n\nQuestion : {sujet}\n" + securite.encadrer(texte, "recherche")}],
                               max_tokens=1400, temperature=0.2)
        brut = extraire_json(msg.get("content") or "") or {}
        deja = {_norme(p.get("titre")) for p in lire_json(DONNEES / "propositions.json", {}).get("propositions", [])}
        deja |= {_norme(p["titre"]) for r in lire_json(RECHERCHES, []) for p in r.get("pistes", [])}
        for p in (brut.get("pistes") if isinstance(brut, dict) else [])[:3]:
            nums = [n for n in p.get("sources", []) if isinstance(n, int) and 1 <= n <= len(uniques)]
            if not nums or not p.get("titre"):
                continue  # pas de source vérifiable : écartée
            p = {k: str(p.get(k, ""))[:300] for k in ("titre", "probleme", "benefice", "fiabilite", "difficulte", "risques", "test")}
            p["sources"] = [{"titre": uniques[n - 1]["titre"], "lien": uniques[n - 1].get("lien", ""), "type": uniques[n - 1]["type"]} for n in nums]
            p["fiabilite"] = fiabilite(p["sources"])
            p["deja_vue"] = _norme(p["titre"]) in deja
            pistes.append(p)
    res = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "sujet": sujet, "pistes": pistes, "nb_sources": len(uniques), "erreurs": erreurs, "modele": modele,
           "depots": [s for s in uniques if s["type"] == "github"][:5]}
    ecrire_json(RECHERCHES, (lire_json(RECHERCHES, []) + [res])[-30:])
    journaliser(agent="veille", action="recherche ciblée", etat="info", statut="ok" if pistes else "vide", resume=f"{sujet[:80]} : {len(pistes)} piste(s)")
    return res


def recherche_ia_periodique():
    """Recherche hebdomadaire des IA utiles, appelée par le cycle uniquement en mode automatique."""
    maintenant = time.time()
    etat = lire_json(RECHERCHE_IA_AUTO, {})
    if maintenant - etat.get("t", 0) < 7 * 86400:
        return True, "recherche des IA déjà faite cette semaine"
    sujet = ("Nouvelles IA, modèles et agents utiles à Jarvis : capacités, limites, compatibilité avec son routeur, "
             "disponibilité et sources officielles")
    ecrire_json(RECHERCHE_IA_AUTO, {"t": maintenant, "sujet": sujet})
    try:
        r = recherche_ciblee(sujet)
    except Exception as e:
        r = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "sujet": sujet, "pistes": [], "nb_sources": 0,
             "erreurs": [f"recherche IA : {type(e).__name__}"], "modele": "", "depots": []}
        ecrire_json(RECHERCHES, (lire_json(RECHERCHES, []) + [r])[-30:])
        journaliser(agent="veille", action="recherche IA hebdomadaire", etat="info", statut="erreur",
                    resume=r["erreurs"][0])
        return False, "recherche IA en erreur (rapport conservé)"
    return not bool(r.get("erreurs")), f"recherche IA : {len(r['pistes'])} piste(s), {r['nb_sources']} source(s)" + (
        f", erreur : {', '.join(r['erreurs'])}" if r.get("erreurs") else "")


# ---------- B. Compétences (skills) : lire, puis tester avant d'adopter ----------

LICENCES_OK = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0", "CC-BY-4.0", "CC0-1.0", "Unlicense"}
SCRIPTS = (".sh", ".ps1", ".bat", ".cmd", ".py", ".js", ".ts", ".exe")
DEPENDANCES = {"requirements.txt", "package.json", "pyproject.toml", "setup.py", "Pipfile", "go.mod", "Cargo.toml"}
TACHES_COMPETENCE = ["court-1", "json-1", "francais-1", "code-1"]


def _frontmatter(texte):
    """L'en-tête YAML d'un SKILL.md (name, description) ; lu comme une donnée (safe_load), jamais exécuté."""
    import yaml
    m = re.match(r"---\s*\n(.*?)\n---", texte, re.S)
    try:
        d = yaml.safe_load(m.group(1)) if m else {}
    except Exception:
        d = {}
    return {str(k).lower(): re.sub(r"\s+", " ", str(v)).strip() for k, v in (d if isinstance(d, dict) else {}).items()}


def skills_existants():
    out = []
    for f in list((IA / ".claude" / "skills").glob("*/SKILL.md")):
        fm = _frontmatter(f.read_text(encoding="utf-8", errors="ignore"))
        out.append({"nom": fm.get("name", f.parent.name), "description": fm.get("description", "")})
    return out


def verifier_competence(depot):
    """LECTURE seule (API GitHub, 8 requêtes au plus) : rien n'est cloné, installé ni exécuté."""
    depot = re.sub(r"^https?://github\.com/", "", str(depot or "")).strip("/")[:120]
    b = decouvertes2.Budget(8)
    a = decouvertes2.analyser_depot(depot, b)
    racine = decouvertes2._get_json(f"https://api.github.com/repos/{depot}/contents/", b)
    noms = {x.get("name", ""): x for x in racine if isinstance(x, dict)}
    chemin = "SKILL.md" if "SKILL.md" in noms else ""
    if not chemin and "skills" in noms:  # un dépôt de plusieurs skills : on lit le premier
        sous = [x for x in decouvertes2._get_json(f"https://api.github.com/repos/{depot}/contents/skills", b) if x.get("type") == "dir"]
        chemin = f"skills/{sous[0]['name']}/SKILL.md" if sous else ""
    if not chemin:
        raise ValueError("pas de SKILL.md dans ce dépôt : ce n'est pas une compétence")
    f = decouvertes2._get_json(f"https://api.github.com/repos/{depot}/contents/{urllib.parse.quote(chemin)}", b)
    texte = base64.b64decode(f.get("content", "")).decode("utf-8", "replace")[:20000]
    pieges = securite.analyser(texte)
    if pieges:
        securite.alerter("competence", texte[:200], pieges)
        raise ValueError("les instructions contiennent un piège (injection) : compétence écartée")
    fm = _frontmatter(texte)
    proches = sorted(((difflib.SequenceMatcher(None, _norme(fm.get("description")), _norme(s["description"])).ratio(), s["nom"])
                      for s in skills_existants()), reverse=True)[:1]
    risques = []
    if a["faits"]["licence"] not in LICENCES_OK:
        risques.append(f"licence {a['faits']['licence']} : à vérifier")
    scripts = sorted(n for n in noms if n.endswith(SCRIPTS))
    if scripts:
        risques.append("contient des scripts (" + ", ".join(scripts[:5]) + ") : lus seulement, jamais lancés")
    deps = sorted(n for n in noms if n in DEPENDANCES)
    if deps:
        risques.append("dépendances à installer : " + ", ".join(deps))
    nouveau = not proches or proches[0][0] < 0.55
    c = decouvertes2.candidat(fm.get("name") or depot.split("/")[-1], "GitHub (compétence)", a["faits"]["lien"], a["faits"].get("derniere_version", ""),
                              a["faits"]["licence"], capacites=fm.get("description", "")[:300], permissions="; ".join(risques) or "aucun script, aucune dépendance")
    d = lire_json(decouvertes2.CANDIDATS, {})
    d[c["id"]]["capacites"] = fm.get("description", "")[:300]  # relue à chaque vérification
    d[c["id"]]["competence"] = {"depot": depot, "chemin": chemin, "instructions": texte, "score_depot": a["score"], "risques": risques,
                                "proche_de": proches[0][1] if proches else "", "ressemblance": round(proches[0][0], 2) if proches else 0, "nouveau": nouveau}
    ecrire_json(decouvertes2.CANDIDATS, d)
    if d[c["id"]]["etat"] == "decouvert":
        decouvertes2.changer_etat(c["id"], "analyse", "jarvis", "lue : " + ("; ".join(risques) or "rien de risqué")
                                  + ("" if nouveau else f" ; ressemble à « {proches[0][1]} » ({round(proches[0][0] * 100)} %)"))
    c = lire_json(decouvertes2.CANDIDATS, {})[c["id"]]  # relu : l'état vient de changer
    return {**c, "competence": {k: v for k, v in c["competence"].items() if k != "instructions"}}


def tester_competence(ident, profil="jarvis-code"):
    """Le Labo compare la méthode actuelle et la même IA AVEC les instructions de la compétence (4 tâches inventées, 8 appels)."""
    d = lire_json(decouvertes2.CANDIDATS, {})
    c = d.get(ident)
    if not c or "competence" not in c or c["etat"] != "analyse":
        raise ValueError("compétence à vérifier d'abord")
    _etape("competence", "le Labo compare (8 appels)")
    e = labo.nouvelle(f"La compétence « {c['nom']} » améliore-t-elle {profil} ?", "Ses instructions donnent de meilleures réponses",
                      {"profil": profil}, {"profil": profil, "systeme": c["competence"]["instructions"][:6000], "max_tokens": 500}, TACHES_COMPETENCE)
    e = labo.lancer(e["id"])
    r, reco = e.get("resume", {}), e.get("decision", "")
    etat = "prototype" if reco.startswith(("adopter", "retester")) else "rejete" if r.get("regresse_sur") and not r.get("gagne_sur") else "surveille"
    pourquoi = (f"Labo {e['id']} : réussite {r.get('reference', {}).get('reussite')} % sans, {r.get('variante', {}).get('reussite')} % avec ; {reco}")
    d = lire_json(decouvertes2.CANDIDATS, {})
    d[ident]["essais"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "labo": e["id"], "recommandation": reco, "resume": pourquoi})
    ecrire_json(decouvertes2.CANDIDATS, d)
    decouvertes2.changer_etat(ident, etat, "jarvis", pourquoi)
    return {"etat": etat, "pourquoi": pourquoi, "labo": e["id"]}


# ---------- C. Comparer des modèles du routeur (sans toucher à config.yaml) ----------

TYPES = {"code": (["code-1", "json-1", "code-2"], "jarvis-code"), "redaction": (["francais-1", "court-1", "redaction-2"], "jarvis-redaction"),
         "tri": (["tri-1", "tri-2"], "jarvis-rapide"),  # mission 10 : vraies tâches de Jarvis (tri d'offres, relance, correction)
         "raisonnement": (["prudence-1", "piege-1"], "jarvis"), "rapide": (["court-1", "court-2"], "jarvis-rapide"),
         "cyber": (["cyber-1", "prudence-1"], "jarvis")}
MAX_CANDIDATS = 3


def modeles_routeur():
    """Les modèles qu'on peut appeler un par un (noms e-… de config.yaml), lus seulement."""
    import yaml
    c = yaml.safe_load((IA / "routeur-ia" / "routeur" / "config.yaml").read_text(encoding="utf-8"))
    return {m["model_name"]: m["litellm_params"]["model"] for m in c.get("model_list", []) if m["model_name"].startswith("e-")}


def comparer_modeles(type_tache, candidats):
    if type_tache not in TYPES:
        raise ValueError("type de tâche inconnu")
    dispo = modeles_routeur()
    candidats = [m for m in dict.fromkeys(candidats) if m in dispo][:MAX_CANDIDATS]
    if not candidats:
        raise ValueError("choisis 1 à 3 modèles du routeur")
    taches, reference = TYPES[type_tache]
    from suite import sante
    etat_ias = {m["modele"]: m for m in sante.ias()["modeles"]}
    anciens = lire_json(ESSAIS_MODELES, [])
    resultats = []
    for i, nom in enumerate(candidats, 1):
        _etape("modeles", f"modèle {i} sur {len(candidats)} : {nom}")
        deja = next((r for a in reversed(anciens) for r in a["resultats"] if a["type"] == type_tache and r["modele"] == nom
                     and time.time() - a["epoque"] < 7 * 86400 and r.get("labo")), None)
        if deja:  # même essai il y a moins de 7 jours : on ne le refait pas
            resultats.append(dict(deja, repris=True))
            continue
        e = labo.nouvelle(f"{nom} contre {reference} ({type_tache})", f"{nom} fait au moins aussi bien", {"profil": reference},
                          {"profil": nom, "max_tokens": 600}, taches)
        e = labo.lancer(e["id"])
        r, m = e.get("resume", {}), etat_ias.get(dispo[nom], {})
        resultats.append({"modele": nom, "vrai_nom": dispo[nom], "labo": e["id"], "reussite": r.get("variante", {}).get("reussite"),
                          "reussite_reference": r.get("reference", {}).get("reussite"), "temps": r.get("variante", {}).get("temps"),
                          "temps_reference": r.get("reference", {}).get("temps"), "tokens": r.get("variante", {}).get("tokens"),
                          "erreurs": r.get("variante", {}).get("erreurs"), "recommandation": e.get("decision", ""),
                          "local": dispo[nom].startswith("ollama"), "gratuit": dispo[nom].endswith(":free") or dispo[nom].startswith("ollama"),
                          "quota": m.get("quota", ""), "remarque_24h": m.get("remarque", "")})
    meilleur = max((r for r in resultats if str(r.get("recommandation", "")).startswith("adopter")), key=lambda r: r.get("reussite") or 0, default=None)
    res = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "epoque": time.time(), "type": type_tache, "reference": reference, "taches": taches,
           "resultats": resultats, "conseil": (f"{meilleur['modele']} fait mieux que {reference} sur ces tâches. Rien n'est changé : "
                                               "si tu veux l'utiliser, dis-le et je prépare le changement du routeur (ton accord).") if meilleur
           else f"Aucun modèle essayé ne fait clairement mieux que {reference} sur ces tâches : on garde le choix actuel."}
    ecrire_json(ESSAIS_MODELES, (anciens + [res])[-40:])
    journaliser(agent="jarvis", action="comparer des modèles", etat="info", statut="ok", resume=f"{type_tache} : {', '.join(candidats)}")
    return res


# ---------- D. Le choix des IA par tâche, tel qu'il marche vraiment ----------

def audit_profils():
    from suite import sante
    i = sante.ias()
    par_modele = {m["modele"]: m for m in i["modeles"]}
    lignes, manques = [], []
    for p, x in i["profils"].items():
        chaine = x.get("chaine", [])
        premier = par_modele.get(chaine[0], {}) if chaine else {}
        local_final = bool(chaine) and chaine[-1].startswith("ollama")
        tout_local = bool(chaine) and all(c.startswith("ollama") for c in chaine)
        taux = round(100 * x.get("erreurs", 0) / x["appels"]) if x.get("appels") else 0
        lignes.append({"profil": p, "role": x.get("role", ""), "nom": x.get("nom", ""), "chaine": chaine, "appels_24h": x.get("appels", 0),
                       "erreurs_pct": taux, "duree_moy": x.get("duree_moy"), "premier_quota": premier.get("quota", ""), "secours_local": local_final})
        if p == "jarvis-prive" and not tout_local:
            manques.append("jarvis-prive peut partir vers une IA en ligne : à corriger (données perso)")
        if p not in ("jarvis-vision",) and chaine and not local_final:
            manques.append(f"{p} n'a pas de secours sur ton PC : si Internet coupe, il ne répond plus")
        if x.get("appels", 0) >= 5 and taux >= 20:
            manques.append(f"{p} échoue souvent ({taux} % d'erreurs en 24 h)")
        if premier.get("quota") == "atteint":
            manques.append(f"le 1er modèle de {p} a atteint son quota : il passe par ses secours")
        if x.get("duree_moy") and x["duree_moy"] > 20:
            manques.append(f"{p} est lent ({x['duree_moy']} s en moyenne)")
    from suite import routes
    if routes.ia_defaut():
        manques.append(f"« Mon IA par défaut » = {routes.ia_defaut()} : le chat ne choisit plus l'IA selon la tâche (code, rédaction…)")
    return {"profils": lignes, "manques": manques or ["aucun manque repéré dans les chiffres des dernières 24 h"]}


def etat():
    return {"travaux": _etat, "recherches": list(reversed(lire_json(RECHERCHES, [])))[:5],
            "essais_modeles": list(reversed(lire_json(ESSAIS_MODELES, [])))[:5], "modeles": sorted(modeles_routeur()), "types": sorted(TYPES)}
