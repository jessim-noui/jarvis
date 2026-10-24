r"""maj_modeles.py — compare les catalogues des fournisseurs à config.yaml.

Ne modifie JAMAIS la config. Il produit des propositions pour la veille :
  - un modèle de la config qui a disparu du catalogue  -> « à remplacer » ;
  - un nouveau modèle apparu dans un catalogue          -> « à essayer ».
Le premier lancement mémorise les catalogues sans rien proposer (sinon 600 « nouveautés »).

Usage : py -3 maj_modeles.py      (écrit donnees\propositions-modeles.json)
"""
import os, re, datetime
import yaml
from commun import RACINE, DONNEES, http_json, lire_json, ecrire_json

CONFIG = RACINE / "routeur" / "config.yaml"
INSTANTANE = DONNEES / "catalogues.json"
SORTIE = DONNEES / "propositions-modeles.json"
E = os.environ

FOURNISSEURS = {
    # préfixe LiteLLM : (url du catalogue, en-têtes, extraction des identifiants)
    "groq": ("https://api.groq.com/openai/v1/models", lambda: {"Authorization": "Bearer " + E.get("GROQ_API_KEY", "")}),
    "mistral": ("https://api.mistral.ai/v1/models", lambda: {"Authorization": "Bearer " + E.get("MISTRAL_API_KEY", "")}),
    "nvidia_nim": ("https://integrate.api.nvidia.com/v1/models", lambda: {"Authorization": "Bearer " + E.get("NVIDIA_API_KEY", "")}),
    "openrouter": ("https://openrouter.ai/api/v1/models", lambda: {}),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000",
               lambda: {"x-goog-api-key": E.get("GEMINI_API_KEY", "")}),
    "ollama_chat": ("http://127.0.0.1:11434/api/tags", lambda: {}),
}
# Bruit à ignorer : embeddings, TTS, modération, OCR...
IGNORER = re.compile(r"embed|tts|whisper|guard|moderation|ocr|reward|safety|transcribe|orpheus|lyria|clip|parse|retriever|calibration|detector", re.I)


def catalogue(nom):
    url, entetes = FOURNISSEURS[nom]
    r = http_json(url, headers=entetes(), timeout=30)
    if nom == "gemini":
        return sorted(m["name"].removeprefix("models/") for m in r.get("models", [])
                      if "generateContent" in m.get("supportedGenerationMethods", []))
    if nom == "ollama_chat":
        return sorted(m["name"] for m in r.get("models", []))
    ids = [m["id"] for m in r.get("data", [])]
    if nom == "openrouter":
        ids = [i for i in ids if i.endswith(":free")]   # gratuits seulement
    return sorted(ids)


def modeles_config():
    """{(fournisseur, modele): [noms de profils]} lus dans config.yaml."""
    conf = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    res = {}
    for d in conf.get("model_list", []):
        fourn, _, mod = d["litellm_params"]["model"].partition("/")
        res.setdefault((fourn, mod), []).append(d["model_name"])
    return res


def main():
    aujourdhui = datetime.date.today().isoformat()
    ancien = lire_json(INSTANTANE, {})
    nouveau, erreurs, props = {}, [], []
    for nom in FOURNISSEURS:
        try:
            nouveau[nom] = catalogue(nom)
        except Exception as e:  # un fournisseur en panne ne bloque pas les autres
            erreurs.append(f"{nom} : {type(e).__name__}")
            nouveau[nom] = ancien.get(nom, [])

    for (fourn, mod), profils in modeles_config().items():
        if fourn in nouveau and nouveau[fourn] and mod not in nouveau[fourn]:
            props.append({
                "titre": f"Modèle disparu : {fourn}/{mod}",
                "lien": FOURNISSEURS[fourn][0].split("/v1")[0],
                "categorie": "Routeur IA",
                "pour_toi": f"Ce modèle n'est plus au catalogue. Les profils {', '.join(sorted(set(profils)))} basculent donc sur l'étage suivant : il faut choisir un remplaçant.",
                "risque": "faible", "risque_raison": "On change juste une ligne de config.yaml, sauvegardée avant.",
                "effort": "5 min", "avis": "à ajouter", "source": "maj_modeles", "date": aujourdhui,
            })

    if ancien:  # pas de « nouveautés » au tout premier lancement
        for fourn, ids in nouveau.items():
            for mod in sorted(set(ids) - set(ancien.get(fourn, []))):
                if IGNORER.search(mod) or fourn == "ollama_chat":
                    continue
                props.append({
                    "titre": f"Nouveau modèle : {fourn}/{mod}",
                    "lien": FOURNISSEURS[fourn][0].split("/v1")[0],
                    "categorie": "Routeur IA",
                    "pour_toi": "Nouveau modèle gratuit apparu chez ce fournisseur. À tester avec un petit appel avant de l'ajouter à un profil.",
                    "risque": "faible", "risque_raison": "Rien ne change tant que tu ne l'ajoutes pas à config.yaml.",
                    "effort": "10 min", "avis": "à ajouter", "source": "maj_modeles", "date": aujourdhui,
                })

    ecrire_json(INSTANTANE, nouveau)
    ecrire_json(SORTIE, {"date": aujourdhui, "erreurs": erreurs, "propositions": props})
    print(f"{len(props)} proposition(s) modèles, {len(erreurs)} fournisseur(s) injoignable(s).")
    return props


if __name__ == "__main__":
    main()
