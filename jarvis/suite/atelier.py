r"""Mission 15, partie 2 : les données des pages Pilote (le graphe), Mes IA et Journal. Lecture seule.

- Rien n'est simulé : agents (jarvis.py), IA et chaînes de secours (config.yaml), appels (usage.json), skills
  (suite/skills_agents.json), notes de la mémoire Obsidian (jarvis/memoire, liens [[…]]), journal, délégations, décisions.
- Aucun contenu privé : seulement des titres, des noms et des chiffres ; tout texte passe par securite.masquer_secrets.
- Ollama n'est jamais démarré ici (on regarde seulement si son port répond) ; nvidia-smi seulement si l’utilisateur est là.
"""
import collections, json, re, socket, statistics, subprocess, time
from pathlib import Path

import commun
from commun import DONNEES, JOURNAL, lire_json

MEMOIRE = Path(__file__).resolve().parent.parent / "memoire"
PAYANTES = {"e-oc-deepseek-pro", "e-oc-deepseek-flash", "e-oc-minimax-m3"}  # trouvées dans config.yaml (mission 15)
RETIREES = {"e-laguna": "retirée en Mission 10 (échecs), encore dans la liste"}
FOUR = {  # préfixe du modèle → (fournisseur, ce que c'est)
    "openrouter": ("OpenRouter", "Des IA gratuites de plusieurs marques (celles marquées « :free »), avec une limite par jour."),
    "nvidia_nim": ("NVIDIA", "build.nvidia.com : gratuit, avec des crédits."),
    "gemini": ("Google", "Gemini gratuit, avec une limite par jour. C’est lui qui regarde les images."),
    "groq": ("Groq", "Très rapide, gratuit, avec des limites par minute et par jour."),
    "mistral": ("Mistral", "Gratuit (offre « Experiment »), avec des limites par minute."),
    "cloud": ("Ollama Cloud", "En ligne, mais ça passe par Ollama sur ton PC. Certaines de ces IA sont payantes."),
    "ollama": ("Ollama (ton PC)", "Le programme qui fait tourner les IA sur ta carte graphique."),
}
CHAINES_NOMS = {"jarvis": "Jarvis, le chef", "jarvis-redaction": "Rédaction (lettres)", "jarvis-code": "Code",
                "jarvis-rapide": "Rapide (tri des offres, Telegram)", "jarvis-vision": "Vision (images)",
                "jarvis-prive": "Privé (mails, rien ne sort du PC)"}
NOMS = {"e-minimax-flash": "MiniMax M3.1 Flash", "e-oc-deepseek-pro": "DeepSeek V4 Pro", "e-oc-deepseek-flash": "DeepSeek V4.1 Flash",
        "e-oc-minimax-m3": "MiniMax M3", "e-oc-gemma4": "Gemma 4 31B (Ollama Cloud)", "e-oc-nemotron-super": "Nemotron 3 Super (cloud)",
        "e-vision-nemotron": "Nemotron 3.5 VL", "e-laguna": "Laguna S 2.1", "e-nemotron-ultra": "Nemotron 3 Ultra 550B",
        "e-nemotron-super": "Nemotron 3 Super 120B", "e-local-qwen": "Qwen3 14B", "e-local-llama": "Llama 3.1 8B", "e-qwen-groq": "Qwen 3.8 27B"}  # noms lisibles
ROLES = {"veille": "Cherche les nouvelles IA, failles et outils.", "emploi": "Lit les offres, garde les 0–1 an, calcule le trajet.",
         "mails": "Lit tes mails sur ton PC, prépare des réponses (jamais envoyées).", "code": "Modifie Jarvis dans une copie à part, avec tests et Annuler.",
         "redaction": "Écrit les lettres de 6 à 8 lignes, vérifiées par le code.", "securite": "Bloque les pièges venus du web ou des mails.",
         "video": "Regarde une vidéo : résumé, idées, conseils de montage."}
VRAM = {"qwen3:14b": "≈ 9 Go", "llama3.1:8b": "≈ 5 Go"}


def _propre(t, n=140):
    from securite import masquer_secrets
    return " ".join(masquer_secrets(str(t or "")).replace("`", "").replace("**", "").split())[:n]


def _fournisseur(modele):
    p = modele.split("/")[0]
    if p.startswith("ollama"):
        p = "cloud" if re.search(r"[:-]cloud$", modele) else "ollama"
    return FOUR.get(p, (p, ""))


def config_ia():
    """Les IA de config.yaml, dans l'ordre : nom du routeur, modèle, nom de la variable de la clé, numéro de ligne ;
    et les chaînes de secours des profils jarvis-* (router_settings → fallbacks), en noms du routeur."""
    import yaml
    texte = commun.CONFIG_ROUTEUR.read_text(encoding="utf-8")
    lignes = {}
    for n, l in enumerate(texte.splitlines(), 1):
        m = re.match(r"\s*-\s*model_name:\s*([\w.-]+)", l)
        if m:
            lignes.setdefault(m.group(1), n)
    conf = yaml.safe_load(texte)
    ias = []
    for d in conf["model_list"]:
        p = d.get("litellm_params", {})
        cle = str(p.get("api_key", ""))
        ias.append({"id": d["model_name"], "modele": p.get("model", ""), "ligne": lignes.get(d["model_name"], 0),
                    "cle": cle.split("/", 1)[1] if cle.startswith("os.environ/") else ""})
    fb = {k: v for x in conf.get("router_settings", {}).get("fallbacks", []) for k, v in x.items()}
    modeles = {i["id"]: i["modele"] for i in ias}
    chaines = {}
    for prof in CHAINES_NOMS:
        if prof in modeles:  # 1er étage = l'IA e-… qui a le même modèle que le profil
            premier = next((i["id"] for i in ias if i["id"].startswith("e-") and i["modele"] == modeles[prof]), prof)
            chaines[prof] = [premier] + list(fb.get(prof, []))
    return [i for i in ias if i["id"].startswith("e-")], chaines


def _usage(jours=7):
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    return [e for e in lire_json(DONNEES / "usage.json", []) if e.get("t", "") >= limite and e.get("modele")]


def ollama_allume():
    """Regarde seulement si le port d'Ollama répond (ne le démarre jamais)."""
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.3):
            return True
    except OSError:
        return False


_gpu = {"t": 0, "v": None}


def carte_graphique():
    """nvidia-smi (lecture seule), seulement si l’utilisateur est là ; gardé 60 s."""
    if not commun.present():
        return {"vu": False, "raison": "L’utilisateur absent : pas de mesure"}
    if time.time() - _gpu["t"] < 60 and _gpu["v"]:
        return _gpu["v"]
    try:
        r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        nom, util, total = [x.strip() for x in r.stdout.strip().splitlines()[0].split(",")]
        v = {"vu": True, "nom": nom, "utilise_go": round(int(util) / 1024, 1), "total_go": round(int(total) / 1024)}
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        v = {"vu": False, "raison": "nvidia-smi n'a pas répondu"}
    _gpu.update(t=time.time(), v=v)
    return v


def mes_ia():
    """La page Mes IA : chaque IA de config.yaml, son fournisseur, ses chaînes, ses appels des 7 derniers jours."""
    from commun import nom_ia
    ias, chaines = config_ia()
    usage = _usage(7)
    jours = [time.strftime("%Y-%m-%d", time.localtime(time.time() - k * 86400)) for k in range(6, -1, -1)]
    heure = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 3600))
    par_modele = collections.defaultdict(list)
    for e in usage:
        par_modele[e["modele"]].append(e)
    out, fours = [], {}
    for i in ias:
        f, desc = _fournisseur(i["modele"])
        u = par_modele.get(i["modele"], [])
        ok = [e.get("duree") or 0 for e in u if not e.get("erreur")]
        dernier = u[-1] if u else {}
        quota = bool(dernier.get("erreur")) and dernier.get("t", "") >= heure and \
            bool(re.search(r"429|quota|rate.?limit", str(dernier.get("erreur")), re.I))
        dans = [p for p, c in chaines.items() if i["id"] in c]
        etat = ("payant" if i["id"] in PAYANTES else "retire" if i["id"] in RETIREES else "lent" if quota
                else "ok" if any(c[0] == i["id"] for c in chaines.values()) and not (u and dernier.get("erreur")) else "repos")
        out.append({"id": i["id"], "nom": NOMS.get(i["id"], "").replace(" (Ollama Cloud)", "") or re.sub(r" \((Google|Mistral|NVIDIA|Groq)\)$", "", nom_ia(i["modele"])), "modele": i["modele"], "four": f, "ou": "pc" if f.startswith("Ollama (") else "net",
                    "etat": etat, "chaines": dans, "ligne": i["ligne"],
                    "vit": f"{statistics.median(ok):.1f} s".replace(".", ",") if ok else "",
                    "note": RETIREES.get(i["id"]) or ("payante, encore dans la liste" if i["id"] in PAYANTES else
                                                      VRAM.get(i["modele"].split("/")[-1], "") + (" de mémoire vidéo" if i["modele"].split("/")[-1] in VRAM else "")
                                                      if f.startswith("Ollama (") else "quota atteint : le routeur passe à la suivante" if quota else ""),
                    "sem": [sum(1 for e in u if e["t"].startswith(j)) for j in jours]})
        fours.setdefault(f, {"nom": f, "desc": desc, "cle": i["cle"] or ("ton compte ollama.com (ollama signin)" if f == "Ollama Cloud" else "")})
    whisper = __import__("importlib.util").util.find_spec("faster_whisper") is not None
    out.append({"id": "whisper", "nom": "Whisper", "modele": "faster-whisper", "four": "faster-whisper", "ou": "pc",
                "etat": "ok" if whisper else "repos", "chaines": [], "ligne": 0, "vit": "", "sem": [0] * 7,
                "note": "le son en texte (vidéos, entretien)" + ("" if whisper else " · pas installé")})
    from suite.routes import ia_defaut
    return {"ias": out, "chaines": [{"id": p, "nom": CHAINES_NOMS[p], "maillons": c} for p, c in chaines.items()],
            "fournisseurs": list(fours.values()), "ollama": ollama_allume(), "gpu": carte_graphique(),
            "defaut": ia_defaut(), "jours": jours,
            "fichier": commun.CONFIG_ROUTEUR.relative_to(commun.IA).as_posix()}


# ---------- Pilote : le graphe ----------

def _notes():
    """{nom de la note: [notes liées]} depuis jarvis/memoire (liens [[…]])."""
    notes = {}
    for f in sorted(MEMOIRE.glob("*.md")):
        try:
            liens = re.findall(r"\[\[([^\]|#]+)", f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        notes[f.stem] = sorted({l.strip() for l in liens if l.strip() and l.strip() != f.stem})
    return notes


def graphe():
    """Nœuds (chef, agents, IA, skills, notes) et liens réels. Les positions sont calculées par la page (forces, une fois)."""
    import jarvis
    from suite import arbre, skills_agents
    ias, chaines = config_ia()
    par_id = {i["id"]: i for i in ias}
    par_modele = {}
    for i in ias:
        par_modele.setdefault(i["modele"], i["id"])
    from commun import nom_ia
    noeuds, liens = {}, {}

    def noeud(ident, type_, nom, info, **x):
        noeuds.setdefault(ident, {"id": ident, "type": type_, "nom": nom, "info": _propre(info, 200), **x})

    def lien(a, b, actif=False, pourquoi=""):
        if a == b or a not in noeuds or b not in noeuds:
            return
        k = tuple(sorted((a, b)))
        l = liens.setdefault(k, {"a": k[0], "b": k[1], "actif": False, "pourquoi": pourquoi})
        l["actif"] = l["actif"] or actif

    def ia(ident):
        i = par_id.get(ident)
        if not i:
            return None
        f = _fournisseur(i["modele"])[0]
        role = next((("1re IA de " if c[0] == ident else "secours de ") + CHAINES_NOMS[p] for p, c in chaines.items() if ident in c), "")
        noeud("ia:" + ident, "local" if f.startswith("Ollama (") else "cloud",
              NOMS.get(ident) or re.sub(r" \((Google|Mistral|NVIDIA)\)$", "", nom_ia(i["modele"])),
              f"{f} · {role or 'dans aucune chaîne'}", lien_page="mes-ia.html#ia=" + ident)
        return "ia:" + ident

    ab = {a["id"]: a for a in arbre.arbre()["agents"]}
    noeud("jarvis", "jarvis", "Jarvis", "Le chef : reçoit ta demande et la répartit. 1re IA : " + (NOMS.get(chaines.get("jarvis", [""])[0]) or ""),
          derniere="")
    for ident in [*jarvis.EQUIPE, "video"]:
        a = ab.get(ident, {})
        noeud(ident, "agent", jarvis.NOMS.get(ident, ident), ROLES.get(ident, ""),
              ia=(lambda m: NOMS.get(m) or nom_ia(par_id.get(m, {}).get("modele", "")))(chaines[a["profil"]][0]) if a.get("profil") in chaines else "",
              derniere=_propre(a["taches"][0][1], 90) if a.get("taches") else "", travail=a.get("etat") == "travail")
        lien("jarvis", ident, actif=a.get("etat") == "travail", pourquoi="membre de l'équipe")
    # IA : 1er étage de chaque chaîne d'agent + celles vraiment appelées (usage.json, 30 jours)
    for p, c in chaines.items():
        for k, m in enumerate(c[:3]):
            ia(m)
            if k:
                lien("ia:" + c[k - 1], "ia:" + m, pourquoi="secours (chaîne du routeur)")
        for ident, a in [("jarvis", {"profil": "jarvis"}), *ab.items()]:
            if a.get("profil") == p and c:
                lien(ident, "ia:" + c[0], pourquoi="chaîne du routeur")
    for ident, a in ab.items():
        for n_ia, appels, _ in a.get("ias", []):
            m = next((i["id"] for i in ias if nom_ia(i["modele"]) == n_ia.replace(" (ton PC)", "")), None)
            if m:
                ia(m)
                lien(ident, "ia:" + m, pourquoi=f"{appels} appels (30 j)")
        if a.get("etat") == "travail":
            cours = next((t for t in a.get("taches", []) if t[2] == "en cours"), None)
            m = next((i["id"] for i in ias if cours and nom_ia(i["modele"]) == cours[3].replace(" (ton PC)", "")), None)
            if m and ia(m):
                lien(ident, "ia:" + m, actif=True, pourquoi="travail en cours")
    for d in lire_json(DONNEES / "delegations.json", [])[-20:]:
        m = par_modele.get(d.get("modele", ""))
        if m and ia(m):
            lien("code", "ia:" + m, pourquoi="délégations de Claude")
    if (MEMOIRE.parent / "outils").exists():
        noeud("ia:whisper", "local", "Whisper", "Sur ton PC · le son en texte (vidéos, entretien)", lien_page="mes-ia.html#ia=whisper")
        lien("video", "ia:whisper", pourquoi="transcription")
    # Skills (suite/skills_agents.json)
    for agent, skills in skills_agents.table().items():
        for s in skills:
            noeud("s:" + s, "skill", s, "Skill : consigne suivie par " + ("tous les agents" if agent == "tous" else jarvis.NOMS.get(agent, agent)),
                  lien_page="skills.html")
            if agent == "tous":
                lien("jarvis", "s:" + s, pourquoi="skill de tous")
            elif agent in noeuds:
                lien(agent, "s:" + s, pourquoi="skill de l'agent")
    # Notes de la mémoire : liens entre notes ; « agent-x » est la note de l'agent x, « Jarvis » celle du chef
    notes = _notes()
    for n in notes:
        noeud("n:" + n, "note", n, f"Note de la mémoire · memoire/{n}.md", lien_page="obsidian://open?vault=memoire&file=" + n)
    for n, cibles in notes.items():
        for c in cibles:
            if c in notes:
                lien("n:" + n, "n:" + c, pourquoi="lien entre notes")
        agent = "jarvis" if n.lower() in ("jarvis", "agent-jarvis") else n[6:] if n.startswith("agent-") else ""
        if agent in noeuds:
            lien("n:" + n, agent, pourquoi="sa note")
    deg = collections.Counter()
    for l in liens.values():
        deg[l["a"]] += 1
        deg[l["b"]] += 1
    for n in noeuds.values():
        n["liens"] = deg[n["id"]]
    return {"noeuds": list(noeuds.values()), "liens": list(liens.values()), "moment": moment(ab), "chiffres": chiffres(chaines)}


def moment(ab):
    """« En ce moment » : un vrai travail en cours (journal), sinon rien."""
    for a in ab.values():
        if a.get("etat") == "travail":
            t = next((x for x in a.get("taches", []) if x[2] == "en cours"), None)
            return {"titre": f"{a['nom']} travaille", "texte": _propre(f"Demandé à {t[0]} : « {t[1]} »" if t else a.get("tache", ""), 160),
                    "ia": t[3] if t else "", "de": _propre(a.get("de"), 80)}
    return None


def chiffres(chaines):
    """Les 4 chiffres du jour : travaux faits, IA qui répondent, réponse du chef (médiane), incident ouvert."""
    jour = time.strftime("%Y-%m-%d")
    journal = [e for e in lire_json(JOURNAL, []) if str(e.get("t", "")).startswith(jour)]
    usage = [e for e in lire_json(DONNEES / "usage.json", []) if str(e.get("t", "")).startswith(jour)]
    premiers = {c[0] for c in chaines.values()}
    ias, _ = config_ia()
    modeles = {i["id"]: i["modele"] for i in ias}
    vus = {e["modele"]: not e.get("erreur") for e in usage if e.get("modele")}
    rep = [m for m in premiers if vus.get(modeles.get(m)) is True]
    chef = [e.get("duree") or 0 for e in usage if e.get("profil") == "jarvis" and not e.get("erreur")]
    try:
        import alertes
        incident = 1 if alertes.incident_actif() else 0
    except Exception:
        incident = 0
    return [[str(sum(1 for e in journal if e.get("etat") in ("fin", "info") and e.get("statut") == "ok")), "travaux faits"],
            [f"{len(rep)}/{len(premiers)}", "IA qui répondent (1res, aujourd’hui)"],
            [f"{statistics.median(chef):.1f} s".replace(".", ",") if chef else "—", "réponse du chef"],
            [str(incident), "incident ouvert"]]


# ---------- Journal : tout ce qui s'est passé, jour par jour ----------

TYPE_ACTION = {"decision": "decision", "pas pour moi": "demande", "relance ollama": "probleme", "mission": "mission",
               "panneau de contrôle": "demande", "tout arrêter": "demande", "exporter": "demande", "modifier Jarvis": "demande"}


def journal(jours=14):
    """Les événements, du plus récent au plus ancien, avec leur type, pourquoi, IA, durée, trace (sans contenu) et l'action possible."""
    from suite import directeur
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - jours * 86400))
    sept = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7 * 86400))
    ev = []

    def ajoute(t, type_, titre, pourquoi="", ia="", duree=None, trace="", detail="", action=None, annule=False, ident=""):
        if t and t >= limite:
            ev.append({"id": ident or f"{type_}-{len(ev)}", "t": t[:19], "type": type_, "titre": _propre(titre, 120),
                       "pourquoi": _propre(pourquoi, 200), "ia": _propre(ia, 60), "duree": duree, "trace": _propre(trace, 12),
                       "detail": _propre(detail, 300), "action": action, "annule": annule})
    for e in lire_json(JOURNAL, []):
        if e.get("etat") == "debut" or e.get("action") in ("decision", "routage"):  # décisions et questions : vues par leur propre source
            continue
        type_ = TYPE_ACTION.get(e.get("action"), "probleme" if e.get("statut") in ("réparé", "regle") else "seul")
        m = re.search(r"trace ([0-9a-f]{8})", str(e.get("resume", "")))
        import jarvis
        ajoute(e.get("t"), type_, e.get("resume") or f"{e.get('action', '')} : {e.get('statut', '')}",
               pourquoi=f"{jarvis.NOMS.get(e.get('agent'), e.get('agent') or 'Jarvis')} · {e.get('action', '')}", ia=commun.nom_ia(e.get("modele")) if e.get("modele") else "",
               trace=m.group(1) if m else "")
    import traces
    for t in traces.lire():
        ia = next((x.get("ia") or x.get("modele") for x in reversed(t.get("etapes", [])) if x.get("ia") or x.get("modele")), "")
        ajoute(t.get("debut"), "demande", "Ta question à Jarvis" + (" (erreur)" if t.get("etat") == "erreur" else ""),
               pourquoi=f"Posée sur le site ({t.get('route', '')})", ia=commun.nom_ia(ia) if ia else "", duree=t.get("duree"), trace=t.get("id", ""),
               detail=" → ".join(x.get("nom", "") for x in t.get("etapes", []))[:300])
    for d in directeur.decisions(False):
        if d["etat"] in ("repondue", "reportee", "annulee"):
            choix = next((o["libelle"] for o in d["options"] if o["id"] == d.get("choix")), d.get("choix") or "plus tard")
            ajoute(d.get("maj"), "decision", f"Tu as choisi : « {choix} »", pourquoi=(d["questions"] or [""])[0], detail=d.get("pourquoi", ""),
                   action={"quoi": "annuler_decision", "id": d["id"]} if d["etat"] != "annulee" and d.get("maj", "") >= sept else None,
                   ident="dec-" + d["id"])
        for a in d.get("avant", []):  # un choix annulé reste visible, barré
            choix = next((o["libelle"] for o in d["options"] if o["id"] == a.get("choix")), a.get("choix") or "plus tard")
            ajoute(a.get("maj"), "decision", f"Tu as choisi : « {choix} »", pourquoi=(d["questions"] or [""])[0], annule=True,
                   ident=f"dec-{d['id']}-{a.get('maj', '')}")
    for r in directeur.mini_rapports(100):
        ajoute(r.get("t"), "seul", r.get("fait") or r.get("probleme"), pourquoi=r.get("pourquoi") or r.get("probleme"),
               detail=f"Tests : {r['tests']}" if r.get("tests") else "", ident="rap-" + r["id"],
               action={"quoi": "annuler_changement", "id": r["commit"]} if r.get("commit") and r.get("t", "") >= sept else None)
    for i in lire_json(DONNEES / "initiatives.json", []):  # mission 16 : ce que Jarvis a fait seul (réversible), avec Annuler
        ajoute(i.get("t"), "seul", i.get("texte", ""), pourquoi="Jarvis l’a fait seul (réversible)", ident="ini-" + i["id"], annule=bool(i.get("annule")),
               action={"quoi": "annuler_initiative", "id": i["id"]} if not i.get("annule") and (i.get("annuler") or {}).get("type") not in (None, "rien") else None)
    for d in lire_json(DONNEES / "delegations.json", []):
        ajoute(d.get("t"), "mission", "Brouillon délégué à une IA gratuite : " + Path(str(d.get("sortie", ""))).name,
               pourquoi="Claude fait écrire le code simple par une IA gratuite, puis le relit", ia=commun.nom_ia(d.get("modele")))
    for m in directeur.tableau()["missions"]:
        if m.get("etat") in ("done", "failed"):
            ajoute(m.get("maj"), "mission", f"Mission du Directeur {'terminée' if m['etat'] == 'done' else 'ratée'} : {m.get('titre', '')}",
                   pourquoi=m.get("blocage") or "")
    for i in __import__("alertes").incidents():
        for h in i.get("historique", []):
            if h.get("etat") in ("réglé", "réparé", "regle"):
                ajoute(h.get("t"), "probleme", f"Réglé : {i.get('type', '')} ({i.get('composant', '')})", pourquoi=h.get("texte", ""))
    import offres
    for o in offres.corbeille():
        if o.get("quand"):
            ajoute(o["quand"] + (":00" if len(o["quand"]) == 16 else ""), "seul" if o["pourquoi"] != offres.ENLEVEE else "demande",
                   f"Offre rangée dans la Corbeille : {o['titre']}", pourquoi=o["pourquoi"], detail=f"{o['entreprise']} · {o['zone']}",
                   action={"quoi": "remettre", "id": o["id"]}, ident="off-" + o["id"])
    for i, x in offres.stock().items():  # remises : la ligne reste, barrée, avec « Remise »
        if x.get("remise"):
            ajoute(x["remise"] + ":00", "demande", f"Offre rangée dans la Corbeille : {x['fiche'].get('titre', '')}", pourquoi="Remise par toi",
                   annule=True, ident="off-" + i, action={"quoi": "enlever", "id": i} if x["remise"] >= sept[:16] else None)
    ev.sort(key=lambda e: e["t"], reverse=True)
    return {"evenements": ev}


# ---------- Mes IA → Décisions : retirer les IA payantes ou abandonnées (seulement après le oui de l’utilisateur) ----------

A_RETIRER = ["e-oc-deepseek-pro", "e-oc-deepseek-flash", "e-oc-minimax-m3", "e-laguna"]  # jamais e-minimax-flash (sert dans les chaînes)
COPIE_CONFIG = DONNEES / "sauvegardes" / "config-avant-retrait-ia.yaml"


def proposer_retrait():
    from suite import directeur
    return directeur.creer_decision(
        "mes-ia:retirer", "Je retire 4 IA payantes ou abandonnées de la liste du routeur ?",
        "DeepSeek V4 Pro, DeepSeek V4.1 Flash, MiniMax M3 (payantes) et Laguna S 2.1 (retirée en Mission 10) sont encore dans "
        "config.yaml. Je ne les utilise pas, mais elles encombrent la liste.",
        [{"id": "oui", "libelle": "Oui, retire-les", "avantages": "Je garde une copie de config.yaml avant. Bouton Annuler pendant 7 jours."},
         {"id": "non", "libelle": "Non, garde-les", "avantages": "Je ne te le redemande pas avant 30 jours."}],
        recommande="oui", si_reporte="rien ne change : elles restent là, inutilisées.", source="mes-ia",
        extra={"categorie": "Mes IA", "temps": "10 s", "conseil": "Moins d’IA dans la liste = moins de risque d’en choisir une payante par erreur.",
               "concerne": ["DeepSeek V4 Pro", "DeepSeek V4.1 Flash", "MiniMax M3", "Laguna S 2.1", "config.yaml"]})


def retirer_ia():
    """Après le oui : copie de config.yaml, puis on enlève les blocs model_name + litellm_params des 4 IA (rien d'autre)."""
    texte = commun.CONFIG_ROUTEUR.read_text(encoding="utf-8")
    COPIE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    COPIE_CONFIG.write_text(texte, encoding="utf-8")
    lignes, out, saute = texte.splitlines(keepends=True), [], False
    for l in lignes:
        m = re.match(r"\s*-\s*model_name:\s*([\w.-]+)", l)
        if m:
            saute = m.group(1) in A_RETIRER
        elif not l.lstrip().startswith("litellm_params"):
            saute = False
        if not saute:
            out.append(l)
    nouveau = "".join(out)
    if any(re.search(r"\b" + re.escape(x) + r"\b", nouveau) for x in A_RETIRER):  # encore cité (ex. une chaîne) : on ne touche à rien
        raise ValueError("une IA à retirer est encore utilisée dans config.yaml")
    commun.CONFIG_ROUTEUR.write_text(nouveau, encoding="utf-8")
    commun.journaliser(agent="jarvis", action="mes ia", etat="info", statut="ok", resume="4 IA retirées de config.yaml (copie gardée)")


def remettre_ia():
    """Annuler (7 jours) : config.yaml revient tel qu'avant le retrait."""
    if COPIE_CONFIG.exists():
        commun.CONFIG_ROUTEUR.write_text(COPIE_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
        commun.journaliser(agent="jarvis", action="mes ia", etat="info", statut="ok", resume="config.yaml remis comme avant (Annuler)")


def prochaine_question():
    """La prochaine question déjà prévue (Mission 14 : « réparations en automatique ? » 7 jours après le début du mode proposer)."""
    from suite import directeur
    debut = commun.reglage("reparations", "debut", "")
    if not debut or any(d["sujet"] == "reparations-auto" for d in directeur.decisions(False)):
        return None
    try:
        quand = time.strftime("%Y-%m-%d", time.localtime(time.mktime(time.strptime(debut[:10], "%Y-%m-%d")) + 7 * 86400))
    except ValueError:
        return None
    return {"quand": quand, "question": "passer les réparations sûres en automatique ?"}


def fait_seul_aujourdhui():
    """Le nombre d'actions que Jarvis a faites seul aujourd'hui (rangées dans La bibliothèque › Journal)."""
    jour = time.strftime("%Y-%m-%d")
    n = sum(1 for e in lire_json(JOURNAL, []) if str(e.get("t", "")).startswith(jour) and e.get("etat") != "debut"
            and e.get("action") not in ("decision", "routage") and TYPE_ACTION.get(e.get("action"), "seul") == "seul")
    from suite import directeur
    return n + sum(1 for r in directeur.mini_rapports(50) if str(r.get("t", "")).startswith(jour))
