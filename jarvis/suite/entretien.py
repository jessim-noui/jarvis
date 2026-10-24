"""Mission 15, étape 13 : l'entraînement d'entretien (maquette R_Entretien, images 16 à 18).

- Sujets : les projets et expériences de la page Moi (moi.json) + Question surprise.
- La question : 1 appel à l'IA Rédaction, à partir de moi.json seulement (gardée en mémoire tant que le serveur tourne).
- Le son : enregistré par le navigateur seulement au clic, envoyé en PCM 16 kHz, écrit dans un fichier temporaire de Jarvis,
  transcrit par Whisper sur le PC (faster-whisper), puis effacé tout de suite (même en cas d'erreur).
- Le retour : 4 critères + « Ta réponse en mieux », passée au vérificateur des lettres (verif_lettre) : seulement les vrais faits.
- Rien n'est gardé sans « Garder » (donnees/entretien.json). En pause pendant un jeu (peut_travailler).
"""
import base64, json, re, threading, time, wave
from commun import DONNEES, lire_json, ecrire_json, demander, extraire_json, peut_travailler
import verif_lettre

TEMP = DONNEES / "tmp_entretien"
GARDE = DONNEES / "entretien.json"
EUH = re.compile(r"\b(euh+|heu+|hum+|bah|ben)\b", re.I)
SEC_MAX = 90
_questions, _verrou = {}, threading.Lock()


def _moi():
    return lire_json(DONNEES / "moi.json", {})


def sujets():
    s = [{"id": f"p{k}", "nom": p["titre"].split("BTS : ", 1)[1].capitalize() if p["titre"].startswith("Projet de BTS : ") else p.get("court") or p["titre"],
          "titre": p["titre"]} for k, p in enumerate(_moi().get("projets", []))]
    return s + [{"id": "experience", "nom": "Mon expérience", "titre": "Mon expérience"}, {"id": "surprise", "nom": "Question surprise", "titre": "Question surprise"}]


def _faits(sujet):
    """Seulement les faits de moi.json utiles au sujet (rien d'autre n'est envoyé à l'IA)."""
    m = _moi()
    if sujet == "experience":
        experience = next((e for e in m.get("experiences", []) if "stage" in str(e.get("titre", "")).lower()), {})
        return json.dumps(experience, ensure_ascii=False)
    if sujet == "surprise":
        return json.dumps({"accroche": m.get("accroche", ""), "formation": m.get("formation", []), "experiences": m.get("experiences", [])}, ensure_ascii=False)
    k = int(sujet[1:]) if re.fullmatch(r"p\d{1,2}", sujet or "") else -1
    p = m.get("projets", [])
    if not 0 <= k < len(p):
        raise ValueError("sujet inconnu")
    return json.dumps(p[k], ensure_ascii=False)


def _pause():
    if not peut_travailler():
        raise PermissionError("Jarvis est en pause (jeu, absence ou arrêt d'urgence) : l'entraînement reprendra après.")


def question(sujet, nouvelle=False):
    faits = _faits(sujet)
    if sujet in _questions and not nouvelle:
        return {"sujet": sujet, "question": _questions[sujet]}
    _pause()
    msg, _ = demander("jarvis-prive", [{"role": "user", "content":
        "Tu es un recruteur en entretien pour un poste en informatique (support, réseau, cybersécurité ou développement web). Voici les faits "
        f"sur la personne candidate :\n{faits}\n"
        "Pose UNE question d'entretien précise sur ces faits (une seule phrase, 30 mots au plus, tutoiement). N'invente aucun "
        "détail qui n'est pas dans les faits. Réponds seulement par la question."}], max_tokens=120, temperature=0.7)
    q = " ".join(str(msg.get("content") or "").replace("*", "").split()).strip("«»\" ")[:300] or "Présente-moi ce projet en une minute."
    _questions[sujet] = q
    return {"sujet": sujet, "question": q}


def transcrire(pcm_b64, sec):
    """PCM 16 bits mono 16 kHz (base64) → texte. Le fichier temporaire est effacé juste après la transcription."""
    _pause()
    brut = base64.b64decode(pcm_b64 or "", validate=True)
    if not 16000 <= len(brut) <= SEC_MAX * 32000 + 1000:
        raise ValueError("enregistrement trop court ou trop long")
    TEMP.mkdir(parents=True, exist_ok=True)
    f = TEMP / f"reponse-{int(time.time() * 1000)}.wav"
    try:
        with wave.open(str(f), "wb") as w:
            w.setnchannels(1), w.setsampwidth(2), w.setframerate(16000), w.writeframes(brut)
        texte = _whisper(f)
    finally:
        f.unlink(missing_ok=True)
    mots = len(re.findall(r"\w+", texte))
    return {"texte": texte, "duree": round(float(sec or len(brut) / 32000)), "mots": mots, "euh": len(EUH.findall(texte))}


def _whisper(f):
    import numpy
    from faster_whisper import WhisperModel
    __import__("suite.dictee").dictee.chemins_cuda()  # mission 16 : sans ça, cublas64_12.dll introuvable → processeur
    with _verrou, wave.open(str(f)) as w:
        son = numpy.frombuffer(w.readframes(w.getnframes()), numpy.int16).astype(numpy.float32) / 32768
        try:
            m = WhisperModel("small", device="cuda", compute_type="float16")
            segs = list(m.transcribe(son, language="fr", vad_filter=False)[0])
        except Exception:  # pas de carte graphique disponible : processeur
            m = WhisperModel("small", device="cpu", compute_type="int8")
            segs = list(m.transcribe(son, language="fr", vad_filter=False)[0])
    return " ".join(s.text.strip() for s in segs).strip()


def mieux_verifie(texte, question_):
    """Même vérificateur que les lettres : chaque phrase « je » ne garde que des faits de moi.json."""
    r = verif_lettre.verifier(texte, _moi(), question_)
    corps = r["texte"].replace("Madame, Monsieur,", "").strip()
    return " ".join(corps.split()), [p for p, _ in r["retire"]]


def retour(sujet, question_, reponse, duree):
    _pause()
    faits = _faits(sujet)
    msg, _ = demander("jarvis-prive", [{"role": "user", "content":
        f"Question d'entretien : « {question_} »\nRéponse orale de la personne candidate (transcrite) : « {reponse} »\nSes faits vérifiés : {faits}\n"
        'Réponds UNIQUEMENT par ce JSON : {"clair":{"e":"ok|moyen|non","x":"<1 phrase>"},"concret":{"e":"…","x":"…"},'
        '"resultat":{"e":"…","x":"…"},"appris":{"e":"…","x":"…"},"mieux":"<un texte : sa réponse améliorée, 4 phrases au plus, à la 1re '
        'personne>"}. Chaque "x" est une phrase de conseil, jamais vide. clair = on comprend ; concret = '
        "des exemples précis ; resultat = il dit ce que ça a donné ; appris = il dit ce qu'il en retient. « mieux » n'utilise QUE "
        "ses vrais faits et sa réponse : aucun chiffre, outil, action, raison ou résultat qui n'y est pas (pas de bibliothèque, de jury ni de "
        "test inventés). Tutoie-le dans les critères. Mots simples, sans astérisques."}],
        max_tokens=700, temperature=0.3, response_format={"type": "json_object"})
    d = extraire_json(msg.get("content")) or {}
    crit = {}
    for k in ("clair", "concret", "resultat", "appris"):
        v = d.get(k) if isinstance(d.get(k), dict) else {}
        crit[k] = {"e": v.get("e") if v.get("e") in ("ok", "moyen", "non") else "moyen", "x": str(v.get("x", "")).replace("*", "")[:200]}
    m = d.get("mieux", "")
    m = next((v for v in m.values() if isinstance(v, str)), "") if isinstance(m, dict) else str(m)  # une IA renvoie parfois {"version": …}
    mieux, retire = mieux_verifie(m.replace("*", ""), question_)
    return {"criteres": crit, "mieux": mieux, "retire": retire, "duree_ok": 30 <= int(duree or 0) <= 60}


def garder(e):
    x = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "sujet": str(e.get("sujet", ""))[:20], "question": str(e.get("question", ""))[:300],
         "reponse": str(e.get("reponse", ""))[:2000], "duree": int(e.get("duree") or 0), "euh": int(e.get("euh") or 0),
         "mots": int(e.get("mots") or 0), "criteres": {k: str((e.get("criteres") or {}).get(k, {}).get("e", ""))[:6]
                                                       for k in ("clair", "concret", "resultat", "appris")}}
    with _verrou:
        ecrire_json(GARDE, (lire_json(GARDE, []) + [x])[-200:])
    return bilan()


NOMS = {"clair": "clair", "concret": "concret", "resultat": "dire le résultat", "appris": "dire ce que tu as appris"}


def bilan():
    """Les 7 derniers jours, seulement ce que l'utilisateur a gardé : nombre, temps de parole, ce qui progresse, ce qui reste."""
    limite = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - 7 * 86400))
    s = [x for x in lire_json(GARDE, []) if x["t"] >= limite]
    note = {"ok": 2, "moyen": 1, "non": 0}
    moy = lambda l, k: sum(note.get(x["criteres"].get(k), 1) for x in l) / len(l)
    progres = travail = ""
    if s:
        travail = NOMS[min(NOMS, key=lambda k: moy(s, k))]
        if len(s) >= 2:
            debut, fin = s[:len(s) // 2], s[len(s) // 2:]
            k = max(NOMS, key=lambda k: moy(fin, k) - moy(debut, k))
            if moy(fin, k) > moy(debut, k):
                progres = NOMS[k]
    return {"questions": len(s), "secondes": sum(x["duree"] for x in s), "progres": progres, "travail": travail}
