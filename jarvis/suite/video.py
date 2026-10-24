r"""Mission 10 — Jarvis regarde vraiment une vidéo (skill analyse-video) : lien ou fichier local.

Lien (YouTube, TikTok, Instagram…) → yt-dlp télécharge dans donnees\videos-temp\<id>\ (effacé après l'analyse).
Fichier local → lu sur place, JAMAIS modifié, copié ailleurs ni déplacé (ffmpeg le lit seulement ; les images et le son
extraits vont dans le dossier temporaire, effacé à la fin).
Analyse : son → texte (faster-whisper, local, langue détectée (français surtout), carte graphique si possible) ; images clés (ffmpeg : 1 toutes les 5 s
+ changements de plan, 24 au plus) décrites par jarvis-vision (Gemini Flash, gratuit) ; puis résumé, idées à retenir,
conseils de montage, avec les minutages. Les étapes sont visibles (_etat) ; le résultat est gardé dans donnees\videos.json.
"""
import base64, re, shutil, subprocess, sys, threading, time, uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import DONNEES, lire_json, ecrire_json, journaliser, demander  # noqa: E402

TEMP = DONNEES / "videos-temp"
RESULTATS = DONNEES / "videos.json"
EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
DUREE_MAX = 20 * 60  # secondes
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_etat = {}  # id -> {etape, en_cours, erreur, resultat}
_verrou = threading.Lock()


def _run(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=SANS_FENETRE)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[-1][:200] if (r.stderr or r.stdout).strip() else "erreur")
    return r.stdout


def source_valide(source):
    """Renvoie ("lien", url) ou ("fichier", Path) ; ValueError sinon."""
    s = (source or "").strip().strip('"')
    if re.fullmatch(r"https?://[^\s\"'<>]{5,500}", s):
        return "lien", s
    p = Path(s)
    if p.is_file() and p.suffix.lower() in EXT:
        return "fichier", p
    raise ValueError("Donne un lien de vidéo (https://…) ou le chemin d'un fichier vidéo de ton PC.")


def _etape(ident, texte):
    _etat[ident].update(etape=texte)


def _telecharger(ident, url, dossier):
    _etape(ident, "Téléchargement…")
    _run(["yt-dlp", "--no-playlist", "--no-progress", "-f", "b[height<=720]/bv*[height<=720]+ba/b", "--match-filter",
          f"duration < {DUREE_MAX}", "-o", str(dossier / "video.%(ext)s"), url], timeout=900)
    v = next((f for f in dossier.iterdir() if f.name.startswith("video.")), None)
    if not v:
        raise RuntimeError("vidéo non téléchargée (trop longue, privée ou lien non pris en charge)")
    return v


def _duree(video):
    return float(_run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)]).strip() or 0)


def _ecouter(ident, video, dossier):
    _etape(ident, "Écoute…")
    wav = dossier / "audio.wav"
    try:
        _run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000", str(wav)])
    except RuntimeError:
        return ""  # pas de piste son
    import wave, numpy
    from faster_whisper import WhisperModel
    with wave.open(str(wav)) as w:  # le son déjà en 16 kHz mono : pas besoin de PyAV (sa version 19 casse faster-whisper 1.2)
        son = numpy.frombuffer(w.readframes(w.getnframes()), numpy.int16).astype(numpy.float32) / 32768
    try:
        m = WhisperModel("medium", device="cuda", compute_type="float16")
        segs, _ = m.transcribe(son, vad_filter=True)
        segs = list(segs)
    except Exception:  # pas de carte graphique disponible : processeur, modèle plus petit
        m = WhisperModel("small", device="cpu", compute_type="int8")
        segs, _ = m.transcribe(son, vad_filter=True)
        segs = list(segs)
    return "\n".join(f"[{_mmss(s.start)}] {s.text.strip()}" for s in segs)


def _mmss(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}"


def _images(ident, video, dossier, duree):
    """1 image toutes les 5 s + les changements de plan (repérés par ffmpeg), 24 au plus, réparties sur toute la vidéo."""
    _etape(ident, "Images…")
    out = dossier / "img"
    out.mkdir()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(video), "-vf", "select='gt(scene,0.4)',showinfo", "-an", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900, creationflags=SANS_FENETRE)
    plans = [float(x) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    temps = sorted({round(t, 1) for t in [i * 5.0 for i in range(int(duree // 5) + 1)] + plans if t < duree})
    if len(temps) > 24:
        temps = [temps[round(i * (len(temps) - 1) / 23)] for i in range(24)]
    images = []
    for n, t in enumerate(temps):
        f = out / f"f_{n:02d}.jpg"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", "-vf", "scale=480:-2", str(f)],
                       capture_output=True, timeout=120, creationflags=SANS_FENETRE)
        if f.is_file():
            images.append((t, f))
    return images


def _decrire(ident, images):
    """Les images clés décrites par jarvis-vision, par paquets de 8."""
    lignes = []
    for i in range(0, len(images), 8):
        paquet = images[i:i + 8]
        contenu = [{"type": "text", "text": "Décris très brièvement chaque image (une ligne chacune, en français) : ce qu'on voit, texte "
                    "à l'écran, type de plan. Format : « mm:ss — description ». Minutages : " + ", ".join(_mmss(t) for t, _ in paquet)}]
        contenu += [{"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(f.read_bytes()).decode()}}
                    for _, f in paquet]
        msg, modele = demander("jarvis-vision", [{"role": "user", "content": contenu}], max_tokens=900)
        lignes.append((msg.get("content") or "").strip())
    return "\n".join(lignes)


CONSIGNE = ("Tu analyses une vidéo pour l’utilisateur à partir de sa transcription et de la description de ses images clés. Réponds en "
            "français simple, court, lisible sur téléphone, sans gras ni titre Markdown, avec ces 4 parties : « De quoi ça parle » "
            "(2-3 phrases), « À retenir » (les idées, outils ou techniques utiles, avec leurs minutages mm:ss), « Conseils de montage » "
            "(accroche, rythme des plans, sous-titres, ce qu'il pourrait copier dans ses vlogs, avec minutages), « Prochaine action » "
            "(une seule). Résume avec tes mots, ne recopie pas de longs passages. N'invente rien qui ne soit ni dit ni montré.")


def _travailler(ident, source):
    dossier = TEMP / ident
    dossier.mkdir(parents=True, exist_ok=True)
    e = _etat[ident]
    try:
        genre, s = source_valide(source)
        video = _telecharger(ident, s, dossier) if genre == "lien" else s
        duree = _duree(video)
        if duree > DUREE_MAX:
            raise RuntimeError(f"vidéo trop longue ({round(duree / 60)} min, 20 min au plus)")
        texte = _ecouter(ident, video, dossier)
        images = _images(ident, video, dossier, duree)
        descr = _decrire(ident, images) if images else ""
        _etape(ident, "Résumé…")
        from suite import skills_agents
        msg, modele = demander("jarvis-redaction", [{"role": "system", "content": CONSIGNE + skills_agents.pour("video")},
                                                    {"role": "user", "content": f"Durée : {_mmss(duree)}.\n\nTranscription :\n"
                                                     f"{texte[:12000] or '(pas de son ou pas de parole)'}\n\nImages clés :\n{descr[:6000]}"}],
                                 max_tokens=1200, temperature=0.3)
        r = {"id": ident, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "source": source[:300], "genre": genre, "duree": _mmss(duree),
             "analyse": (msg.get("content") or "").strip(), "transcription": texte[:20000], "images": descr[:8000], "modele": modele,
             "nb_images": len(images)}
        with _verrou:
            ecrire_json(RESULTATS, ([x for x in lire_json(RESULTATS, []) if x.get("id") != ident] + [r])[-20:])
        e.update(en_cours=False, etape="Terminé", resultat=r)
        journaliser(agent="video", action="regarder une vidéo", etat="info", statut="ok", resume=f"{genre}, {r['duree']}")
    except Exception as x:
        e.update(en_cours=False, etape="Erreur", erreur=f"{type(x).__name__} : {str(x)[:200]}")
        journaliser(agent="video", action="regarder une vidéo", etat="info", statut="erreur", resume=str(x)[:120])
    finally:
        shutil.rmtree(dossier, ignore_errors=True)  # le téléchargement et les extraits sont effacés ; l'original local n'est jamais touché


def lancer(source):
    """Démarre l'analyse en arrière-plan ; une seule à la fois. Renvoie l'id (ValueError si la source est invalide)."""
    source_valide(source)
    with _verrou:
        if any(v.get("en_cours") for v in _etat.values()):
            raise RuntimeError("Je regarde déjà une vidéo : attends qu'elle soit finie.")
        ident = uuid.uuid4().hex[:8]
        _etat[ident] = {"id": ident, "en_cours": True, "etape": "Préparation…", "source": source[:300]}
    threading.Thread(target=_travailler, args=(ident, source), daemon=True, name="video").start()
    return ident


def etat(ident=None):
    if ident:
        return _etat.get(ident) or next(({"id": ident, "en_cours": False, "etape": "Terminé", "resultat": r}
                                         for r in lire_json(RESULTATS, []) if r.get("id") == ident), None)
    return {"en_cours": [v for v in _etat.values() if v.get("en_cours")], "resultats": list(reversed(lire_json(RESULTATS, [])))[:10]}


DEMANDE = re.compile(r"^\s*(?:jarvis[ ,:]+)?(?:regarde|analyse|resume|résume)\b.{0,40}?\b(?:cette |la |une )?vid[eé]o\b\s*:?\s*(\S+)", re.I)


def depuis_chat(q):
    """« regarde cette vidéo : <lien ou chemin> » → réponse du chat avec le suivi, sinon None."""
    m = DEMANDE.search(q or "")
    if not m:
        return None
    reste = q[m.start(1):].strip()
    try:
        ident = lancer(reste)
    except (ValueError, RuntimeError) as e:
        return {"reponse": str(e), "agent": "video", "agent_nom": "Vidéo", "modele": ""}
    return {"reponse": "Je regarde la vidéo : je télécharge si besoin, j'écoute, je regarde les images, puis je résume.",
            "video": {"id": ident}, "agent": "video", "agent_nom": "Vidéo", "modele": ""}
