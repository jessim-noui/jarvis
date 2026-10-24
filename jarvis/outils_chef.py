r"""Mission 16 : les outils du chef. Jarvis va voir lui-même ses IA, ses agents, la page Moi, ses offres…
Chaque outil renvoie (texte, source) : la source est citée dans la réponse (« d'après config.yaml, ligne 29 »).
- Lire : toujours permis. lire_code : seulement jarvis et routeur-ia\site, jamais C:\SECRETS ni un fichier de clés.
- Agir (réversible) : Jarvis le fait seul, puis une ligne dans le Journal avec Annuler (donnees\initiatives.json).
- Jamais : envoyer, payer, supprimer pour de vrai, C:\SECRETS.
Les résultats sont encadrés comme DONNÉES non fiables (securite.encadrer) avant d'aller à une IA.
"""
import datetime, json, re, time, uuid
from pathlib import Path

import commun
from commun import JARVIS, DONNEES, lire_json, ecrire_json, nom_ia
import securite

INITIATIVES = DONNEES / "initiatives.json"
SITE = commun.RACINE / "site"
PAGES = {p.stem for p in SITE.glob("*.html")} if SITE.is_dir() else set()
LISIBLES = (JARVIS.resolve(), SITE.resolve())
INTERDIT = re.compile(r"(mdp|cles?\.txt|gmail\.env|\.env$|\.key$|\.pem$|token|secret|memoire\.db|[\\/]donnees[\\/])", re.I)


def _jour():
    return datetime.date.today().isoformat()


# ---------- Lire ----------

def mes_ia():
    """config.yaml + chaînes + sante.json : qui répond en premier pour chaque profil, et son état."""
    from suite import atelier
    ias, chaines = atelier.config_ia()
    modeles = {i["id"]: i for i in ias}
    sante = (lire_json(DONNEES / "sante.json", {}).get("composants") or {})
    lignes = []
    for prof, ch in chaines.items():
        noms = [nom_ia(modeles[e]["modele"]) if e in modeles else e for e in ch]
        etat = (sante.get("ia:" + prof) or {}).get("etat", "?")
        lignes.append(f"{prof} : {noms[0]} (puis {', '.join(noms[1:3]) or 'rien'}) · état {etat}")
    ligne = next((modeles[c[0]]["ligne"] for p, c in chaines.items() if p == "jarvis" and c and c[0] in modeles), 0)
    return "\n".join(lignes), f"config.yaml{', ligne ' + str(ligne) if ligne else ''} et sante.json"


def ia_du_chef():
    """L'IA qui répond vraiment au chat en ce moment : la dernière utilisée pour le profil jarvis (usage.json) si elle date de moins
    de 15 min (une bascule en cours), sinon le 1er étage de la chaîne."""
    dernier = next((e for e in reversed(lire_json(DONNEES / "usage.json", [])) if e.get("profil") == "jarvis" and e.get("modele")), None)
    chaine = commun.chaines_modeles().get("jarvis", [])
    recent = dernier and dernier.get("t", "") >= time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 900))
    return (dernier["modele"] if recent else (chaine[0] if chaine else "")), chaine  # un vieux dernier appel ne dit plus rien


def agents():
    import jarvis
    dernier = {}
    for e in lire_json(DONNEES / "journal.json", []):
        if e.get("etat") == "fin":
            dernier[e.get("agent")] = e.get("t", "")[:16].replace("T", " ")
    chaines = commun.chaines_modeles()
    l = [f"{jarvis.NOMS.get(n, n)} : {a['role'].split(' : ', 1)[-1] if a['role'].startswith(jarvis.NOMS.get(n, n)) else a['role']} IA : {nom_ia((chaines.get(a['profil']) or [''])[0]) if a['profil'] else '—'}"
         f"{' · dernière tâche ' + dernier[n] if n in dernier else ''}{' (bientôt)' if a['statut'] != 'actif' else ''}"
         for n, a in jarvis.AGENTS.items()]
    return "\n".join(l), "jarvis.py (registre AGENTS) et journal.json"


def moi():
    m = lire_json(DONNEES / "moi.json", {})
    import memoire_db
    l = [m.get("accroche", "")]
    l += [f"Formation : {f.get('titre')} — {f.get('lieu')} ({f.get('periode')})" for f in m.get("formation", [])]
    l += [f"Expérience : {e.get('titre')} — {e.get('lieu')} ({e.get('periode')})" for e in m.get("experiences", [])]
    l += [f"Compétences {c.get('domaine', '')} : {', '.join(c.get('items', []))}" for c in m.get("competences", []) if isinstance(c, dict)]
    l += [f"{k.capitalize()} : {', '.join(map(str, m[k]))}" for k in ("langues", "certificats", "autres") if isinstance(m.get(k), list) and m[k]]
    l += [f"Fait retenu : {t}" for _, t in memoire_db.faits(False)]
    return "\n".join(x for x in l if x), "la page Moi (moi.json) et ce que Jarvis sait de toi (memoire.db)"


def memoire(question):
    import memoire_db
    r = memoire_db.rechercher(question, k=3)
    return ("\n".join(f"({src}) {t[:400]}" for _, src, t in r) or "rien trouvé"), "la mémoire de Jarvis"


def _offres_pour_toi():
    import offres as mod
    return mod.pour_toi(mod.resume()["offres"])


def offres(ville="", mot="", n=5):
    l = _offres_pour_toi()
    v, m = securite.normaliser(ville or ""), securite.normaliser(mot or "")
    l = [o for o in l if (not v or v in securite.normaliser(f"{o.get('ville', '')} {o.get('region', '')}"))
         and (not m or m in securite.normaliser(o.get("titre", "")))]
    n = max(1, min(10, int(n or 5)))
    lignes = [f"{k}. {o['titre']} — {o.get('entreprise') or 'entreprise non précisée'} ({o.get('ville', '')})" for k, o in enumerate(l[:n], 1)]
    return (f"{len(l)} offre(s) pour toi" + (" :\n" + "\n".join(lignes) if lignes else "")), "tes offres « pour toi » (offres-stock.json, vérifiées)"


def candidatures():
    st = lire_json(DONNEES / "candidatures-statuts.json", {})
    compte = {}
    for v in (st.values() if isinstance(st, dict) else []):
        s = v.get("statut") if isinstance(v, dict) else str(v)
        compte[s] = compte.get(s, 0) + 1
    return (", ".join(f"{k} : {n}" for k, n in compte.items()) or "aucune candidature suivie"), "candidatures-statuts.json (compteurs seulement)"


def decisions():
    from suite import directeur
    d = directeur.decisions(True)
    return (f"{len(d)} décision(s) en attente" + "".join(f"\n- {(x.get('questions') or [''])[0][:120]}" for x in d[:5])), "la page Décisions"


def journal(jour=""):
    jour = jour or _jour()
    faits = [f"{e['t'][11:16]} {e.get('agent')} · {e.get('action')} : {str(e.get('resume', ''))[:80]}"
             for e in lire_json(DONNEES / "journal.json", []) if e.get("t", "").startswith(jour) and e.get("etat") == "fin"
             and e.get("action") not in ("routage",)]
    seul = [f"{i['t'][11:16]} {i['texte']}{' (annulé)' if i.get('annule') else ''}" for i in lire_json(INITIATIVES, []) if i["t"].startswith(jour)]
    return ("Fait seul : " + ("\n".join(seul) or "rien") + "\nTâches : " + ("\n".join(faits[-10:]) or "rien")), f"le Journal du {jour}"


def rapport(n):
    texte = (JARVIS / "RAPPORT.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^#+ .*(?:mission|MISSION)[ _]?{int(n)}\b.*?(?=^#+ .*(?:mission|MISSION)[ _]?\d|\Z)", texte, re.S | re.M)
    if m:
        return m.group(0).strip()[:1500], f"RAPPORT.md (mission {n})"
    prog = (JARVIS / "PROGRESSION.md").read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^## .*MISSION_?{int(n)}\b.*$", prog, re.M)
    return (m.group(0).lstrip("# ") if m else f"rien sur la mission {n}"), "PROGRESSION.md"


def idees():
    from suite import idees as mod
    l = [i for i in mod.liste()["idees"] if i.get("statut") != "non"]
    return "\n".join(f"- {i.get('titre')} ({i.get('statut', 'nouvelle')})" for i in l[:10]) or "aucune idée", "la boîte à idées"


def chercher_site(texte):
    import projet
    r = [(f, b) for f, b in projet.chercher(texte, 3) if "PROGRESSION" not in f]
    return "\n\n".join(f"[{f}] {b[:500]}" for f, b in r) or "rien trouvé", "le guide du site"


def lire_code(chemin, lignes=""):
    """Seulement jarvis et routeur-ia\\site ; jamais C:\\SECRETS, un fichier de clés ou donnees\\."""
    p = Path(str(chemin))
    p = (p if p.is_absolute() else JARVIS / p).resolve()
    if INTERDIT.search(str(p)) or not any(str(p).lower().startswith(str(b).lower()) for b in LISIBLES) or not p.is_file():
        raise securite.ActionRefusee("Je ne lis que le code de Jarvis et du site (jamais les clés ni C:\\SECRETS).")
    t = p.read_text(encoding="utf-8", errors="replace").splitlines()
    m = re.match(r"(\d+)\D+(\d+)", str(lignes or ""))
    a, b = (int(m.group(1)), int(m.group(2))) if m else (1, 60)
    a, b = max(1, a), min(len(t), b, a + 80)  # 80 lignes au plus : le quota gratuit de Groq est de 8 000 jetons par minute
    return securite.masquer_secrets("\n".join(f"{k}: {t[k - 1]}" for k in range(a, b + 1))), f"{p.name}, lignes {a}-{b}"


def web(question):
    import web as mod
    r, _ = mod.repondre(question)
    return r, "le web (sources dans la réponse)"


# ---------- Agir, réversible : fait seul, noté avec Annuler ----------

def noter(texte, annuler, bouton=None):
    """Une ligne « fait seul » (Journal) + de quoi l'annuler. Renvoie l'id."""
    i = {"id": uuid.uuid4().hex[:8], "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "texte": texte[:200], "annuler": annuler,
         "bouton": bouton, "annule": False}
    ecrire_json(INITIATIVES, (lire_json(INITIATIVES, []) + [i])[-300:])
    return i["id"]


def annuler(ident):
    l = lire_json(INITIATIVES, [])
    i = next((x for x in l if x["id"] == ident), None)
    if not i or i.get("annule"):
        raise ValueError("rien à annuler")
    a = i.get("annuler") or {}
    if a.get("type") == "lettre":
        import candidature
        d = lire_json(candidature.LETTRES, {})
        if a.get("avant"):
            d[a["id"]] = a["avant"]
        else:
            d.pop(a["id"], None)
        ecrire_json(candidature.LETTRES, d)
    elif a.get("type") == "offre":
        import offres as mod
        mod.choisir(a["id"], a["quoi"])
    elif a.get("type") == "idee":
        from suite import idees as mod
        mod.choisir(a["id"], "non")
    elif a.get("type") == "rappel":
        ecrire_json(DONNEES / "rappels.json", [r for r in lire_json(DONNEES / "rappels.json", []) if r.get("id") != a["id"]])
    i["annule"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    ecrire_json(INITIATIVES, l)
    return {"ok": True}


def tester_ia():
    from suite import sante
    r = sante.tester_maintenant()
    noter("J'ai testé tes IA : " + r["phrase"], {"type": "rien"})
    return r["phrase"], "un vrai petit test de chaque profil (Santé)"


def chercher_offres(ville="", mot="", n=3):
    texte, source = offres(ville, mot, n)
    return texte, source


def preparer_lettre(rang=1):
    """Brouillon vérifié (verif_lettre) pour la n-ième offre « pour toi ». Jamais envoyé."""
    import candidature, lecture_offres
    l = _offres_pour_toi()
    rang = max(1, int(rang or 1))
    if len(l) < rang:
        return "Je n'ai pas d'offre « pour toi » à ce rang.", "tes offres"
    o = l[rang - 1]
    avant = lire_json(candidature.LETTRES, {}).get(o["id"])
    r = candidature.ecrire_lettre(o, lecture_offres.lues().get(o["id"], {}).get("texte", ""))
    if r.get("question"):
        return "Il me manque une info : " + r["question"], "l'offre"
    noter(f"Brouillon de lettre pour « {o['titre']} » ({o.get('entreprise') or '?'})", {"type": "lettre", "id": o["id"], "avant": avant},
          {"texte": "Voir la lettre", "page": "emploi.html#lettres"})
    return (f"Brouillon prêt pour « {o['titre']} » ({o.get('entreprise') or '?'}), vérifié, non envoyé :\n{r['texte']}"), "l'offre et la page Moi"


def ranger_offre(ident, raison="rangée par Jarvis"):
    import offres as mod
    mod.choisir(ident, "enlever")
    noter(f"Offre rangée ({raison})", {"type": "offre", "id": ident, "quoi": "remettre"})
    return "Offre rangée dans la Corbeille (Remettre possible).", "tes offres"


def remettre_offre(ident):
    import offres as mod
    mod.choisir(ident, "remettre")
    noter("Offre remise dans tes offres", {"type": "offre", "id": ident, "quoi": "enlever"})
    return "Offre remise.", "tes offres"


def ajouter_idee(titre, apporte=""):
    from suite import idees as mod
    ident = "jarvis-" + uuid.uuid4().hex[:6]
    mod.ajouter(ident, str(titre)[:120], str(apporte)[:300], source="jarvis")
    noter(f"Idée ajoutée : {titre}", {"type": "idee", "id": ident})
    return f"Idée « {titre} » ajoutée à la boîte à idées.", "la boîte à idées"


def noter_rappel(texte, quand=""):
    ident = uuid.uuid4().hex[:6]
    ecrire_json(DONNEES / "rappels.json", lire_json(DONNEES / "rappels.json", []) + [{"id": ident, "texte": str(texte)[:200], "quand": str(quand)[:40],
                                                                                        "t": time.strftime("%Y-%m-%dT%H:%M")}])
    noter(f"Rappel noté : {texte}", {"type": "rappel", "id": ident})
    return f"Rappel noté : {texte}{' (' + quand + ')' if quand else ''}.", "tes rappels"


def ouvrir_page(page):
    p = str(page).split("#")[0].removesuffix(".html")
    if p not in PAGES:
        return f"La page « {page} » n'existe pas.", "le site"
    return f"BOUTON:{p}.html", "le site"


# ---------- Le catalogue donné au chef (format OpenAI) ----------

def _f(nom, desc, props=None, requis=()):
    return {"type": "function", "function": {"name": nom, "description": desc,
            "parameters": {"type": "object", "properties": props or {}, "required": list(requis)}}}


S = {"type": "string"}
CATALOGUE = {
    "mes_ia": (mes_ia, _f("mes_ia", "Les IA de Jarvis : qui répond en premier pour chaque profil, les secours, leur état.")),
    "agents": (agents, _f("agents", "Les agents de Jarvis : nom, rôle, IA, dernière tâche.")),
    "offres": (offres, _f("offres", "Les offres d'emploi « pour toi » (vérifiées), filtrables.", {"ville": S, "mot": S, "n": {"type": "integer"}})),
    "candidatures": (candidatures, _f("candidatures", "Compteurs des candidatures par statut.")),
    "decisions": (decisions, _f("decisions", "Les décisions qui attendent l’utilisateur.")),
    "journal": (journal, _f("journal", "Ce que Jarvis a fait un jour donné (AAAA-MM-JJ, aujourd'hui par défaut).", {"jour": S})),
    "rapport": (rapport, _f("rapport", "Le rapport d'une mission (numéro).", {"n": {"type": "integer"}}, ["n"])),
    "idees": (idees, _f("idees", "La boîte à idées.")),
    "chercher_site": (chercher_site, _f("chercher_site", "Chercher dans le guide du site (où cliquer, quelle page).", {"texte": S}, ["texte"])),
    "lire_code": (lire_code, _f("lire_code", "Lire un fichier de code de Jarvis ou du site (chemin relatif à jarvis, lignes « 10-40 »).",
                                {"chemin": S, "lignes": S}, ["chemin"])),
    "web": (web, _f("web", "Chercher sur Internet une info récente, avec sources.", {"question": S}, ["question"])),
    "tester_ia": (tester_ia, _f("tester_ia", "Tester maintenant toutes les IA (petit test, réversible).")),
    "chercher_offres": (chercher_offres, _f("chercher_offres", "Trouver des offres pour l’utilisateur.", {"ville": S, "mot": S, "n": {"type": "integer"}})),
    "preparer_lettre": (preparer_lettre, _f("preparer_lettre", "Préparer un BROUILLON de lettre (jamais envoyé) pour la n-ième offre « pour toi » (1 = la meilleure).",
                                            {"rang": {"type": "integer"}})),
    "ajouter_idee": (ajouter_idee, _f("ajouter_idee", "Ajouter une idée dans la boîte à idées.", {"titre": S, "apporte": S}, ["titre"])),
    "noter_rappel": (noter_rappel, _f("noter_rappel", "Noter un rappel pour l’utilisateur.", {"texte": S, "quand": S}, ["texte"])),
    "ouvrir_page": (ouvrir_page, _f("ouvrir_page", "Mettre un bouton pour ouvrir une page du site (ex. mes-ia, emploi, moi, journal).", {"page": S}, ["page"])),
}
OUTILS = [v[1] for v in CATALOGUE.values()]


def appeler(nom, args):
    """Exécute un outil ; renvoie (texte, source). Une erreur devient un texte (le chef s'en sert pour dire « je ne sais pas »)."""
    if nom not in CATALOGUE:
        return f"outil inconnu : {nom}", ""
    try:
        return CATALOGUE[nom][0](**{k: v for k, v in (args or {}).items() if isinstance(k, str)})
    except securite.ActionRefusee as e:
        return str(e), ""
    except TypeError:
        return "arguments invalides", ""
    except Exception as e:  # noqa: BLE001
        return f"l'outil a échoué ({type(e).__name__})", ""
