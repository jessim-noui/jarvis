r"""« Chercher dans le projet » (mission 6) : Jarvis répond aux questions sur son propre site et sur ce qui a été fait,
en citant le fichier, au lieu d'inventer (« l'export, c'est sur Google Drive »).

Lecture seule, liste fermée de fichiers : le guide du site, RAPPORT.md, PROGRESSION.md, les missions et la feuille de route.
Jamais le code, jamais C:\SECRETS, jamais donnees\ (mails, offres, mémoire perso). Les extraits passent par securite.py
(clés masquées, texte encadré comme donnée). Mission 16 : lus en ligne, sauf PROGRESSION (noms tirés des mails) → IA locale.
"""
import re
from commun import JARVIS, demander
import securite

GUIDE = JARVIS / "memoire" / "guide-du-site.md"


def fichiers():
    l = [GUIDE, JARVIS / "RAPPORT.md", JARVIS / "PROGRESSION.md", JARVIS / "missions" / "reprise" / "FEUILLE_DE_ROUTE.md"]
    l += sorted((JARVIS / "missions").glob("*.md")) + [JARVIS / "missions" / "suite" / "INTEGRATION.md"]
    return [f for f in l if f.is_file()]


def mots(texte):
    return set(re.findall(r"[a-z0-9]{4,}", securite.normaliser(texte))) - {"jarvis", "quoi", "comment", "dans", "pour", "avec"}


def chercher(question, n=5):
    """Les n passages (paragraphes) qui partagent le plus de mots avec la question : [(fichier, extrait)]."""
    q = mots(question)
    if not q:
        return []
    trouves = []
    for f in fichiers():
        for bloc in re.split(r"\n\s*\n|\n(?=#)", f.read_text(encoding="utf-8", errors="replace")):
            score = len(q & mots(bloc)) * (2 if f == GUIDE else 1)  # le guide d'abord : il est fait pour ça
            if score >= max(1, min(2, len(q))):
                trouves.append((score, f.relative_to(JARVIS.parent).as_posix(), bloc.strip()[:900]))
    trouves.sort(key=lambda t: -t[0])
    return [(f, b) for _, f, b in trouves[:n]]


LENT = "L'IA de ton PC est lente (plus de 60 s). Je réessaie en ligne ?"


def repondre(question, en_ligne=False):
    """Renvoie (réponse, modèle). Rien trouvé → « je ne sais pas », sans appeler d'IA.
    Mission 16 : le local SEULEMENT s'il y a vraiment du privé. Les extraits de PROGRESSION.md (noms tirés des mails) sont
    privés : s'il y a d'autres extraits, on les laisse de côté et on répond en ligne (quelques secondes au lieu de 2 min).
    Local trop lent (60 s) → LENT : l’utilisateur décide de réessayer en ligne (en_ligne=True)."""
    extraits = chercher(question)
    if not extraits:
        return ("Je ne sais pas : je n'ai rien trouvé à ce sujet dans le guide du site ni dans les rapports. "
                "Regarde le menu Plus, ou demande-moi autrement."), ""
    publics = [(f, b) for f, b in extraits if "PROGRESSION" not in f]
    profil = "jarvis-rapide" if publics or en_ligne else "jarvis-prive"
    extraits = extraits if en_ligne or not publics else publics
    texte = securite.masquer_secrets("\n\n".join(f"[{f}]\n{b}" for f, b in extraits))
    try:
        msg, modele = _demander_projet(profil, question, texte)
    except Exception as e:  # noqa: BLE001
        if profil == "jarvis-prive" and type(e).__name__ in ("TimeoutError", "URLError", "HTTPError", "timeout"):
            return LENT, ""
        raise
    return (msg.get("content") or "").strip() or "Je ne sais pas.", modele


def _demander_projet(profil, question, texte):
    return demander(profil, [{"role": "system", "content": securite.CONSIGNE_DONNEES}, {"role": "user", "content":
        "Réponds à la question de l’utilisateur UNIQUEMENT avec ces extraits du projet Jarvis (son site sur http://127.0.0.1:4100). "
        "Dis où cliquer dans le site si c'est écrit, et cite le fichier entre crochets à la fin. Si la réponse n'est pas dans les "
        "extraits, réponds exactement « Je ne sais pas » puis dis où il pourrait regarder. 4 phrases maximum, tutoiement, mots simples.\n"
        f"Question : {question}\n{securite.encadrer(texte, 'projet')}"}], max_tokens=400, temperature=0,
        timeout=60 if profil == "jarvis-prive" else None)
