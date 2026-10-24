r"""Mission 10 — Découvertes : analyser VRAIMENT un dépôt GitHub, pas à pas, sans jamais rien installer ni exécuter.

Étapes visibles : README, releases, licence, activité (commits, langages, issues), failles connues (avis de sécurité GitHub),
scripts d'installation (curl | bash, binaires, post-install), avis de l'IA (ce que ça fait, utile ou non pour Jarvis,
risques, intégration, effort). Tout ce qui vient du dépôt est une DONNÉE (encadrée, contrôlée contre l'injection).
Résultat gardé dans donnees\depots.json ; une amélioration possible pour Jarvis devient une proposition dans Décisions.
"""
import base64, re, threading, time, uuid

from commun import DONNEES, lire_json, ecrire_json, journaliser, demander, extraire_json
from suite import decouvertes2
import securite

RESULTATS = DONNEES / "depots.json"
DANGER = [(r"curl[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b", "commande « curl … | sh » (exécute un script venu d'Internet)"),
          (r"wget[^\n|]{0,200}\|\s*(sudo\s+)?(ba|z)?sh\b", "commande « wget … | sh »"),
          (r"iwr[^\n|]{0,200}\|\s*iex|Invoke-Expression|irm[^\n|]{0,200}\|\s*iex", "PowerShell « … | iex » (exécute un script venu d'Internet)"),
          (r"\"(pre|post)install\"\s*:", "script « postinstall » dans package.json (lancé tout seul à l'installation)"),
          (r"\bsudo\s+(rm|chmod\s+777|curl)", "commande sudo risquée"),
          (r"base64\s+-d[^\n]{0,80}\|\s*(ba)?sh", "script caché en base64")]
BINAIRES = (".exe", ".dll", ".msi", ".bin", ".so", ".dylib", ".jar", ".apk", ".deb", ".rpm", ".pkg", ".dmg")
INSTALL = ("install.sh", "install.ps1", "setup.sh", "setup.py", "package.json", "Makefile", "bootstrap.sh", "get.sh", "install.bat")
_etat = {}
_verrou = threading.Lock()


def _b64(f):
    return base64.b64decode(f.get("content", "") or "").decode("utf-8", "replace")


def _etape(ident, texte, **faits):
    _etat[ident]["etapes"].append(texte)
    _etat[ident].update(etape=texte, **faits)


def _travailler(ident, nom):
    e, b = _etat[ident], decouvertes2.Budget(14)
    g = lambda chemin: decouvertes2._get_json(f"https://api.github.com/repos/{nom}{chemin}", b)
    try:
        _etape(ident, "Lecture du README…")
        repo = g("")
        try:
            readme = _b64(g("/readme"))[:20000]
        except Exception:
            readme = ""
        pieges = securite.analyser(readme) if readme else []
        if pieges:
            securite.alerter("depot", readme[:200], pieges)
        _etape(ident, "Releases…")
        try:
            rel = [{"version": r.get("tag_name", ""), "date": (r.get("published_at") or "")[:10],
                    "binaires": [a["name"] for a in r.get("assets", []) if a.get("name", "").lower().endswith(BINAIRES)][:6]} for r in g("/releases?per_page=5")]
        except Exception:
            rel = []
        _etape(ident, "Licence…")
        licence = (repo.get("license") or {}).get("spdx_id") or "aucune"
        _etape(ident, "Activité…")
        try:
            commits = [{"date": (c.get("commit", {}).get("author", {}).get("date") or "")[:10],
                        "message": securite.masquer_secrets((c.get("commit", {}).get("message") or "").splitlines()[0])[:100]} for c in g("/commits?per_page=8")]
        except Exception:
            commits = []
        try:
            langages = list(g("/languages").keys())[:6]
        except Exception:
            langages = []
        _etape(ident, "Failles connues…")
        try:
            failles = [{"id": a.get("ghsa_id", ""), "gravite": a.get("severity", ""), "resume": (a.get("summary") or "")[:160],
                        "date": (a.get("published_at") or "")[:10]} for a in g("/security-advisories?per_page=10")]
        except Exception:
            failles = []  # pas d'avis publiés (ou dépôt sans cette page) : on le dit tel quel
        _etape(ident, "Scripts d'installation…")
        try:
            racine = {x.get("name", ""): x for x in g("/contents/") if isinstance(x, dict)}
        except Exception:
            racine = {}
        dangers, lus = [], []
        textes = [("README", readme)]
        for n in [n for n in INSTALL if n in racine][:3]:
            try:
                textes.append((n, _b64(g(f"/contents/{n}"))[:30000]))
                lus.append(n)
            except Exception:
                pass
        for n, t in textes:
            for motif, quoi in DANGER:
                if re.search(motif, t, re.I):
                    dangers.append(f"{n} : {quoi}")
        binaires = sorted(n for n in racine if n.lower().endswith(BINAIRES)) + sorted({x for r in rel for x in r["binaires"]})
        if binaires:
            dangers.append("binaires fournis (programmes déjà compilés, on ne peut pas lire leur code) : " + ", ".join(binaires[:6]))
        faits = {"depot": nom, "lien": repo.get("html_url", ""), "description": (repo.get("description") or "")[:300], "etoiles": repo.get("stargazers_count", 0),
                 "archive": bool(repo.get("archived")), "dernier_push": (repo.get("pushed_at") or "")[:10], "issues_ouvertes": repo.get("open_issues_count", 0),
                 "licence": licence, "langages": langages, "releases": rel, "commits": commits, "failles": failles, "dangers": dangers,
                 "fichiers_lus": lus, "injection": bool(pieges)}
        _etape(ident, "Avis de l'IA…")
        msg, modele = demander("jarvis-rapide", [
            {"role": "system", "content": securite.CONSIGNE_DONNEES + " Tu analyses un dépôt GitHub pour Jarvis, l'assistant local de l’utilisateur "
             "(Python, site HTML/JS, routeur LiteLLM, Ollama, agents IA ; tout sur 127.0.0.1, rien de payant). Jarvis utilise DÉJÀ : Ollama "
             "(Qwen3 14B), LiteLLM, ffmpeg, yt-dlp, faster-whisper, Claude Code, un bot Telegram : ne propose jamais ce qu'il a déjà ; "
             "\"proposition\" seulement pour une vraie idée nouvelle et petite. Réponds UNIQUEMENT en JSON : "
             "{\"ce_que_ca_fait\": \"2 phrases\", \"utile\": \"oui|peut-être|non\", \"pourquoi\": \"1 phrase\", \"risques\": [\"…\"], "
             "\"integration\": \"comment l'intégrer à Jarvis, 2 phrases (sans rien installer seul)\", \"effort\": \"petit|moyen|gros\", "
             "\"proposition\": null ou {\"titre\": \"amélioration concrète de Jarvis inspirée du dépôt\", \"demande\": \"la demande exacte, "
             "ex. « Dans jarvis/… , … »\"}}. Français simple."},
            {"role": "user", "content": "Faits vérifiés : " + str({k: v for k, v in faits.items() if k not in ("commits",)})[:6000]
             + "\n\n" + securite.encadrer(readme[:8000], "README du dépôt")}], max_tokens=900, temperature=0.2)
        avis = extraire_json(msg.get("content") or "") or {"ce_que_ca_fait": (msg.get("content") or "")[:600]}
        r = {"id": ident, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), **faits, "avis": avis, "modele": modele, "requetes": 14 - b.reste}
        p = avis.get("proposition") if isinstance(avis.get("proposition"), dict) else None
        if p and str(p.get("titre", "")).strip() and str(p.get("demande", "")).strip():
            from suite import cycle, idees  # mission 15 : une idée de Jarvis va dans la boîte à idées, pas dans Décisions
            cle = cycle._cle(str(p["titre"]))
            deja = lire_json(cycle.PROPOSITIONS_DIR, {})
            if cle not in deja:
                idees.ajouter("dep-" + cle, f"{str(p['titre'])[:100]} (vu dans {nom})", str(avis.get("pourquoi", "")), str(avis.get("effort", "petit")),
                              "decouvertes", str(p["demande"]))
                deja[cle] = {"titre": str(p["titre"])[:120], "etat": "proposee", "t": r["t"]}
                ecrire_json(cycle.PROPOSITIONS_DIR, deja)
                r["proposition_creee"] = True
        with _verrou:
            ecrire_json(RESULTATS, ([x for x in lire_json(RESULTATS, []) if x.get("depot") != nom] + [r])[-30:])
        e.update(en_cours=False, etape="Terminé", resultat=r)
        journaliser(agent="veille", action="analyser un dépôt", etat="info", statut="ok", resume=nom)
    except Exception as x:
        e.update(en_cours=False, etape="Erreur", erreur=f"{type(x).__name__} : {securite.masquer_secrets(str(x))[:200]}")
        journaliser(agent="veille", action="analyser un dépôt", etat="info", statut="erreur", resume=f"{nom} : {type(x).__name__}")


def lancer(nom):
    nom = re.sub(r"^https?://github\.com/", "", str(nom or "").strip()).strip("/")[:120]
    nom = re.sub(r"\.git$", "", nom)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", nom):
        raise ValueError("Donne un dépôt sous la forme auteur/projet ou son lien GitHub.")
    with _verrou:
        if any(v.get("en_cours") for v in _etat.values()):
            raise RuntimeError("Une analyse est déjà en cours.")
        ident = uuid.uuid4().hex[:8]
        _etat[ident] = {"id": ident, "depot": nom, "en_cours": True, "etape": "Préparation…", "etapes": []}
    threading.Thread(target=_travailler, args=(ident, nom), daemon=True, name="depot").start()
    return ident


def etat(ident=None):
    if ident:
        return _etat.get(ident)
    return {"en_cours": [v for v in _etat.values() if v.get("en_cours")], "resultats": list(reversed(lire_json(RESULTATS, [])))[:10]}
