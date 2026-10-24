r"""Mission 16, étape 8 : la dictée rapide du chat.
Avant : entretien.py chargeait Whisper « small » à CHAQUE dictée, et la carte graphique ne marchait pas (cublas64_12.dll introuvable :
les bibliothèques CUDA sont installées par pip dans site-packages\nvidia\*\bin mais pas sur le chemin des DLL) → processeur, lent.
Maintenant : « small » sur la carte graphique (float16), GARDÉ chargé tant que la page est ouverte et que l’utilisateur est là (≈ 1 Go),
libéré en jeu, absent ou après 10 min sans dictée ; vad_filter coupe les silences ; la page envoie le son toutes les 2 s pendant
qu'il parle (texte en direct). Sans carte graphique : « base » sur le processeur (0,7 s pour 11 s de parole).
Le son n'est jamais écrit sur le disque : il reste en mémoire le temps de la transcription. Medium reste pour les vidéos (video.py).
"""
import base64, gc, glob, os, threading, time

import commun

_m = {"modele": None, "nom": "", "t": 0.0}
_verrou = threading.Lock()
LIBRE_APRES = 600  # s sans dictée


def chemins_cuda():
    """Les DLL CUDA installées par pip (nvidia-cublas-cu12, nvidia-cudnn-cu12) : ajoutées au chemin de recherche."""
    try:
        import nvidia
    except ImportError:
        return
    for p in nvidia.__path__:
        for d in glob.glob(os.path.join(p, "*", "bin")):
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
            if d not in os.environ.get("PATH", ""):
                os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")


def modele():
    import numpy
    with _verrou:
        if _m["modele"] is None:
            chemins_cuda()
            from faster_whisper import WhisperModel
            try:
                m = WhisperModel("small", device="cuda", compute_type="float16")
                list(m.transcribe(numpy.zeros(16000, numpy.float32), language="fr")[0])  # chauffe : la 1re fois prend ~20 s
                _m.update(modele=m, nom="small · carte graphique")
            except Exception:  # pas de carte graphique utilisable
                _m.update(modele=WhisperModel("base", device="cpu", compute_type="int8"), nom="base · processeur")
        _m["t"] = time.time()
        return _m["modele"], _m["nom"]


def liberer():
    with _verrou:
        if _m["modele"] is not None:
            _m.update(modele=None, nom="")
            gc.collect()
            return True
    return False


def surveiller():
    """Appelé par le gardien (presence.tour) : en jeu, absent ou 10 min sans dictée → le modèle quitte la carte graphique."""
    if _m["modele"] is not None and (not commun.peut_travailler() or time.time() - _m["t"] > LIBRE_APRES):
        liberer()


def prechauffer():
    """La page du chat est ouverte : on charge le modèle en fond (seulement si l’utilisateur est là et pas en jeu)."""
    if not commun.peut_travailler():
        return {"ok": False, "raison": "en pause"}
    threading.Thread(target=modele, daemon=True).start()
    return {"ok": True}


def transcrire(pcm_b64):
    """PCM 16 bits mono 16 kHz (base64) → {"texte", "ms", "modele"}."""
    if not commun.peut_travailler():
        liberer()
        raise ValueError("Jarvis est en pause (jeu ou absence) : la dictée attend.")
    import numpy
    brut = base64.b64decode(pcm_b64 or "", validate=True)
    if not 3200 <= len(brut) <= 60 * 32000:
        raise ValueError("enregistrement trop court ou trop long (60 s au plus)")
    son = numpy.frombuffer(brut, numpy.int16).astype(numpy.float32) / 32768
    m, nom = modele()
    t = time.time()
    with _verrou:
        segs = list(m.transcribe(son, language="fr", vad_filter=True, beam_size=1)[0])
    return {"texte": " ".join(s.text.strip() for s in segs).strip(), "ms": round((time.time() - t) * 1000), "modele": nom}
