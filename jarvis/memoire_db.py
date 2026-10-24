r"""Mémoire de Jarvis, économe en tokens — un seul fichier SQLite (donnees\memoire.db).

Trois niveaux :
  1. faits      : courts et stables (profil, décisions, préférences), toujours fournis ;
  2. resumes    : un résumé glissant par conversation, mis à jour après chaque échange.
                  On ne relit JAMAIS l'historique complet ;
  3. souvenirs  : passages (échanges passés + notes Obsidian) retrouvés par le sens,
                  grâce à des embeddings LOCAUX (Ollama, nomic-embed-text). Seuls les 3 à 5 plus proches sont fournis.
Plafond : environ 4 000 tokens de mémoire par requête.
Confidentialité : tout ce qui est marqué « prive » (mails, données perso) n'est fourni qu'aux appels locaux (jarvis-prive).
"""
import sqlite3, hashlib, re, time, threading, math
from contextlib import contextmanager
from array import array
from commun import DONNEES, MEMOIRE, IA, http_json, demander

DB = DONNEES / "memoire.db"
OLLAMA = "http://127.0.0.1:11434"
MODELE_EMB = "nomic-embed-text"
BUDGET_TOKENS = 4000
_verrou = threading.Lock()


def tokens(texte):
    """Estimation simple (≈ 4 caractères par token en français), suffisante pour un plafond."""
    return len(texte or "") // 4 + 1


@contextmanager
def connexion():
    """Ouvre, valide puis FERME la connexion (sans fermeture, Windows garde le fichier verrouillé)."""
    c = sqlite3.connect(DB, timeout=10)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS faits (cle TEXT PRIMARY KEY, texte TEXT, prive INT DEFAULT 0, maj TEXT);
        CREATE TABLE IF NOT EXISTS resumes (conversation TEXT PRIMARY KEY, resume TEXT, prive INT DEFAULT 0, maj TEXT);
        CREATE TABLE IF NOT EXISTS souvenirs (id INTEGER PRIMARY KEY, source TEXT, texte TEXT, prive INT DEFAULT 0,
                                              empreinte TEXT UNIQUE, vecteur BLOB, t TEXT);
    """)
    try:
        yield c
        c.commit()
    finally:
        c.close()


def ollama_deja_allume(modele_charge=False):
    """Mission 16 : la mémoire n'allume JAMAIS Ollama ; elle s'en sert seulement s'il tourne déjà (réponse en 0,5 s au plus).
    modele_charge=True (pendant une question) : il faut en plus que nomic-embed-text soit déjà en mémoire (sinon 3 s de chargement)."""
    from commun import ollama_autorise
    if not ollama_autorise():
        return False
    try:
        r = http_json(OLLAMA + ("/api/ps" if modele_charge else "/api/version"), timeout=0.5)
        return not modele_charge or any(m.get("name", "").startswith(MODELE_EMB) for m in r.get("models", []))
    except Exception:
        return False


def vecteur(texte, tache="search_document", delai=3):
    """Embedding local via Ollama (rien ne sort du PC), 3 s au plus. nomic-embed-text attend un préfixe de tâche.
    Pour une question (search_query), seulement si le modèle est déjà chargé : la mémoire répond en moins d'1 s."""
    from commun import reglage
    if tache == "search_query" and reglage("memoire", "mots_cles_jusqua", 0) > time.time():  # réparation « mémoire lente » (1 h)
        raise OSError("mémoire en mots-clés (réparation)")
    if not ollama_deja_allume(tache == "search_query"):  # mission 16 : Ollama éteint (ou l'utilisateur absent) → les mots-clés, tout de suite
        raise OSError("IA locale éteinte")
    try:
        r = http_json(OLLAMA + "/api/embed", {"model": MODELE_EMB, "input": [f"{tache}: {texte}"], "keep_alive": "2m"}, timeout=delai)
    except Exception as e:  # modèle pas encore chargé, Ollama occupé : on ne fait pas attendre l'utilisateur
        raise OSError(f"embedding trop lent ({type(e).__name__})")
    v = r["embeddings"][0]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return array("f", (x / n for x in v))  # normalisé : le cosinus devient un simple produit scalaire


# ---------- Niveau 1 : faits ----------

def fait(cle, texte, prive=False):
    with _verrou, connexion() as c:
        c.execute("INSERT OR REPLACE INTO faits VALUES (?,?,?,?)", (cle, texte.strip(), int(prive), time.strftime("%Y-%m-%d")))


def faits(prive=False):
    with connexion() as c:
        q = "SELECT cle, texte FROM faits" + ("" if prive else " WHERE prive=0") + " ORDER BY cle"
        return c.execute(q).fetchall()


# ---------- Niveau 3 : souvenirs ----------

def se_souvenir(texte, source, prive=False):
    texte = (texte or "").strip()
    if len(texte) < 20:
        return False
    empreinte = hashlib.sha1(texte.encode()).hexdigest()
    with connexion() as c:
        if c.execute("SELECT 1 FROM souvenirs WHERE empreinte=?", (empreinte,)).fetchone():
            return False
    try:
        v = vecteur(texte, delai=30).tobytes()
    except OSError:  # mission 16 : Ollama éteint → gardé sans vecteur (mots-clés), le vecteur viendra plus tard (completer_vecteurs)
        v = None
    with _verrou, connexion() as c:
        c.execute("INSERT OR IGNORE INTO souvenirs (source, texte, prive, empreinte, vecteur, t) VALUES (?,?,?,?,?,?)",
                  (source, texte, int(prive), empreinte, v, time.strftime("%Y-%m-%dT%H:%M:%S")))
    return True


def completer_vecteurs(maxi=50):
    """Mission 16 : calcule les vecteurs manquants, seulement si Ollama est DÉJÀ allumé pour autre chose (jamais en jeu ni site
    fermé : ollama_autorise). Appelé en fond après une réponse."""
    with connexion() as c:
        manquants = c.execute("SELECT id, texte FROM souvenirs WHERE vecteur IS NULL LIMIT ?", (maxi,)).fetchall()
    n = 0
    for ident, texte in manquants:
        try:
            v = vecteur(texte, delai=30)
        except OSError:
            break
        with _verrou, connexion() as c:
            c.execute("UPDATE souvenirs SET vecteur=? WHERE id=?", (v.tobytes(), ident))
        n += 1
    return n


def rechercher(question, k=3, prive=False, seuil=0.6):
    """Les k passages les plus proches par le sens (cosinus), au-dessus d'un seuil de pertinence.
    Mission 13 : IA locale en pause → recherche par mots-clés (part des mots de la question présents dans le passage)."""
    with connexion() as c:
        lignes = c.execute("SELECT source, texte, vecteur FROM souvenirs" + ("" if prive else " WHERE prive=0")).fetchall()
    try:
        q = vecteur(question, "search_query")
    except OSError:
        mots = set(re.findall(r"\w{4,}", question.lower()))
        scores = sorted(((len(mots & set(re.findall(r"\w{4,}", t.lower()))) / len(mots), src, t) for src, t, _ in lignes), reverse=True) if mots else []
        return [(round(s, 3), src, t) for s, src, t in scores[:k] if s >= 0.5]
    scores = []
    for source, texte, blob in lignes:
        if not blob:  # pas encore de vecteur (mission 16)
            continue
        v = array("f"); v.frombytes(blob)
        scores.append((sum(a * b for a, b in zip(q, v)), source, texte))
    scores.sort(reverse=True)
    return [(round(s, 3), src, t) for s, src, t in scores[:k] if s >= seuil]


def indexer_notes():
    """Découpe les notes Obsidian en paragraphes et indexe ce qui a changé. journal-de-bord = privé."""
    nb, actuels = 0, set()
    for f in sorted(MEMOIRE.glob("*.md")):
        prive = f.stem == "journal-de-bord"
        blocs = [b.strip() for b in re.split(r"\n(?=#)|\n\s*\n", f.read_text(encoding="utf-8", errors="ignore")) if b.strip()]
        for b in blocs:
            texte = f"[note {f.stem}] {b[:1200]}"
            actuels.add(hashlib.sha1(texte.encode()).hexdigest())
            nb += se_souvenir(texte, "note:" + f.stem, prive)
    with _verrou, connexion() as c:  # retire les passages de notes qui ont été modifiés ou supprimés
        for (emp,) in c.execute("SELECT empreinte FROM souvenirs WHERE source LIKE 'note:%'").fetchall():
            if emp not in actuels:
                c.execute("DELETE FROM souvenirs WHERE empreinte=?", (emp,))
    return nb


# ---------- Niveau 2 : résumé glissant ----------

def resume(conversation):
    with connexion() as c:
        r = c.execute("SELECT resume FROM resumes WHERE conversation=?", (conversation,)).fetchone()
    return r[0] if r else ""


def maj_resume(conversation, question, reponse, prive=False, local=False):
    """Résume localement : les échanges peuvent contenir des informations personnelles et ne sortent pas du PC."""
    ancien = resume(conversation)
    consigne = ("Mets à jour ce résumé de conversation entre l'utilisateur et Jarvis. Garde seulement ce qui servira plus tard "
                "(sujets en cours, décisions, préférences, questions ouvertes). 120 mots maximum, en français, sans titre.\n\n"
                f"Résumé actuel : {ancien or '(vide)'}\n\nDernier échange :\nl'utilisateur : {question[:800]}\nJarvis : {reponse[:1200]}")
    msg, modele = demander("jarvis-prive", consigne, max_tokens=300, temperature=0.2)
    if "ollama" not in str(modele).lower():
        raise RuntimeError("Le résumé de mémoire doit rester local.")
    nouveau = re.sub(r"<think>.*?</think>", "", msg.get("content") or "", flags=re.S).strip()[:1500]
    with _verrou, connexion() as c:
        c.execute("INSERT OR REPLACE INTO resumes VALUES (?,?,?,?)",
                  (conversation, nouveau, int(prive), time.strftime("%Y-%m-%dT%H:%M:%S")))
    return nouveau


# ---------- Le contexte envoyé avec une question ----------

def contexte(question, conversation="page", prive=False, budget=BUDGET_TOKENS, k=3):
    """Pour les modèles en ligne, ne transmet que des préférences sûres. Le contexte complet est réservé aux appels locaux."""
    morceaux = []
    f = faits(prive)
    if not prive:
        f = []  # aucun fait ou profil n'est transmis aux modèles en ligne par le contexte général
    if f:
        morceaux.append("Faits stables :\n" + "\n".join(f"- {t}" for _, t in f))
    r = resume(conversation) if prive else ""
    if r:
        morceaux.append("Résumé de la conversation en cours :\n" + r)
    try:
        trouves = rechercher(question, k, prive) if prive else []
    except Exception:  # Ollama éteint : on continue sans les souvenirs
        trouves = []
    if trouves:
        morceaux.append("Souvenirs pertinents :\n" + "\n".join(f"- ({src}) {t[:450]}" for _, src, t in trouves))
    texte, total = "", 0
    for m in morceaux:  # ordre de priorité : faits, résumé, souvenirs
        if total + tokens(m) > budget:
            m = m[: max(0, (budget - total) * 4)]
        texte += m + "\n\n"
        total += tokens(m)
        if total >= budget:
            break
    texte = texte.strip()[: (budget - 1) * 4]  # plafond strict
    return texte, {"tokens": tokens(texte), "souvenirs": len(trouves), "faits": len(f)}


def apprendre(conversation, question, reponse, agent, prive=False):
    """Après chaque échange : résumé glissant + souvenir. Appelé en arrière-plan pour ne pas ralentir la réponse."""
    def tache():
        try:
            maj_resume(conversation, question, reponse, prive)
            se_souvenir(f"Q ({agent}) : {question[:500]}\nR : {reponse[:900]}", "echange:" + agent, prive)
            completer_vecteurs()
        except Exception:
            pass
    threading.Thread(target=tache, daemon=True).start()


def initialiser():
    """Faits de départ (idempotent) et indexation des notes Obsidian."""
    base = [
        ("machine", "Jarvis utilise un routeur IA local et peut utiliser Ollama."),
        ("style", "Réponses courtes, directes, en français, avec le tutoiement."),
        ("lettres", "Lettres et mails : courts, directs, humains, jamais de style « IA »."),
        ("regles", "Rien ne s'installe ni ne s'envoie sans un clic de l'utilisateur. Les mails restent en local."),
        ("projets", "Projets : site perso (Three.js), routeur IA, Jarvis (agents), homelab (pfSense, VLAN, Linux), montage vidéo."),
    ]
    from commun import lire_json
    oublies = lire_json(DONNEES / "memoire_moi.json", {}).get("oublies", {})  # mission 15 : un fait oublié par l'utilisateur ne revient pas
    for cle, t in base:
        if cle not in oublies:
            fait(cle, t)
    profil = IA / "routeur-ia" / "outils" / "analyse-offres" / "profil.txt"
    with _verrou, connexion() as c:
        c.execute("DELETE FROM faits WHERE cle='profil_detaille'")
    if profil.exists():
        for bloc in re.split(r"\n\s*\n", profil.read_text(encoding="utf-8", errors="ignore")):
            se_souvenir("[profil local] " + bloc.strip()[:800], "profil", prive=True)
    return indexer_notes()


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    print("notes indexées :", initialiser())
    q = " ".join(sys.argv[1:]) or "Quel modèle utilise la rédaction ?"
    texte, stats = contexte(q)
    print(stats)
    for s, src, t in rechercher(q):
        print(s, src, t[:90].replace("\n", " "))
