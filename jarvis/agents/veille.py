r"""Agent de veille de Jarvis — une fois par jour maximum.

Sources : GitHub (dépôts récents qui montent), Tavily (web, 30 recherches/jour max),
YouTube (flux RSS officiels, sans clé), CERT-FR (alertes et avis), mises à jour
de LiteLLM / Ollama, et les modèles via maj_modeles.py.
Le profil « jarvis-rapide » transforme les trouvailles en fiches ; 10 fiches max par jour.
Rien ne s'installe : on PROPOSE, l'utilisateur décide (page jarvis.html ou donnees\propositions.json).

Usage : py -3 veille.py           (ne fait rien si déjà lancé aujourd'hui)
        py -3 veille.py --force   (relance quand même ; le budget Tavily reste respecté)
"""
import sys, os, re, json, hashlib, datetime, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from commun import DONNEES, RACINE, ROUTEUR, http_json, lire_json, ecrire_json, demander, activite, extraire_json  # noqa: E402
import maj_modeles  # noqa: E402
import securite  # noqa: E402

ETAT = DONNEES / "veille-etat.json"
VUS = DONNEES / "vus.json"
PROPOSITIONS = DONNEES / "propositions.json"
CHAINES = DONNEES / "chaines-youtube.json"
E = os.environ
MAX_FICHES = 5      # mission 4 : 5 trouvailles maximum par jour, une par source si possible
GROUPES = ["GitHub", "Web", "YouTube", "Alertes cyber"]
NOTE_MIN = 5        # sur 10 : en dessous, la trouvaille est écartée (et ne reviendra pas)
NOTE_MIN_GROUPE = {}
# Mission 6 (choix de l'utilisateur) : moins de bruit. Une fiche seulement si elle vaut vraiment le coup (≥ 8) ;
# entre 5 et 8, elle va dans le résumé de la semaine (une seule fiche par semaine) ; cyber : 1 fiche par semaine au plus,
# sauf une faille grave qui touche son PC ou Jarvis (≥ 9).
NOTE_FICHE = 8
NOTE_GRAVE = 9
SEMAINE = DONNEES / "decouvertes-semaine.json"
BUDGET_TAVILY = 30

PROFIL_DEMO = ("Profil de démonstration : personne débutante en informatique, intéressée par le support, "
               "les systèmes et les outils libres. Ne déduis aucune donnée personnelle ou localisation.")

GITHUB_SUJETS = ["topic:ai-agents", "topic:mcp", "topic:llm", "topic:developer-tools", "topic:web-development",
                 "topic:self-hosted", "topic:cybersecurity"]  # IA et agents, dev web et outils, un peu de cyber
TAVILY_REQUETES = [
    "nouveautés agents IA MCP outils pour développeurs",
    "nouvel outil open source développement web",
    "astuce productivité développeur outil gratuit",
]
# « Nouveautés IA » : une recherche par semaine sur les nouveaux modèles, outils et techniques utiles à Jarvis
REQUETE_NOUVEAUTES_IA = "nouveaux modèles IA open source, outils et techniques pour agents IA locaux cette semaine"


def lire_url(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 jarvis-veille"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def court(texte, n=220):
    texte = re.sub(r"<[^>]+>", " ", texte or "")
    return re.sub(r"\s+", " ", texte).strip()[:n]


# ---------- Sources ----------

def source_github(depuis):
    h = {"Authorization": "Bearer " + E.get("GITHUB_TOKEN", ""), "Accept": "application/vnd.github+json"}
    out = []
    for sujet in GITHUB_SUJETS:
        q = urllib.parse.quote(f"{sujet} created:>{depuis} stars:>20")
        r = http_json(f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page=4", headers=h)
        for d in r.get("items", []):
            out.append({"source": "GitHub", "titre": d["full_name"], "lien": d["html_url"],
                        "desc": f"★{d['stargazers_count']} · {d.get('language') or ''} · {court(d.get('description'))}"})
    return out


def source_tavily(etat):
    jour = datetime.date.today().isoformat()
    compteur = etat.setdefault("tavily", {})
    out = []
    requetes = list(TAVILY_REQUETES)
    if etat.get("nouveautes_ia", "2000-01-01") <= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
        requetes.append(REQUETE_NOUVEAUTES_IA)
        etat["nouveautes_ia"] = jour
    for q in requetes:
        if compteur.get(jour, 0) >= BUDGET_TAVILY:
            break
        compteur[jour] = compteur.get(jour, 0) + 1
        r = http_json("https://api.tavily.com/search",
                      {"query": q, "max_results": 4, "time_range": "week", "search_depth": "basic"},
                      {"Authorization": "Bearer " + E.get("TAVILY_API_KEY", "")})
        for d in r.get("results", []):
            out.append({"source": "Web", "titre": court(d.get("title"), 120), "lien": d["url"],
                        "desc": ("[Nouveautés IA] " if q == REQUETE_NOUVEAUTES_IA else "") + court(d.get("content"))})
    etat["tavily"] = {jour: compteur.get(jour, 0)}  # on ne garde que le jour en cours
    return out


def lire_rss(url, limite_jours, max_items):
    """Lit un flux RSS 2.0 ou Atom. Renvoie [(titre, lien, date, résumé)]."""
    racine = ET.fromstring(lire_url(url))
    ns = {"a": "http://www.w3.org/2005/Atom", "m": "http://search.yahoo.com/mrss/"}
    seuil = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=limite_jours)
    items = []
    for it in racine.iter("item"):
        d = it.findtext("pubDate") or ""
        try:
            date = datetime.datetime.strptime(d[:25].strip(), "%a, %d %b %Y %H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            date = seuil
        items.append((it.findtext("title"), it.findtext("link"), date, it.findtext("description")))
    for it in racine.findall("a:entry", ns):
        date = datetime.datetime.fromisoformat(it.findtext("a:published", "", ns).replace("Z", "+00:00"))
        lien = it.find("a:link", ns).get("href")
        items.append((it.findtext("a:title", "", ns), lien, date, it.findtext("m:group/m:description", "", ns)))
    return [i for i in items if i[2] >= seuil][:max_items]


def source_youtube():
    out = []
    for c in lire_json(CHAINES, {}).get("chaines", []):
        try:
            for titre, lien, _, desc in lire_rss(f"https://www.youtube.com/feeds/videos.xml?channel_id={c['channel_id']}", 3, 2):
                out.append({"source": f"YouTube · {c['nom']}", "titre": titre, "lien": lien, "desc": court(desc)})
        except Exception:
            continue  # une chaîne en panne ne bloque pas les autres
    return out


def source_certfr():
    out = []
    for flux, jours, nb in (("alerte", 14, 5), ("avis", 7, 8)):
        for titre, lien, _, desc in lire_rss(f"https://www.cert.ssi.gouv.fr/{flux}/feed/", jours, nb):
            out.append({"source": f"CERT-FR {flux}", "titre": titre, "lien": lien, "desc": court(desc)})
    return out


def source_mises_a_jour():
    """Fiches directes (pas besoin de l'IA) si LiteLLM ou Ollama ont une version plus récente QUI CORRIGE UNE FAILLE
    (mission 6 : plus de fiche pour une petite version ; la page Découvertes 2.0 suit toutes les versions)."""
    fiches = []
    try:
        installee = metadata.version("litellm")
        derniere = http_json("https://pypi.org/pypi/litellm/json")["info"]["version"]
        failles = http_json(f"https://pypi.org/pypi/litellm/{installee}/json").get("vulnerabilities") or []
        if derniere != installee and failles:
            fiches.append(fiche_systeme(f"LiteLLM {derniere} disponible (tu as {installee})",
                                        f"https://pypi.org/project/litellm/{derniere}/",
                                        "Nouvelle version du routeur IA. Elle peut corriger des bugs ou ajouter des fournisseurs ; "
                                        "à installer seulement si quelque chose ne marche plus, après avoir sauvegardé config.yaml.",
                                        "moyen", "Une mise à jour du routeur peut changer son comportement.",
                                        "10 min : py -3 -m pip install -U litellm"))
    except Exception:
        pass
    try:
        installee = http_json("http://127.0.0.1:11434/api/version")["version"]
        rel = http_json("https://api.github.com/repos/ollama/ollama/releases/latest",
                        headers={"Authorization": "Bearer " + E.get("GITHUB_TOKEN", "")})
        derniere = rel["tag_name"].lstrip("v")
        if derniere != installee and re.search(r"secur|CVE|vuln", rel.get("body") or "", re.I):
            fiches.append(fiche_systeme(f"Ollama {derniere} disponible (tu as {installee})", rel["html_url"],
                                        "Nouvelle version du moteur d'IA locale. Souvent plus rapide et compatible avec les nouveaux modèles.",
                                        "faible", "Mise à jour officielle, les modèles déjà téléchargés sont gardés.",
                                        "5 min : winget upgrade Ollama.Ollama"))
    except Exception:
        pass
    return fiches


def fiche_systeme(titre, lien, pour, risque, raison, effort):
    return {"titre": titre, "lien": lien, "pour_toi": pour, "categorie": "Mes outils", "risque": risque,
            "risque_raison": raison, "effort": effort, "avis": "à ajouter", "source": "Mises à jour"}


# ---------- Fiches par l'IA ----------

def groupe(source):
    """GitHub, Web, YouTube ou Alertes cyber (CERT-FR)."""
    return "Alertes cyber" if source.startswith("CERT-FR") else "YouTube" if source.startswith("YouTube") else source


def melanger(candidats):
    """Alterne les sources (1 GitHub, 1 web, 1 YouTube, 1 alerte…) pour qu'aucune ne soit coupée par la limite de taille du prompt."""
    files = {g: [c for c in candidats if groupe(c["source"]) == g] for g in GROUPES}
    out = []
    while any(files.values()):
        for g in GROUPES:
            if files[g]:
                out.append(files[g].pop(0))
    return out + [c for c in candidats if groupe(c["source"]) not in GROUPES]


def noter(candidats):
    """1er appel : l'IA note chaque trouvaille de 0 à 10 pour l'utilisateur (réponse courte). Renvoie ({index: note}, modèle)."""
    liste = "\n".join(f"{i}. [{groupe(c['source'])}] {c['titre']} — {c['desc']}" for i, c in enumerate(candidats))
    consigne = (
        f"{PROFIL_DEMO}\n\nVoici des trouvailles du jour :\n{securite.encadrer(liste, 'veille')}\n\n"
        "Note chacune de 0 à 10 selon son utilité pour l'utilisateur et pour Jarvis, son assistant. Ce qui compte le plus : l'IA et les agents "
        "(nouveaux modèles, outils, techniques utiles à Jarvis), le développement web et les outils de développeur. La cybersécurité "
        "compte un peu moins. Une faille grave et exploitée sur ce qu'il utilise (Windows, son navigateur, Python, Ollama, LiteLLM) "
        "vaut 9 ou 10 ; une alerte sur un produit d'entreprise qu'il n'a pas vaut 2 au plus ; une petite mise à jour sans vrai gain vaut 2. "
        "Une vidéo ou un article qui lui apprend quelque chose d'utile vaut autant qu'un outil.\n"
        'Réponds UNIQUEMENT en JSON : {"notes": {"<numéro>": <note>, ...}} pour TOUS les numéros.'
    )
    # Aucun outil fourni : cet agent lit du contenu externe, il ne peut donc que produire du texte.
    msg, modele = demander("jarvis-rapide", [{"role": "system", "content": securite.CONSIGNE_DONNEES},
                                             {"role": "user", "content": consigne}],
                           max_tokens=3000, temperature=0, response_format={"type": "json_object"})
    brut = extraire_json(msg.get("content"))
    notes = {}
    for k, v in (brut.get("notes", brut) if isinstance(brut, dict) else {}).items():
        try:
            if 0 <= int(k) < len(candidats):
                notes[int(k)] = max(0, min(10, float(v)))
        except (TypeError, ValueError):
            continue
    return notes, modele


def choisir(candidats, notes, nb, cyber_ok=True):
    """Seulement ce qui vaut vraiment une fiche (≥ NOTE_FICHE), en variant les sources. Une seule alerte cyber, et seulement si
    aucune fiche cyber cette semaine (cyber_ok), sauf une faille grave (≥ NOTE_GRAVE)."""
    cyber = lambda i: groupe(candidats[i]["source"]) == "Alertes cyber"
    par_note = [i for i in sorted(notes, key=lambda i: -notes[i]) if notes[i] >= NOTE_FICHE and (not cyber(i) or cyber_ok or notes[i] >= NOTE_GRAVE)]
    choix = []
    for g in GROUPES:
        i = next((i for i in par_note if groupe(candidats[i]["source"]) == g), None)
        if i is not None:
            choix.append(i)
    choix += [i for i in par_note if i not in choix and not cyber(i)]
    return choix[:nb]


def ecrire_fiches(choisis):
    """2e appel : les fiches des trouvailles choisies, en mots de tous les jours."""
    liste = "\n".join(f"{n}. [{groupe(c['source'])}] {c['titre']} — {c['desc']}" for n, c in enumerate(choisis))
    consigne = (
        f"{PROFIL_DEMO}\n\nÉcris une fiche pour chacune de ces trouvailles :\n{securite.encadrer(liste, 'veille')}\n\n"
        "Réponds UNIQUEMENT par ce JSON :\n"
        '{"fiches":[{"n":<numéro>,"titre_simple":"<nom court en mots simples, 6 mots max>",'
        '"pour_toi":"<à quoi ça lui sert : 2 phrases courtes>",'
        '"categorie":"<Cyber|Réseau|Systèmes|Dev web|IA|Agents IA|Vidéo|Alerte sécurité|Vie pratique>",'
        '"risque":"<faible|moyen|élevé>","risque_raison":"<1 phrase>","effort":"<ex : 5 min, 1 h, une soirée>"}]}\n'
        "Tutoie l'utilisateur. Mots de tous les jours, pas de jargon ni de sigle sans explication : écris « outil qui repère les failles "
        "connues », pas « framework MITRE ATT&CK ». Ton positif, sans émoji."
    )
    msg, modele = demander("jarvis-rapide", [{"role": "system", "content": securite.CONSIGNE_DONNEES},
                                             {"role": "user", "content": consigne}],
                           max_tokens=3000, temperature=0.2, response_format={"type": "json_object"})
    brut = extraire_json(msg.get("content"))
    fiches = []
    for f in (brut.get("fiches", []) if isinstance(brut, dict) else brut):
        try:
            c = choisis[int(f["n"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        fiches.append({"titre": c["titre"], "lien": c["lien"], "source": c["source"], "avis": "à ajouter",
                       **{k: str(f.get(k, "")) for k in ("titre_simple", "pour_toi", "categorie", "risque", "risque_raison", "effort")}})
    return fiches, modele


def faire_fiches(candidats, nb, cyber_ok=True):
    """Renvoie (fiches, modèle, liens à ne plus proposer, trouvailles pour le résumé de la semaine).
    Une trouvaille correcte (5 à 8) ne devient pas une fiche : elle part dans le résumé de la semaine, sans déranger l'utilisateur."""
    if not candidats or nb <= 0:
        return [], "", set(), []
    notes, modele = noter(candidats)
    choix = choisir(candidats, notes, nb, cyber_ok)
    fiches, modele2 = ecrire_fiches([candidats[i] for i in choix]) if choix else ([], "")
    ecartes = {candidats[i]["lien"] for i, n in notes.items() if n < NOTE_MIN_GROUPE.get(groupe(candidats[i]["source"]), NOTE_MIN)}
    semaine = [{"titre": candidats[i]["titre"], "lien": candidats[i]["lien"], "source": groupe(candidats[i]["source"]), "note": n}
               for i, n in notes.items() if i not in choix and NOTE_MIN <= n]
    return fiches, modele2 or modele, ecartes | {f["lien"] for f in fiches} | {s["lien"] for s in semaine}, semaine


def resume_semaine(trouvailles):
    """Une seule fiche par semaine qui résume les trouvailles correctes, au lieu d'une fiche chacune."""
    liste = "\n".join(f"- [{t['source']}] {t['titre']} ({t['lien']})" for t in sorted(trouvailles, key=lambda t: -t["note"])[:25])
    msg, modele = demander("jarvis-rapide", [{"role": "system", "content": securite.CONSIGNE_DONNEES}, {"role": "user", "content":
        f"{PROFIL_DEMO}\n\nRésume en 5 lignes au plus ce qui est sorti cette semaine d'utile pour le profil et pour Jarvis "
        f"(IA et agents d'abord, puis dev web et outils, puis cyber). Tutoie-le, mots simples, sans émoji ni lien.\n{securite.encadrer(liste, 'veille')}"}],
        max_tokens=600, temperature=0.2)
    return {"titre": f"Résumé de la semaine ({len(trouvailles)} trouvailles)", "titre_simple": "Résumé de la semaine", "lien": "",
            "source": "Résumé", "categorie": "Résumé de la semaine", "pour_toi": (msg.get("content") or "").strip()[:900],
            "risque": "faible", "risque_raison": "Rien à installer : c'est un résumé.", "effort": "2 min de lecture", "avis": "à ajouter"}, modele


# ---------- Programme ----------

def ident(lien):
    return hashlib.sha1(lien.encode()).hexdigest()[:10]


def norme(titre):
    """Titre comparable : « bl4ckr0ss3/ttpscope » et « TTPScope » deviennent « ttpscope »."""
    t = str(titre).lower()
    return re.sub(r"[^a-z0-9]+", " ", t.split("/")[-1] if re.fullmatch(r"[\w.-]+/[\w.-]+", t) else t).strip()


def routeur_pret(attente=30):
    """Mission 13 : la veille n'allume JAMAIS le routeur (seul JARVIS.bat le fait). Elle attend un peu qu'il réponde, sinon
    elle passe son tour."""
    import time
    fin = time.time() + attente
    while True:
        try:
            if http_json(ROUTEUR + "/health/liveliness", timeout=3) is not None:
                return True
        except Exception:
            pass
        if time.time() >= fin:
            return False
        time.sleep(5)


def lancer(force=False, essai=False):
    """essai=True : tout est cherché, noté et rédigé, mais rien n'est enregistré (propositions, « déjà vus », date)."""
    jour = datetime.date.today().isoformat()
    etat = lire_json(ETAT, {})
    if etat.get("dernier_lancement") == jour and not force:
        print("Veille déjà faite aujourd'hui (utilise --force pour relancer).")
        return {"deja_fait": True}
    from commun import arret_actif
    if arret_actif():
        print("Arrêt d'urgence actif : veille annulée.")
        return {"erreur": "arrêt d'urgence actif"}
    if not routeur_pret():
        # On ne marque pas la journée comme faite : le prochain lancement réessaiera.
        print("Routeur IA injoignable : veille reportée (lance JARVIS.bat).")
        return {"erreur": "routeur injoignable"}

    with activite("veille", "lancement") as info:
        vus = set(lire_json(VUS, []))
        depuis = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
        candidats, erreurs = [], []
        for nom, f in (("GitHub", lambda: source_github(depuis)), ("Web/Tavily", lambda: source_tavily(etat)),
                       ("YouTube", source_youtube), ("CERT-FR", source_certfr)):
            try:
                candidats += f()
            except Exception as e:
                erreurs.append(f"{nom} : {type(e).__name__}")

        # Fiches « système » (modèles disparus/nouveaux, mises à jour) : 1 au plus, pour laisser 4 places aux 4 sources
        systeme = []
        try:
            systeme += [{k: p[k] for k in ("titre", "lien", "pour_toi", "categorie", "risque", "risque_raison", "effort", "avis", "source")}
                        for p in maj_modeles.main()]
        except Exception as e:
            erreurs.append(f"maj_modeles : {type(e).__name__}")
        systeme += source_mises_a_jour()
        # dédoublonnage par titre pour les fiches système (le lien est le même pour tout un fournisseur)
        systeme = [s for s in systeme if ident(s["titre"]) not in vus][:1]

        # Déduplication avec les jours précédents : même lien, ou même titre (une info déjà vue sous une autre forme est fusionnée)
        deja_titres = {norme(p.get("titre", "")) for p in lire_json(PROPOSITIONS, {}).get("propositions", [])}
        uniques, liens, titres = [], set(), set(deja_titres)
        for c in candidats:
            if c["lien"] and c["lien"] not in vus and c["lien"] not in liens and norme(c["titre"]) not in titres:
                liens.add(c["lien"]); titres.add(norme(c["titre"])); uniques.append(c)
        fusionnes = len(candidats) - len(uniques)
        uniques = melanger(securite.filtrer(uniques, "veille"))[:70]  # bloque les pages piégées ; toutes les sources restent dans le prompt

        cyber_ok = etat.get("cyber_semaine", "2000-01-01") <= (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        fiches, modele, a_oublier, semaine = [], "", set(), []
        try:
            fiches, modele, a_oublier, semaine = faire_fiches(uniques, MAX_FICHES - len(systeme), cyber_ok)
        except Exception as e:
            erreurs.append(f"fiches IA : {type(e).__name__}")
        en_attente = lire_json(SEMAINE, []) + semaine
        if en_attente and etat.get("resume_hebdo", "2000-01-01") <= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
            try:
                f, _ = resume_semaine(en_attente)
                fiches.append(f)
                en_attente = []
                if not essai:
                    etat["resume_hebdo"] = jour
            except Exception as e:
                erreurs.append(f"résumé de la semaine : {type(e).__name__}")
        info["modele"] = modele
        if essai:
            info["resume"] = f"essai : {len(fiches)} fiches sur {len(uniques)} trouvailles"
            return {"fiches": systeme + fiches, "trouvailles": len(uniques), "modele": modele, "erreurs": erreurs,
                    "par_source": {g: sum(1 for c in uniques if groupe(c["source"]) == g) for g in GROUPES}}

        ecrire_json(SEMAINE, en_attente[-200:])
        if any(groupe(f["source"]) == "Alertes cyber" for f in fiches):
            etat["cyber_semaine"] = jour
        nouvelles = []
        for f in systeme + fiches:
            cle = ident(f["titre"]) if f["source"] in ("maj_modeles", "Mises à jour", "Résumé") else ident(f["lien"])
            nouvelles.append({"id": cle, "date": jour, "statut": "nouvelle", **f})

        # « pas utile » après « à ajouter », comme demandé : les meilleures d'abord
        nouvelles.sort(key=lambda f: f["avis"] != "à ajouter")
        tout = lire_json(PROPOSITIONS, {}).get("propositions", [])
        deja = {p["id"] for p in tout}
        tout = [n for n in nouvelles if n["id"] not in deja] + tout
        ecrire_json(PROPOSITIONS, {"maj": datetime.datetime.now().isoformat(timespec="seconds"),
                                   "erreurs": erreurs, "propositions": tout[:300]})

        vus |= a_oublier | {ident(s["titre"]) for s in systeme}  # les bonnes trouvailles non choisies pourront revenir demain
        ecrire_json(VUS, sorted(vus)[-5000:])
        etat["dernier_lancement"] = jour
        ecrire_json(ETAT, etat)
        info["resume"] = f"{len(nouvelles)} fiches sur {len(uniques)} trouvailles, {fusionnes} doublons fusionnés, {len(semaine)} pour le résumé"
        try:  # une fois par semaine, Jarvis propose aussi d'améliorer son propre code (il vérifie lui-même la date)
            import ameliorer
            ameliorer.lancer()
        except Exception as e:
            erreurs.append(f"auto-amélioration : {type(e).__name__}")
        if nouvelles:
            try:
                import telegram_bot
                telegram_bot.notifier(f"Découvertes : {len(nouvelles)} trouvaille(s) pour toi. Tape /decouvertes pour les voir.")
            except Exception:
                pass
        print(f"Veille : {len(uniques)} trouvailles nouvelles, {len(nouvelles)} fiches. Modèle : {modele or '-'}. "
              f"Erreurs : {', '.join(erreurs) or 'aucune'}.")
        return {"fiches": len(nouvelles), "trouvailles": len(uniques), "modele": modele, "erreurs": erreurs}


if __name__ == "__main__":
    lancer(force="--force" in sys.argv, essai="--essai" in sys.argv)

