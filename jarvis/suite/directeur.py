r"""Mission 7 — Le Directeur : un seul point de pilotage.

Ce n'est PAS une IA de plus : c'est une file de travail + des règles. Il
- choisit le mode d'une demande (direct / mission / mission sensible) par des règles simples, sans appel d'IA ;
- garde les missions dans donnees\missions.json (reprise après redémarrage, jamais d'action externe rejouée en aveugle) ;
- exécute les étapes dans l'ordre, avec un nombre d'essais et un budget (appels, tokens, temps) ;
- s'arrête quand c'est fini, quand le budget est atteint, ou quand une décision humaine est nécessaire ;
- range les vraies questions dans « Décisions pour moi » (donnees\decisions.json), regroupées par sujet ;
- écrit un mini-rapport à chaque amélioration terminée (donnees\mini-rapports.json).

Claude Code peut lui parler par la « boîte » : des fichiers JSON dans donnees\boite-claude\ (voir la fin du fichier).
Les réponses de l’utilisateur ne viennent QUE de la page (origine humaine), jamais d'un fichier ou d'une IA.
"""
import json, re, sys, time, uuid, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import DONNEES, lire_json, ecrire_json, journaliser, arret_actif  # noqa: E402

MISSIONS = DONNEES / "missions.json"
DECISIONS = DONNEES / "decisions.json"
RAPPORTS = DONNEES / "mini-rapports.json"
BOITE = DONNEES / "boite-claude"
_verrou = threading.RLock()

ETATS = ("pending", "running", "blocked", "done", "failed", "skipped")
BUDGET_DEFAUT = {"appels": 12, "tokens": 60000, "secondes": 900}
ORIGINES_HUMAINES = {"page"}  # choix de l’utilisateur : décisions sur le site seulement


def maintenant():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def court(t, n):
    t = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", str(t or "")).strip()
    return t[:n]


# ---------- 1. Le mode d'une demande (règles, sans IA) ----------

SENSIBLE = re.compile(r"\b(envoie|envoyer|supprime|supprimer|efface|installe|installer|publie|publier|paie|payer|achète|"
                      r"désinstalle|formate|déploie|mot de passe|clé|cles?\.txt|token|virement|résilie)\b", re.I)
PLUSIEURS = re.compile(r"\b(puis|ensuite|et après|étape|compare|comparer|recherche .{0,40} et |analyse .{0,40} et |"
                       r"prépare .{0,40} et |plan|rapport complet|tous les|toutes les)\b", re.I)


def choisir_mode(demande):
    """direct = une seule IA ou un outil ; mission = plusieurs étapes ; critique = action réelle ou sensible."""
    d = demande or ""
    from suite import politique  # mission 10 : les trois niveaux (seul / demande / jamais) décident, partout pareil
    if politique.niveau(d)[0] != "seul":
        return "critique"
    if PLUSIEURS.search(d) or len(d) > 400:
        return "mission"
    return "direct"


# ---------- 2. La file de missions ----------

def _lire():
    return lire_json(MISSIONS, {"missions": []})


def _ecrire(d):
    ecrire_json(MISSIONS, d)


def score_priorite(impact=2, frequence=2, confiance=2, cout=2, risque=1):
    """impact × fréquence × confiance ÷ (coût × risque), chaque valeur de 1 (faible) à 3 (fort)."""
    v = [max(1, min(3, int(x))) for x in (impact, frequence, confiance, cout, risque)]
    return round(v[0] * v[1] * v[2] / (v[3] * v[4]), 2)


def creer_mission(titre, objectif, etapes, mode=None, budget=None, priorite=None, depend_de=None, source="jarvis"):
    """etapes : [{"titre", "type" (ia|outil|verification|externe|humain), "executant", "params", "max_essais", "critere"}]"""
    m = {"id": "m-" + uuid.uuid4().hex[:8], "titre": court(titre, 120), "objectif": court(objectif, 600),
         "mode": mode or choisir_mode(objectif), "etat": "pending", "priorite": priorite or score_priorite(),
         "budget": {**BUDGET_DEFAUT, **(budget or {})}, "consomme": {"appels": 0, "tokens": 0, "secondes": 0.0},
         "depend_de": list(depend_de or []), "source": source, "cree": maintenant(), "maj": maintenant(),
         "blocage": "", "rapport": "", "etapes": []}
    for i, e in enumerate(etapes, 1):
        m["etapes"].append({"n": i, "titre": court(e.get("titre"), 120), "type": e.get("type", "outil"),
                            "executant": e.get("executant", ""), "params": e.get("params", {}),
                            "max_essais": max(1, min(3, int(e.get("max_essais", 2)))), "essais": 0,
                            "critere": e.get("critere", ""), "statut": "pending", "resultat": "", "preuve": "",
                            "erreur": "", "categorie_erreur": "", "duree": 0.0})
    with _verrou:
        d = _lire()
        d["missions"].append(m)
        _ecrire(d)
    journaliser(agent="jarvis", action="mission", etat="info", statut="creee", resume=m["titre"], id=m["id"])
    return m


def mission(ident):
    return next((m for m in _lire()["missions"] if m["id"] == ident), None)


def _maj(m):
    with _verrou:
        d = _lire()
        d["missions"] = [m if x["id"] == m["id"] else x for x in d["missions"]]
        m["maj"] = maintenant()
        _ecrire(d)


def prochaine():
    """La mission prête la plus prioritaire (dépendances terminées, pas bloquée)."""
    ms = _lire()["missions"]
    finies = {m["id"] for m in ms if m["etat"] == "done"}
    pretes = [m for m in ms if m["etat"] == "pending" and set(m["depend_de"]) <= finies]
    return min(pretes, key=lambda m: (-m["priorite"], m["cree"]), default=None)  # la plus prioritaire, puis la plus ancienne


def budget_epuise(m):
    b, c = m["budget"], m["consomme"]
    return c["appels"] >= b["appels"] or c["tokens"] >= b["tokens"] or c["secondes"] >= b["secondes"]


def avancer(ident, executants, verifier=None):
    """Exécute les étapes restantes d'une mission. `executants` : {nom: fonction(params) -> dict(resultat, ok, appels, tokens)}.
    `verifier` : {critere: fonction(resultat) -> (ok, raison)}. Renvoie la mission à jour.
    Une étape « externe » ou « humain », ou toute étape d'une mission critique, crée une décision et bloque la mission."""
    verifier = verifier or {}
    m = mission(ident)
    if not m or m["etat"] in ("done", "failed"):
        return m
    if arret_actif():
        m["etat"], m["blocage"] = "blocked", "Arrêt d'urgence actif"
        _maj(m)
        return m
    m["etat"] = "running"
    _maj(m)
    for e in m["etapes"]:
        if e["statut"] in ("done", "skipped"):
            continue
        if budget_epuise(m):
            m["etat"], m["blocage"] = "blocked", "Budget atteint"
            m["rapport"] = rapport_mission(m)
            _maj(m)
            return m
        from suite import politique
        niv = politique.niveau(e["titre"] + " " + str((e.get("params") or {}).get("consigne", "")))[0]
        if niv == "jamais":  # jamais, même avec un accord : l'étape est sautée, la mission continue
            e["statut"], e["resultat"] = "skipped", "Sautée : Jarvis ne fait jamais ça (envoi, paiement, secrets, photos, candidature)."
            _maj(m)
            continue
        sensible = e["type"] in ("externe", "humain") or niv == "demande"
        if sensible and not e.get("autorise"):
            e["statut"] = "blocked"
            m["etat"], m["blocage"] = "blocked", f"Ton accord est nécessaire : {e['titre']}"
            creer_decision(sujet=f"mission:{m['id']}", question=f"{m['titre']} — j'ai besoin de ton accord pour : {e['titre']}",
                           pourquoi="C'est une action réelle (elle sort de ton PC ou ne s'annule pas).",
                           options=[{"id": "oui", "libelle": "Oui, vas-y"}, {"id": "non", "libelle": "Non, saute cette étape"}],
                           recommande="", si_reporte="La mission reste en pause, les autres continuent.",
                           source="directeur", mission=m["id"], etape=e["n"])
            _maj(m)
            return m
        fn = executants.get(e["executant"])
        if not fn:
            e["statut"], e["resultat"] = "failed", f"Outil inconnu : {e['executant']}"
            m["etat"], m["blocage"] = "failed", e["resultat"]
            _maj(m)
            return m
        e["statut"] = "running"
        _maj(m)
        while e["essais"] < e["max_essais"]:
            e["essais"] += 1
            debut = time.time()
            try:
                r = fn(dict(e["params"], erreur_precedente=e.get("resultat", "")) if e["essais"] > 1 else dict(e["params"])) or {}
            except Exception as err:
                categorie = ("timeout" if isinstance(err, TimeoutError) else "permission" if isinstance(err, PermissionError)
                             else "entrée" if isinstance(err, (ValueError, TypeError)) else "dépendance" if isinstance(err, FileNotFoundError)
                             else "outil")
                r = {"ok": False, "resultat": f"{type(err).__name__}: {court(err, 120)}",
                     "erreur": type(err).__name__, "categorie_erreur": categorie}
            e["duree"] = round(e["duree"] + time.time() - debut, 2)
            m["consomme"]["appels"] += int(r.get("appels", 0))
            m["consomme"]["tokens"] += int(r.get("tokens", 0))
            m["consomme"]["secondes"] = round(m["consomme"]["secondes"] + time.time() - debut, 1)
            e["resultat"] = court(r.get("resultat", ""), 600)
            e["preuve"] = court(r.get("preuve", ""), 400)
            e["erreur"] = court(r.get("erreur", ""), 80)
            e["categorie_erreur"] = court(r.get("categorie_erreur", ""), 40)
            # Une sortie sans preuve explicite ne peut pas valider l'étape.
            ok = r.get("ok") is True
            if ok and e["critere"]:
                ok, raison = verifier.get(e["critere"], lambda _r: (False, "critère inconnu"))(r)
                if not ok:
                    e["resultat"] = court(f"{e['resultat']} — vérification : {raison}", 600)
            if ok:
                e["statut"] = "done"
                _maj(m)
                break
            # Pas de répétition implicite : l'outil doit prouver qu'une nouvelle tentative est sûre et utile.
            if r.get("reessayable") is not True:
                if e["type"] in ("externe", "humain"):
                    e["statut"] = "blocked"
                    m["etat"], m["blocage"] = "blocked", f"Résultat incertain pour « {e['titre']} » ; vérifie avant de relancer."
                    creer_decision(sujet=f"mission:{m['id']}", question=f"{m['titre']} : résultat incertain",
                                   pourquoi=e["resultat"] or "L'action a échoué sans preuve qu'elle n'a pas eu lieu.",
                                   options=[{"id": "oui", "libelle": "Vérifier puis refaire l'étape"},
                                            {"id": "non", "libelle": "Passer cette étape"}], recommande="non",
                                   si_reporte="La mission reste en pause.", source="directeur", mission=m["id"], etape=e["n"])
                    _maj(m)
                    return m
                break
            if budget_epuise(m):
                e["statut"] = "pending"
                m["etat"], m["blocage"] = "blocked", "Budget atteint"
                m["rapport"] = rapport_mission(m)
                _maj(m)
                return m
            _maj(m)
        if e["statut"] != "done":
            e["statut"] = "failed"
            m["etat"], m["blocage"] = "failed", f"Étape « {e['titre']} » ratée après {e['essais']} essai(s)"
            m["rapport"] = rapport_mission(m)
            _maj(m)
            return m
        _maj(m)
    m["etat"], m["blocage"] = "done", ""
    m["rapport"] = rapport_mission(m)
    _maj(m)
    journaliser(agent="jarvis", action="mission", etat="info", statut="terminee", resume=m["titre"], id=m["id"])
    return m


def rapport_mission(m):
    faites = [e for e in m["etapes"] if e["statut"] == "done"]
    txt = f"{m['titre']} : {len(faites)}/{len(m['etapes'])} étapes faites."
    if m["blocage"]:
        txt += f" {m['blocage']}."
    c = m["consomme"]
    return txt + f" ({c['appels']} appels, {c['tokens']} tokens, {round(c['secondes'])} s)"


def reprendre_apres_redemarrage(seule=None):
    """Au lancement : une mission restée « running » (PC éteint, plantage) reprend proprement.
    Étape interne en cours → rejouée (elle n'a pas d'effet externe). Étape externe en cours → bloquée + question."""
    n = 0
    with _verrou:
        d = _lire()
        for m in d["missions"]:
            if m["etat"] != "running" or (seule and m["id"] != seule):  # mission 14 : une seule mission bloquée
                continue
            n += 1
            for e in m["etapes"]:
                if e["statut"] == "running":
                    if e["type"] in ("externe", "humain"):
                        e["statut"], e["autorise"] = "blocked", False
                        m["blocage"] = f"Interrompue pendant « {e['titre']} » : je ne sais pas si c'est parti. Je te demande avant de refaire."
                    else:
                        e["statut"] = "pending"
            m["etat"] = "blocked" if m["blocage"] else "pending"
        _ecrire(d)
    for m in _lire()["missions"]:
        if m["etat"] == "blocked" and m["blocage"].startswith("Interrompue") and (not seule or m["id"] == seule):
            creer_decision(sujet=f"mission:{m['id']}", question=f"{m['titre']} : {m['blocage']}",
                           pourquoi="Refaire une action réelle deux fois pourrait envoyer un doublon.",
                           options=[{"id": "oui", "libelle": "Refaire l'étape"}, {"id": "non", "libelle": "Passer à la suite"}],
                           recommande="non", si_reporte="La mission reste en pause.", source="directeur", mission=m["id"])
    return n


def autoriser_etape(ident, n, oui):
    """Appelé quand l’utilisateur répond à la décision d'une mission (jamais par une IA)."""
    m = mission(ident)
    if not m or m["etat"] in ("done", "failed"):  # mission finie : une décision changée après coup ne la relance pas
        return m
    for e in m["etapes"]:
        if e["statut"] == "done":  # déjà faite (un mail est peut-être parti) : on ne réécrit jamais l'historique
            continue
        if e["n"] == n or (n is None and e["statut"] == "blocked"):
            if oui:
                e["autorise"], e["statut"] = True, "pending"
            else:
                e["statut"] = "skipped"
    m["etat"], m["blocage"] = "pending", ""
    _maj(m)
    return m


def tableau():
    """Pour la page Missions : en cours, en attente, terminées, ratées (les 30 dernières)."""
    ms = sorted(_lire()["missions"], key=lambda m: m["maj"], reverse=True)[:30]
    return {"compteurs": {e: sum(m["etat"] == e for m in ms) for e in ETATS}, "missions": ms}


# ---------- 3. « Décisions pour moi » ----------

def _dec():
    return lire_json(DECISIONS, {"decisions": []})


def creer_decision(sujet, question, pourquoi, options, recommande="", si_reporte="", source="jarvis", mission=None, etape=None, demande="",
                   extra=None, ref=""):
    """Une vraie question pour l’utilisateur. Même sujet encore ouvert = regroupé dans la même carte (pas de 2e interruption)."""
    opts = [{"id": court(o.get("id"), 30) or f"o{i}", "libelle": court(o.get("libelle"), 120),
             "avantages": court(o.get("avantages"), 300), "risques": court(o.get("risques"), 300), "cout": court(o.get("cout"), 120)}
            for i, o in enumerate(options[:4], 1)] or [{"id": "ok", "libelle": "D'accord"}]
    with _verrou:
        d = _dec()
        ouverte = next((x for x in d["decisions"] if x["sujet"] == sujet and x["etat"] == "ouverte"), None)
        if ouverte:
            if court(question, 400) not in ouverte["questions"]:
                ouverte["questions"].append(court(question, 400))
            if ref:
                ouverte.setdefault("refs", []).append(court(ref, 40))
            ouverte["maj"] = maintenant()
            ecrire_json(DECISIONS, d)
            return ouverte
        x = {"id": "d-" + uuid.uuid4().hex[:8], "sujet": court(sujet, 80), "questions": [court(question, 400)],
             "pourquoi": court(pourquoi, 400), "options": opts,
             "recommande": recommande if any(o["id"] == recommande for o in opts) else "",
             "si_reporte": court(si_reporte, 200), "source": court(source, 30), "mission": mission, "etape": etape,
             "etat": "ouverte", "cree": maintenant(), "maj": maintenant(), "choix": "", "note": "", "demande": court(demande, 1000),
             "refs": [court(ref, 40)] if ref else [],  # référence de chaque question de Claude Code (voir reponse_pour)
             **{k: v for k, v in (extra or {}).items() if k in ("items", "texte", "titre", "categorie", "temps", "conseil", "concerne")}}  # m12 : liste, texte ; m15 : carte Décisions
        d["decisions"].append(x)
        d["decisions"] = [y for y in d["decisions"] if y["etat"] == "ouverte"] + \
                         [y for y in d["decisions"] if y["etat"] != "ouverte"][-100:]
        ecrire_json(DECISIONS, d)
    return x


def decisions(ouvertes_seulement=True):
    ds = _dec()["decisions"]
    return [x for x in ds if x["etat"] == "ouverte"] if ouvertes_seulement else ds[-50:]


def repondre(ident, choix, origine, note=""):
    """Réponse de l’utilisateur. `origine` doit être humaine (le clic sur la page) : une IA ne peut pas décider à sa place."""
    if origine not in ORIGINES_HUMAINES:
        raise PermissionError("Seul l’utilisateur répond aux décisions.")
    with _verrou:
        d = _dec()
        x = next((y for y in d["decisions"] if y["id"] == ident), None)
        if not x or x["etat"] != "ouverte":
            return None
        if choix == "reporter":
            x["etat"], x["maj"] = "reportee", maintenant()
        elif any(o["id"] == choix for o in x["options"]):
            x["etat"], x["choix"], x["note"], x["maj"] = "repondue", choix, court(note, 400), maintenant()
        else:
            raise ValueError("Choix inconnu.")
        ecrire_json(DECISIONS, d)
    if x["mission"] and x["etat"] == "repondue":
        autoriser_etape(x["mission"], x.get("etape"), choix in ("oui",))
    journaliser(agent="jarvis", action="decision", etat="info", statut=x["etat"], resume=x["sujet"])
    return x


def rouvrir(ident, origine):
    """« Changer mon choix » : la décision redevient ouverte (l'ancien choix est gardé dans « avant »)."""
    if origine not in ORIGINES_HUMAINES:
        raise PermissionError("Seul l’utilisateur change ses décisions.")
    with _verrou:
        d = _dec()
        x = next((y for y in d["decisions"] if y["id"] == ident), None)
        if not x or x["etat"] not in ("repondue", "reportee"):
            return None
        if x.get("maj", "") < time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7 * 86400)):  # mission 15 : Annuler pendant 7 jours
            return None
        x.setdefault("avant", []).append({"etat": x["etat"], "choix": x.get("choix", ""), "maj": x.get("maj", "")})
        x["etat"], x["choix"], x["maj"] = "ouverte", "", maintenant()
        ecrire_json(DECISIONS, d)
    journaliser(agent="jarvis", action="decision", etat="info", statut="rouverte", resume=x["sujet"])
    return x


# ---------- 4. Mini-rapports ----------

def mini_rapport(probleme, fait, pourquoi="", tests="", gain="", limites="", fichiers="", commit="", retour_arriere="", source="jarvis"):
    r = {"id": "r-" + uuid.uuid4().hex[:8], "t": maintenant(), "source": court(source, 30),
         "probleme": court(probleme, 300), "fait": court(fait, 400), "pourquoi": court(pourquoi, 300), "tests": court(tests, 200),
         "gain": court(gain, 200), "limites": court(limites, 300), "fichiers": court(fichiers, 300), "commit": court(commit, 20),
         "retour_arriere": court(retour_arriere, 200)}
    with _verrou:
        rs = lire_json(RAPPORTS, [])
        rs.append(r)
        ecrire_json(RAPPORTS, rs[-100:])
    return r


def mini_rapports(n=20):
    return list(reversed(lire_json(RAPPORTS, [])[-n:]))


# ---------- 5. La boîte de Claude Code (canal local, fichiers JSON) ----------
# Claude Code écrit : py -3 -m suite.directeur question --sujet "x" --question "…" --option oui:"Oui" --option non:"Non" --recommande oui
#                     py -3 -m suite.directeur rapport --probleme "…" --fait "…" --tests "37 OK" --commit abc1234
# Le serveur importe la boîte (route GET /decisions) ; Claude Code lit les réponses : py -3 -m suite.directeur reponses

TYPES_BOITE = {"question", "rapport"}


def deposer(type_, contenu):
    if type_ not in TYPES_BOITE:
        raise ValueError("type inconnu")
    BOITE.mkdir(parents=True, exist_ok=True)
    f = BOITE / f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.json"
    ecrire_json(f, {"type": type_, "contenu": contenu, "t": maintenant(), "ref": "q-" + uuid.uuid4().hex[:10]})
    return f


def ref_depot(f):
    """La référence unique d'un dépôt (le fichier a pu être rangé dans lus/ entre-temps)."""
    f = Path(f)
    return (lire_json(f, None) or lire_json(f.parent / "lus" / f.name, {})).get("ref", "")


def reponse_pour(ref):
    """La carte qui contient la question `ref` : Claude Code lit LA réponse à SA question, pas la dernière du même sujet."""
    x = next((y for y in _dec()["decisions"] if ref and ref in y.get("refs", [])), None)
    return x and {k: x.get(k) for k in ("id", "sujet", "questions", "etat", "choix", "note", "maj")}


def importer_boite():
    """Lit les fichiers déposés, les valide strictement, les range, puis les déplace dans boite-claude/lus/."""
    if not BOITE.exists():
        return 0
    with _verrou_boite:  # deux pages qui lisent /decisions en même temps : un seul import (sinon doublon puis FileNotFoundError)
        return _importer_boite()


_verrou_boite = threading.Lock()


def _importer_boite():
    lus = BOITE / "lus"
    lus.mkdir(exist_ok=True)
    n = 0
    for f in sorted(BOITE.glob("*.json"))[:50]:
        d = lire_json(f, {})
        c = d.get("contenu") if isinstance(d, dict) else None
        try:
            if d.get("type") == "question" and isinstance(c, dict) and c.get("question"):
                creer_decision(sujet="claude:" + court(c.get("sujet") or "divers", 60), question=c["question"],
                               pourquoi=c.get("pourquoi", ""), options=[o for o in c.get("options", []) if isinstance(o, dict)],
                               recommande=c.get("recommande", ""), si_reporte=c.get("si_reporte", ""), source="claude-code",
                               ref=str(d.get("ref", "")))
                n += 1
            elif d.get("type") == "rapport" and isinstance(c, dict) and c.get("fait"):
                mini_rapport(**{k: c.get(k, "") for k in ("probleme", "fait", "pourquoi", "tests", "gain", "limites",
                                                          "fichiers", "commit", "retour_arriere")}, source="claude-code")
                n += 1
        finally:
            f.replace(lus / f.name)
    return n


def _cli():
    import argparse
    p = argparse.ArgumentParser(prog="suite.directeur")
    s = p.add_subparsers(dest="cmd", required=True)
    q = s.add_parser("question")
    q.add_argument("--sujet", default="divers")
    q.add_argument("--question", required=True)
    q.add_argument("--pourquoi", default="")
    q.add_argument("--option", action="append", default=[], help="id:libellé")
    q.add_argument("--recommande", default="")
    q.add_argument("--si-reporte", default="")
    r = s.add_parser("rapport")
    for k in ("probleme", "fait", "pourquoi", "tests", "gain", "limites", "fichiers", "commit", "retour-arriere"):
        r.add_argument("--" + k, default="")
    s.add_parser("reponses").add_argument("--ref", default="", help="la référence affichée par « question »")
    a = p.parse_args()
    if a.cmd == "question":
        opts = [{"id": o.split(":", 1)[0], "libelle": o.split(":", 1)[-1]} for o in a.option]
        f = deposer("question", {"sujet": a.sujet, "question": a.question, "pourquoi": a.pourquoi, "options": opts,
                                 "recommande": a.recommande, "si_reporte": a.si_reporte})
        print(f)
        print("ref=" + ref_depot(f))  # à garder : « reponses --ref … » lira exactement la réponse à cette question
    elif a.cmd == "rapport":
        print(deposer("rapport", {k.replace("-", "_"): v for k, v in vars(a).items() if k not in ("cmd",)}))
    elif a.ref:
        print(json.dumps(reponse_pour(a.ref) or {"etat": "pas encore affichée sur le site (ou référence inconnue)"}, ensure_ascii=False))
    else:
        for x in decisions(False):
            if x["source"] == "claude-code" and x["etat"] != "ouverte":
                print(json.dumps({"sujet": x["sujet"], "questions": x["questions"], "etat": x["etat"], "choix": x["choix"],
                                  "note": x["note"]}, ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    _cli()
