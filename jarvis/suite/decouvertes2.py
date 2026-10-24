r"""Mission 8 — Découvertes 2.0 : une veille utile, dédupliquée, vérifiable, qui n'installe JAMAIS rien.

En plus de agents\veille.py (GitHub, web, YouTube, CERT-FR, qui reste en place), ce module surveille ce que Jarvis
UTILISE vraiment :
  - les nouvelles versions de ses outils (LiteLLM, Ollama, SDK MCP) comparées à la version installée ;
  - les failles connues des paquets Python installés (base OSV, gratuite) ;
  - les failles activement exploitées (catalogue CISA KEV) sur les logiciels de l’utilisateur.
Et il sait analyser un dépôt GitHub en profondeur (maintenu ? licence ? scripts d'installation ?) avec un score EXPLIQUÉ.

Cache : donnees\decouvertes2.json (première et dernière vue, empreinte, statut) → une version déjà vue n'est pas re-résumée.
Pas d'IA ici : que des faits lus dans les sources officielles. Les textes externes passent par securite.analyser().
Registre des candidats (skills, outils, dépôts) : découverte → analyse → prototype → décision → intégré → mesuré → réévalué.
"""
import hashlib, json, re, sys, time, urllib.request, urllib.error
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import DONNEES, lire_json, ecrire_json, journaliser  # noqa: E402
import securite  # noqa: E402

CACHE = DONNEES / "decouvertes2.json"
CANDIDATS = DONNEES / "candidats.json"
AJOUTS_FEUILLE = DONNEES / "feuille-de-route-ajouts.json"
TTL = {"version": 24 * 3600, "osv": 24 * 3600, "kev": 12 * 3600, "depot": 7 * 86400}
BUDGET_APPELS = 25  # requêtes réseau maximum par lancement
NOTE_MIN, MAX_FICHES, JOURS_VISIBLE = 7, 5, 7  # peu de fiches, seulement les utiles ; une fiche montrée reste 7 jours puis s'archive

OUTILS = {  # ce que Jarvis utilise réellement → dépôt officiel + comment lire la version installée
    "LiteLLM": {"depot": "BerriAI/litellm", "paquet": "litellm", "fichiers": "routeur-ia\\routeur\\config.yaml, run.bat"},
    "Ollama": {"depot": "ollama/ollama", "api": "http://127.0.0.1:11434/api/version", "fichiers": "lancer.ps1, config.yaml (profils locaux)"},
    "SDK MCP (Python)": {"depot": "modelcontextprotocol/python-sdk", "paquet": "mcp", "fichiers": "jarvis\\mcp_jarvis.py"},
}
LOGICIELS_KEV = ["windows", "chrome", "chromium", "firefox", "edge", "python", "7-zip", "winrar", "notepad++", "discord",
                 "steam", "vlc", "obs", "nvidia", "ollama", "openssl", "git"]
SOURCES_COUPEES_DEFAUT = []


class Budget:
    def __init__(self, n=BUDGET_APPELS):
        self.reste = n

    def prendre(self):
        if self.reste <= 0:
            raise RuntimeError("budget de requêtes atteint")
        self.reste -= 1


def _get_json(url, budget, data=None, timeout=20):
    budget.prendre()
    h = {"User-Agent": "jarvis-decouvertes/2", "Accept": "application/json"}
    import os
    if "api.github.com" in url and os.environ.get("GITHUB_TOKEN"):
        h["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]  # jamais journalisé
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(5_000_000).decode("utf-8", "replace"))


def _propre(texte, n=600):
    """Texte externe : coupé, et vidé s'il contient un piège (injection de consigne)."""
    t = re.sub(r"\s+", " ", str(texte or "")).strip()[:n]
    if securite.analyser(t):
        securite.alerter("decouvertes2", t[:200], securite.analyser(t))
        return "(texte retiré : contenu suspect)"
    return t


def _ver(v):
    """'v1.79.3' → (1, 79, 3) pour comparer. Les suffixes (-rc, -nightly) comptent comme plus petits."""
    v = str(v or "")
    base, pre = re.split(r"[-+]|(?=rc|beta|alpha|dev|nightly|pre)", v, maxsplit=1)[0], re.search(r"rc|beta|alpha|dev|nightly|pre", v, re.I)
    nums = tuple(int(x) for x in re.findall(r"\d+", base)[:4])
    nums += (0,) * (4 - len(nums))
    return nums + ((-1,) if pre else (0,))


# ---------- Cache et déduplication ----------

def _cache():
    return lire_json(CACHE, {"items": {}, "dernier": {}, "sources_coupees": SOURCES_COUPEES_DEFAUT})


def _frais(c, cle, ttl):
    return time.time() - c["dernier"].get(cle, 0) < ttl


def _noter(c, ident, fiche):
    """Ajoute ou met à jour une fiche. Renvoie True seulement si c'est NOUVEAU ou si le contenu a changé.
    Une fiche déjà montrée à l’utilisateur (c["vus"]) ne revient jamais. La date du jour n'entre pas dans l'empreinte."""
    if ident in c.setdefault("vus", {}):
        return False
    preuves = [{k: v for k, v in p.items() if k != "date"} for p in fiche.get("preuves", [])]
    empreinte = hashlib.sha256(json.dumps(preuves, sort_keys=True).encode()).hexdigest()[:16]
    t = time.strftime("%Y-%m-%dT%H:%M:%S")
    ancien = c["items"].get(ident)
    if ancien and ancien.get("empreinte") == empreinte:
        ancien["last_seen"] = t
        return False
    c["items"][ident] = {**fiche, "id": ident, "empreinte": empreinte, "first_seen": (ancien or {}).get("first_seen", t),
                         "last_seen": t, "statut": (ancien or {}).get("statut", "nouvelle"),
                         "historique": (ancien or {}).get("historique", [])}
    return True


# ---------- Sources ----------

def version_installee(nom, info, budget):
    if "paquet" in info:
        try:
            return metadata.version(info["paquet"])
        except metadata.PackageNotFoundError:
            return None
    try:
        return _get_json(info["api"], budget, timeout=3).get("version")
    except Exception:
        return None


def source_versions(c, budget):
    nouvelles = []
    for nom, info in OUTILS.items():
        installee = version_installee(nom, info, budget)
        try:
            rel = _get_json(f"https://api.github.com/repos/{info['depot']}/releases/latest", budget)
        except Exception:
            continue
        derniere = rel.get("tag_name", "")
        if not installee or not derniere or _ver(derniere) <= _ver(installee):
            continue
        notes = _propre(rel.get("body"), 700)
        securite_mention = bool(re.search(r"secur|vuln|cve|fix", notes, re.I))
        fiche = fiche_type(
            titre=f"{nom} {derniere} est sortie (tu as {installee})", source="Versions",
            ce_qui_change=f"Nouvelle version publiée le {rel.get('published_at', '')[:10]}.",
            pourquoi=f"Jarvis utilise {nom}.", fichiers=info["fichiers"],
            benefice="Corrections de sécurité mentionnées." if securite_mention else "Corrections et nouveautés.",
            difficulte="faible", risque="moyen : tester avant (le routeur ou l'IA locale peuvent changer de comportement)",
            cout="aucun (gratuit)", recommandation="tester en bac à sable" if securite_mention else "surveiller",
            preuves=[{"lien": rel.get("html_url", ""), "version": derniere, "date": rel.get("published_at", "")[:10], "extrait": notes[:300]}],
            score=score(adequation=3, fraicheur=3, maintenance=3, compatibilite=2, benefice=2 + securite_mention, cout=1, risque=2))
        if _noter(c, f"version:{info['depot']}:{derniere}", fiche):
            nouvelles.append(fiche)
    return nouvelles


def paquets_installes(limite=400):
    vus = {}
    for d in metadata.distributions():
        nom = (d.metadata.get("Name") or "").lower()
        if nom and nom not in vus:
            vus[nom] = d.version
    return dict(list(sorted(vus.items()))[:limite])


def source_osv(c, budget):
    paquets = paquets_installes()
    if not paquets:
        return []
    noms = list(paquets)
    r = _get_json("https://api.osv.dev/v1/querybatch", budget,
                  data={"queries": [{"package": {"name": n, "ecosystem": "PyPI"}, "version": paquets[n]} for n in noms]})
    nouvelles = []
    for nom, res in zip(noms, r.get("results", [])):
        vids = sorted(v.get("id", "") for v in (res.get("vulns") or []))
        if vids:
            vid = vids[0] if len(vids) == 1 else f"{len(vids)} failles"
            fiche = fiche_type(
                titre=f"Mettre à jour {nom} {paquets[nom]} ({vid})", source="Alertes cyber",
                ce_qui_change="Une ou plusieurs failles publiées concernent la version installée sur ton PC.",
                pourquoi=f"Le paquet Python « {nom} » est installé (Jarvis ou ses outils peuvent l'utiliser).",
                fichiers="paquets Python du PC", benefice="Fermer une faille connue.", difficulte="faible (mise à jour pip)",
                risque="faible à moyen : relancer les tests après la mise à jour", cout="aucun",
                recommandation="tester en bac à sable",
                preuves=[{"lien": f"https://osv.dev/vulnerability/{v}", "version": paquets[nom], "date": time.strftime("%Y-%m-%d")}
                         for v in vids[:5]],
                score=score(adequation=3, fraicheur=3, maintenance=2, compatibilite=2, benefice=3, cout=1, risque=1))
            if _noter(c, f"osv:{nom}:{paquets[nom]}:{','.join(vids)}", fiche):
                nouvelles.append(fiche)
    return nouvelles


def source_kev(c, budget, jours=14):
    d = _get_json("https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json", budget, timeout=30)
    limite = time.strftime("%Y-%m-%d", time.localtime(time.time() - jours * 86400))
    nouvelles = []
    for v in d.get("vulnerabilities", []):
        if v.get("dateAdded", "") < limite:
            continue
        cible = f"{v.get('vendorProject', '')} {v.get('product', '')}".lower()
        if not any(l in cible for l in LOGICIELS_KEV):
            continue
        cve = v.get("cveID", "")
        fiche = fiche_type(
            titre=f"Faille exploitée : {v.get('vendorProject')} {v.get('product')} ({cve})", source="Alertes cyber",
            ce_qui_change=f"Ajoutée le {v.get('dateAdded')} au catalogue des failles activement exploitées.",
            pourquoi="Ce logiciel est peut-être sur ton PC : à mettre à jour.", fichiers="ton PC (pas Jarvis)",
            benefice="Éviter une attaque réelle en cours dans le monde.", difficulte="faible (mise à jour du logiciel)",
            risque="faible", cout="aucun", recommandation="mettre à jour dès que possible",
            preuves=[{"lien": f"https://nvd.nist.gov/vuln/detail/{cve}", "date": v.get("dateAdded"),
                      "extrait": _propre(v.get("shortDescription"), 300)}],
            score=score(adequation=2, fraicheur=3, maintenance=3, compatibilite=3, benefice=3, cout=1, risque=1))
        if _noter(c, f"kev:{cve}", fiche):
            nouvelles.append(fiche)
    return nouvelles


# ---------- Analyse approfondie d'un dépôt GitHub ----------

SCRIPTS_RISQUES = ["install.sh", "setup.py", "install.ps1", "postinstall", "Makefile"]


def analyser_depot(nom_complet, budget=None):
    """owner/repo → faits vérifiés + score expliqué. N'exécute RIEN, ne clone rien."""
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", nom_complet or ""):
        raise ValueError("nom de dépôt invalide")
    budget = budget or Budget(6)
    r = _get_json(f"https://api.github.com/repos/{nom_complet}", budget)
    faits = {"existe": True, "archive": bool(r.get("archived")), "dernier_push": (r.get("pushed_at") or "")[:10],
             "licence": ((r.get("license") or {}).get("spdx_id") or "aucune"), "etoiles": r.get("stargazers_count", 0),
             "issues_ouvertes": r.get("open_issues_count", 0), "fork": bool(r.get("fork")),
             "description": _propre(r.get("description"), 200), "lien": r.get("html_url", "")}
    try:
        rel = _get_json(f"https://api.github.com/repos/{nom_complet}/releases/latest", budget)
        faits["derniere_version"], faits["date_version"] = rel.get("tag_name", ""), (rel.get("published_at") or "")[:10]
    except Exception:
        faits["derniere_version"], faits["date_version"] = "", ""
    try:
        racine = _get_json(f"https://api.github.com/repos/{nom_complet}/contents/", budget)
        noms = {x.get("name", "") for x in racine if isinstance(x, dict)}
        faits["scripts_installation"] = sorted(n for n in noms if n in SCRIPTS_RISQUES)
        faits["integration_continue"] = ".github" in noms
    except Exception:
        faits["scripts_installation"], faits["integration_continue"] = [], False
    jours = (time.time() - time.mktime(time.strptime(faits["dernier_push"], "%Y-%m-%d"))) / 86400 if faits["dernier_push"] else 9999
    licence_ok = faits["licence"] in ("MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC", "MPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-3.0")
    facteurs = []
    def f(texte, points):
        facteurs.append({"facteur": texte, "points": points})
    f("maintenu (modifié il y a moins de 3 mois)" if jours < 90 else "peu actif" if jours < 365 else "abandonné (plus d'un an)",
      2 if jours < 90 else 0 if jours < 365 else -3)
    if faits["archive"]:
        f("archivé par son auteur", -4)
    f(f"licence {faits['licence']}" + ("" if licence_ok else " : à vérifier avant tout usage"), 1 if licence_ok else -2)
    if faits["etoiles"] >= 1000:
        f(f"{faits['etoiles']} étoiles (communauté)", 1)
    if faits["scripts_installation"]:
        f("contient des scripts d'installation : à lire avant d'installer", -1)
    if faits["integration_continue"]:
        f("tests automatiques sur GitHub", 1)
    if faits["fork"]:
        f("copie d'un autre projet : préférer l'original", -1)
    total = max(0, min(10, 5 + sum(x["points"] for x in facteurs)))
    return {"depot": nom_complet, "faits": faits, "score": total, "facteurs": facteurs,
            "recommandation": "ignorer" if total < 4 else "surveiller" if total < 7 else "tester en bac à sable",
            "rappel": "Rien n'est installé automatiquement."}


# ---------- Fiches et score expliqué ----------

def score(adequation, fraicheur, maintenance, compatibilite, benefice, cout, risque):
    """Note sur 10 + ce qui la fait monter ou baisser (chaque dimension de 0 à 3)."""
    plus = {"adéquation avec Jarvis": adequation, "fraîcheur": fraicheur, "maintenance": maintenance,
            "compatibilité": compatibilite, "bénéfice": benefice}
    moins = {"coût d'intégration": cout, "risque": risque}
    brut = sum(plus.values()) - sum(moins.values())  # de -6 à 15
    note = round(max(0, min(10, (brut + 6) * 10 / 21)), 1)
    return {"note": note, "monte": [k for k, v in plus.items() if v >= 2], "baisse": [k for k, v in moins.items() if v >= 2]}


def fiche_type(titre, source, ce_qui_change, pourquoi, fichiers, benefice, difficulte, risque, cout, recommandation, preuves, score):
    return {"titre": titre, "source": source, "ce_qui_change": ce_qui_change, "pourquoi_jarvis": pourquoi,
            "fichiers_concernes": fichiers, "benefice": benefice, "difficulte": difficulte, "risque": risque, "cout": cout,
            "recommandation": recommandation, "preuves": preuves, "score": score,
            "actions": ["analyser_plus", "feuille_de_route", "ignorer", "ne_plus_source"]}


# ---------- Lancement planifié ----------

def lancer(force=False):
    """Une passe : seulement les sources dont le cache a expiré, dans le budget. Rien de nouveau = rien à signaler."""
    c = _cache()
    budget = Budget()
    nouvelles, erreurs = [], []
    for cle, fn in (("kev", source_kev), ("osv", source_osv), ("version", source_versions)):
        if cle in c.get("sources_coupees", []) or (not force and _frais(c, cle, TTL[cle])):
            continue
        try:
            nouvelles += fn(c, budget)
            c["dernier"][cle] = time.time()
        except Exception as e:
            erreurs.append(f"{cle} : {type(e).__name__}")
    c["derniere_passe"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    c["derniere_resultat"] = {"date": c["derniere_passe"], "nouvelles": len(nouvelles),
                               "erreurs": erreurs, "requetes": BUDGET_APPELS - budget.reste}
    ecrire_json(CACHE, c)
    if nouvelles or erreurs:
        journaliser(agent="veille", action="decouvertes2", etat="info", statut="erreur" if erreurs and not nouvelles else "ok",
                    resume=f"{len(nouvelles)} nouvelle(s)" + (f", erreurs : {', '.join(erreurs)}" if erreurs else ""))
    return c["derniere_resultat"]


def fiches(statut=None, montrer=False):
    """montrer=True (la page Découvertes) : les nouvelles fiches utiles (note >= NOTE_MIN, MAX_FICHES au plus) sont notées
    « vues » ; JOURS_VISIBLE jours après, elles passent en « vue » et ne reviennent plus jamais."""
    c = _cache()
    vus, limite = c.setdefault("vus", {}), time.strftime("%Y-%m-%d", time.localtime(time.time() - JOURS_VISIBLE * 86400))
    change = False
    for ident, i in c["items"].items():
        if i["statut"] == "nouvelle" and ident in vus and vus[ident] < limite:
            i["statut"], change = "vue", True
    items = sorted(c["items"].values(), key=lambda x: (-x["score"]["note"], x["last_seen"]))
    if montrer:
        nouv = [i for i in items if i["statut"] in ("nouvelle", "a_analyser") and i["score"]["note"] >= NOTE_MIN][:MAX_FICHES]
        for i in nouv:
            if i["id"] not in vus:
                vus[i["id"]], change = time.strftime("%Y-%m-%d"), True
        items = nouv + [i for i in items if i not in nouv and i["statut"] not in ("nouvelle", "a_analyser")]
    if change:
        ecrire_json(CACHE, c)
    return [i for i in items if statut is None or i["statut"] == statut][:60]


def decider(ident, action):
    """Les boutons des fiches. Aucun n'installe quoi que ce soit."""
    c = _cache()
    it = c["items"].get(ident)
    if not it or action not in it["actions"]:
        raise ValueError("fiche ou action inconnue")
    it["historique"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "action": action})
    if action == "ignorer":
        it["statut"] = "ignoree"
    elif action == "feuille_de_route":
        it["statut"] = "feuille_de_route"
        a = lire_json(AJOUTS_FEUILLE, [])
        a.append({"t": time.strftime("%Y-%m-%d"), "titre": it["titre"], "lien": (it["preuves"] or [{}])[0].get("lien", "")})
        ecrire_json(AJOUTS_FEUILLE, a[-100:])
    elif action == "ne_plus_source":
        it["statut"] = "ignoree"
        cle = ident.split(":", 1)[0]
        c.setdefault("sources_coupees", [])
        if cle not in c["sources_coupees"]:
            c["sources_coupees"].append(cle)
    elif action == "analyser_plus":
        it["statut"] = "a_analyser"  # le Directeur en fait une mission (budget limité)
    ecrire_json(CACHE, c)
    return it


# ---------- Registre des candidats (skills, outils, dépôts) ----------

ETATS_CANDIDAT = ["decouvert", "analyse", "prototype", "approuve", "integre", "surveille", "rejete", "desactive"]
TRANSITIONS = {"decouvert": {"analyse", "rejete", "surveille"}, "analyse": {"prototype", "rejete", "surveille"},
               "surveille": {"analyse", "rejete"}, "prototype": {"approuve", "rejete"}, "approuve": {"integre", "rejete"},
               "integre": {"desactive"}, "desactive": {"integre", "rejete"}, "rejete": {"analyse"}}
DEMANDE_UTILISATEUR = {"approuve", "integre"}  # ces étapes passent par « Décisions pour moi »


def candidat(nom, source, lien, version="", licence="", capacites="", permissions="", besoin=""):
    d = lire_json(CANDIDATS, {})
    ident = re.sub(r"[^a-z0-9]+", "-", nom.lower()).strip("-")[:50]
    d.setdefault(ident, {"id": ident, "nom": nom[:80], "source": source[:80], "lien": lien[:300], "version": version[:40],
                         "licence": licence[:30], "capacites": capacites[:300], "permissions": permissions[:300],
                         "besoin": besoin[:300], "etat": "decouvert", "decouvert_le": time.strftime("%Y-%m-%d"),
                         "verifie_le": "", "essais": [], "utilisations": 0, "mesures": [], "retrait": "", "historique": []})
    ecrire_json(CANDIDATS, d)
    return d[ident]


def changer_etat(ident, etat, origine, raison=""):
    """Chaque passage est vérifié. Approuver ou intégrer demande une origine humaine (la page)."""
    d = lire_json(CANDIDATS, {})
    c = d.get(ident)
    if not c or etat not in TRANSITIONS.get(c["etat"], set()):
        raise ValueError("passage non autorisé")
    if etat in DEMANDE_UTILISATEUR and origine != "page":
        raise PermissionError("Seul l’utilisateur approuve ou intègre un nouvel outil.")
    c["historique"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "de": c["etat"], "vers": etat, "par": origine, "raison": raison[:200]})
    c["etat"], c["verifie_le"] = etat, time.strftime("%Y-%m-%d")
    ecrire_json(CANDIDATS, d)
    return c


def candidats():
    return sorted(lire_json(CANDIDATS, {}).values(), key=lambda c: c["decouvert_le"], reverse=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) > 2 and sys.argv[1] == "depot":
        print(json.dumps(analyser_depot(sys.argv[2]), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(lancer(force="--force" in sys.argv), ensure_ascii=False))
