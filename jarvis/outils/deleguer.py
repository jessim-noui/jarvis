r"""Délégation : les IA gratuites du routeur écrivent un brouillon, Claude relit, teste et corrige.

Usage :
  py -3 outils\deleguer.py --consigne "Écris ..." --fichiers a.py b.js --sortie nom_du_brouillon.ext [--profil jarvis-code]

- Envoie au profil jarvis-code (par défaut) la consigne + SEULEMENT les fichiers de contexte donnés.
- Refuse tout fichier sensible (clés, mails, données perso) et masque toute valeur de clé connue.
- Écrit la réponse dans jarvis\outils\brouillons\<sortie> et note la délégation dans donnees\delegations.json
  (sert à estimer les tokens économisés par Claude).
"""
import sys, re, argparse, time
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))
from commun import DONNEES, demander, lire_json, ecrire_json  # noqa: E402
import securite  # noqa: E402

BROUILLONS = ICI / "brouillons"
INTERDITS = re.compile(r"(cles\.env|cl.\s?ia\.txt|gmail\.env|\.env|\.key$|\.pem$|[\\/]donnees[\\/]|journal-de-bord|"
                       r"candidatures-data\.js|offres-data\.js|telechargements\.js|profil\.txt|memoire\.db)", re.I)
SYSTEME = ("Tu es un développeur soigné. Tu écris du code simple, lisible, commenté en français, avec la bibliothèque "
           "standard d'abord. Réponds UNIQUEMENT avec le contenu final du fichier demandé, dans un seul bloc de code, "
           "sans explication avant ni après.")


def contenu_sur(chemin):
    p = Path(chemin)
    if INTERDITS.search(str(p).replace("/", "\\")):
        raise PermissionError(f"Fichier refusé (sensible) : {p.name}")
    texte = p.read_text(encoding="utf-8", errors="ignore")
    if securite.masquer_secrets(texte) != texte:
        raise PermissionError(f"Fichier refusé : il contient une clé ({p.name})")
    return texte


def extraire_code(texte):
    blocs = re.findall(r"```[\w+-]*\n(.*?)```", texte or "", flags=re.S)
    return max(blocs, key=len) if blocs else (texte or "")


def deleguer(consigne, fichiers=(), sortie="brouillon.txt", profil="jarvis-code", max_tokens=8000):
    from commun import LOCAUX
    if profil in LOCAUX or profil.startswith(("e-local", "e-oc-")):  # mission 13 : IA en ligne seulement, jamais Ollama
        raise ValueError("Délégation : IA en ligne seulement (jamais l'IA locale du PC).")
    contexte = "\n\n".join(f"### Fichier de contexte : {Path(f).name}\n```\n{contenu_sur(f)}\n```" for f in fichiers)
    msg, modele = demander(profil, [{"role": "system", "content": SYSTEME},
                                    {"role": "user", "content": securite.masquer_secrets(consigne) + "\n\n" + contexte}],
                           max_tokens=max_tokens, temperature=0.2, timeout=300)
    code = extraire_code(msg.get("content"))
    BROUILLONS.mkdir(exist_ok=True)
    cible = BROUILLONS / Path(sortie).name
    cible.write_text(code, encoding="utf-8")
    journal = lire_json(DONNEES / "delegations.json", [])
    journal.append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "sortie": cible.name, "modele": modele,
                    "consigne": consigne[:200], "caracteres_ecrits": len(code),
                    "tokens_economises_estimes": len(code) // 4})  # ce que Claude n'a pas eu à écrire
    ecrire_json(DONNEES / "delegations.json", journal)
    return cible, modele


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = argparse.ArgumentParser()
    a.add_argument("--consigne", required=True)
    a.add_argument("--fichiers", nargs="*", default=[])
    a.add_argument("--sortie", required=True)
    a.add_argument("--profil", default="jarvis-code")
    a.add_argument("--max-tokens", type=int, default=8000)
    x = a.parse_args()
    cible, modele = deleguer(x.consigne, x.fichiers, x.sortie, x.profil, x.max_tokens)
    print(f"Brouillon écrit : {cible} ({modele}). À relire et tester avant usage.")
