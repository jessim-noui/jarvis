r"""Mission 6 — Sauvegarde et restauration de Jarvis.

Une copie par jour dans sauvegardes\jarvis_AAAA-MM-JJ.zip, les 7 dernières sont gardées (choix de l’utilisateur).
Contenu : jarvis\donnees (mémoire SQLite comprise), les notes Obsidian de jarvis\memoire, la config du routeur.
JAMAIS : cles.env, gmail.env, .env, ni rien qui contient la valeur d'une vraie clé (vérifié fichier par fichier).
Ni photos ni vidéos : seuls ces dossiers-là sont lus.

Restaurer = d'abord une sauvegarde de l'état actuel (« avant_restauration »), puis remise en place, puis vérification.
Usage : py -3 -m suite.sauvegarde [--maintenant] [--verifier] [--restaurer FICHIER.zip]   (depuis jarvis)
"""
import fnmatch, hashlib, json, os, shutil, sqlite3, sys, tempfile, time, zipfile
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from commun import IA, DONNEES, MEMOIRE, RACINE, lire_json, ecrire_json, journaliser  # noqa: E402

DOSSIER = IA / "sauvegardes"
GARDER = 7
ETAT = DONNEES / "sauvegarde-etat.json"
SOURCES = {  # nom dans le zip -> dossier ou fichier sur le PC
    "donnees": DONNEES,
    "memoire": MEMOIRE,
    "routeur/config.yaml": RACINE / "routeur" / "config.yaml",
}
JAMAIS = ["cles.env", "gmail.env", "*.env", ".env*", "*.key", "*.pem", "*.tmp", "ARRET_URGENCE", ".obsidian/*", "*/.obsidian/*"]
TAILLE_MAX = 200 * 1024 * 1024  # un fichier de plus de 200 Mo n'a rien à faire ici


def _secrets():
    """Valeurs des vraies clés (pour vérifier qu'aucune ne part dans une sauvegarde). Jamais affichées."""
    vals = set()
    for f in [RACINE / "routeur" / "cles.env", *IA.glob("**/gmail.env")] if IA.exists() else []:
        try:
            for l in f.read_text(encoding="utf-8", errors="ignore").splitlines():
                v = l.partition("=")[2].strip() if "=" in l else l.strip()
                if len(v) >= 12 and "@" not in v and not l.lstrip().startswith("#"):
                    vals.add(v.encode("utf-8"))
        except OSError:
            pass
    return vals


def _exclu(rel):
    nom = rel.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(nom, m) or fnmatch.fnmatch(rel, m) for m in JAMAIS)


def _copie_sqlite(src):
    """Copie cohérente d'une base SQLite ouverte (API backup), au lieu de copier un fichier en cours d'écriture."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)  # sous Windows, un fichier resté ouvert ne peut pas être supprimé
    tmp = Path(tmp)
    try:
        with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(tmp)) as b:  # fermées : sinon Windows verrouille le fichier
            a.backup(b)
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def fichiers_a_sauver():
    for nom, chemin in SOURCES.items():
        if chemin.is_file():
            yield nom, chemin
        elif chemin.is_dir():
            for f in sorted(chemin.rglob("*")):
                if f.is_file():
                    rel = f"{nom}/{f.relative_to(chemin).as_posix()}"
                    if not _exclu(rel):
                        yield rel, f


def sauvegarder(nom=None, dossier=None):
    """Crée le zip. Renvoie {"fichier", "nb", "octets", "ecartes"}. Un fichier qui contient une clé est écarté."""
    dossier = Path(dossier or DOSSIER)
    dossier.mkdir(parents=True, exist_ok=True)
    nom = nom or f"jarvis_{time.strftime('%Y-%m-%d')}"
    cible = dossier / f"{nom}.zip"
    tmp = cible.with_suffix(".zip.tmp")
    secrets, ecartes, inventaire = _secrets(), [], {}
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, f in fichiers_a_sauver():
            try:
                if f.stat().st_size > TAILLE_MAX:
                    ecartes.append(f"{rel} (trop gros)")
                    continue
                contenu = _copie_sqlite(f) if f.suffix == ".db" else f.read_bytes()
            except (OSError, sqlite3.Error) as e:
                ecartes.append(f"{rel} ({type(e).__name__})")
                continue
            if any(s in contenu for s in secrets):
                ecartes.append(f"{rel} (contient une clé)")
                continue
            z.writestr(rel, contenu)
            inventaire[rel] = hashlib.sha256(contenu).hexdigest()
        z.writestr("INVENTAIRE.json", json.dumps({"cree": time.strftime("%Y-%m-%dT%H:%M:%S"), "fichiers": inventaire},
                                                 ensure_ascii=False, indent=1))
    os.replace(tmp, cible)
    res = {"fichier": str(cible), "nb": len(inventaire), "octets": cible.stat().st_size, "ecartes": ecartes}
    nettoyer(dossier)
    return res


def nettoyer(dossier=None, garder=GARDER):
    """Garde les `garder` sauvegardes quotidiennes les plus récentes (les « avant_restauration » sont gardées à part : 3)."""
    dossier = Path(dossier or DOSSIER)
    for motif, n in (("jarvis_2*.zip", garder), ("avant_restauration_*.zip", 3)):
        for vieux in sorted(dossier.glob(motif))[:-n]:
            vieux.unlink()


def verifier(fichier):
    """Relit le zip : intégrité (CRC), empreintes de l'inventaire, base SQLite lisible. Renvoie (ok, détail)."""
    try:
        with zipfile.ZipFile(fichier) as z:
            mauvais = z.testzip()
            if mauvais:
                return False, f"fichier abîmé : {mauvais}"
            inv = json.loads(z.read("INVENTAIRE.json"))["fichiers"]
            for rel, empreinte in inv.items():
                contenu = z.read(rel)
                if hashlib.sha256(contenu).hexdigest() != empreinte:
                    return False, f"empreinte différente : {rel}"
                if rel.endswith(".db"):
                    with tempfile.TemporaryDirectory() as td:
                        p = Path(td) / "t.db"
                        p.write_bytes(contenu)
                        with closing(sqlite3.connect(p)) as c:
                            if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                                return False, f"base abîmée : {rel}"
        return True, f"{len(inv)} fichiers vérifiés"
    except (OSError, zipfile.BadZipFile, KeyError, ValueError, sqlite3.Error) as e:
        return False, type(e).__name__


def restaurer(fichier, dossier=None):
    """Remet une sauvegarde en place. L'état actuel est d'abord sauvegardé (retour arrière possible).
    À lancer Jarvis ÉTEINT (sinon la base est en cours d'utilisation). cles.env n'est jamais touché."""
    ok, detail = verifier(fichier)
    if not ok:
        raise ValueError(f"Sauvegarde refusée : {detail}")
    avant = sauvegarder(f"avant_restauration_{time.strftime('%Y-%m-%d_%H%M%S')}", dossier)
    with zipfile.ZipFile(fichier) as z, tempfile.TemporaryDirectory() as td:
        z.extractall(td)  # noms vérifiés juste après : aucun chemin ne sort des dossiers prévus
        for rel in json.loads(z.read("INVENTAIRE.json"))["fichiers"]:
            racine, _, reste = rel.partition("/")
            if rel in SOURCES:
                cible = SOURCES[rel]
            elif racine in SOURCES and reste:
                cible = (SOURCES[racine] / reste).resolve()
                if not str(cible).startswith(str(SOURCES[racine].resolve())):
                    continue  # tentative de sortie du dossier : ignorée
            else:
                continue
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(td) / rel, cible)
    journaliser(agent="jarvis", action="restauration", etat="info", statut="ok", resume=Path(fichier).name)
    return {"restaure": Path(fichier).name, "avant": avant["fichier"]}


def quotidienne(forcer=False):
    """Appelée au lancement de Jarvis : une seule sauvegarde par jour, vérifiée. Ne lève jamais d'exception."""
    jour = time.strftime("%Y-%m-%d")
    e = lire_json(ETAT, {})
    if e.get("jour") == jour and e.get("ok") and not forcer:
        return e
    try:
        r = sauvegarder()
        ok, detail = verifier(r["fichier"])
        e = {"jour": jour, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "ok": ok, "detail": detail,
             "fichier": Path(r["fichier"]).name, "nb": r["nb"], "octets": r["octets"], "ecartes": r["ecartes"]}
    except Exception as err:
        e = {"jour": jour, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "ok": False, "detail": type(err).__name__}
    ecrire_json(ETAT, e)
    journaliser(agent="jarvis", action="sauvegarde", etat="info", statut="ok" if e["ok"] else "erreur", resume=e["detail"][:100])
    return e


def quotidienne_forcee():
    """Le bouton « Sauvegarder maintenant » (remplace la sauvegarde du jour)."""
    return quotidienne(forcer=True)


def liste(dossier=None):
    dossier = Path(dossier or DOSSIER)
    return [{"nom": f.name, "octets": f.stat().st_size, "t": time.strftime("%Y-%m-%dT%H:%M", time.localtime(f.stat().st_mtime))}
            for f in sorted(dossier.glob("*.zip"), reverse=True)] if dossier.exists() else []


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if "--restaurer" in sys.argv:
        print(json.dumps(restaurer(sys.argv[sys.argv.index("--restaurer") + 1]), ensure_ascii=False))
    elif "--verifier" in sys.argv:
        for s in liste():
            print(s["nom"], *verifier(DOSSIER / s["nom"]))
    else:
        print(json.dumps(sauvegarder() if "--maintenant" in sys.argv else quotidienne(), ensure_ascii=False, indent=1))
