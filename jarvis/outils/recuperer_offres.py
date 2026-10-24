r"""Mission 8 : remet dans le stock (donnees/offres-stock.json) les offres déjà lues qui ont disparu du site.

Avant la mission 8, chaque recherche écrasait la précédente dans offres-data.js. Les lectures, elles, sont restées
(offres-lues.json, clé = id = sha1(lien)[:10]), mais sans le lien. On retrouve le lien dans les Excel de l’utilisateur
(dossier « Recherche emploi », réglable par JARVIS_DOSSIER_EMPLOI, LUS seulement, jamais modifiés), puis on réinjecte l'offre si :
lue il y a moins de 30 jours, pas « plus en ligne », pas « pas pour moi ».

  py -3 outils\recuperer_offres.py            → récupère et affiche le nombre d'offres revenues
  py -3 outils\recuperer_offres.py --essai    → compte seulement, n'écrit rien
  py -3 outils\recuperer_offres.py --restaurer → remet le stock d'avant (sauvegarde faite au 1er passage)
"""
import os, sys, time, shutil, hashlib, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import offres  # noqa: E402
from commun import DONNEES, lire_json, ecrire_json  # noqa: E402

DOSSIER = Path(os.environ.get("JARVIS_DOSSIER_EMPLOI", Path.home() / "Documents" / "Recherche emploi"))
SAUVE = DONNEES / "sauvegardes" / "mission8-avant" / "offres-stock.json"


def liens_des_excel(dossier=DOSSIER):
    """{id: {lien, titre, entreprise, ville}} pour chaque ligne d'Excel qui a un lien."""
    import openpyxl
    out = {}
    for f in sorted(dossier.rglob("*.xlsx"), key=lambda p: p.stat().st_mtime):
        if f.name.startswith("~"):
            continue
        try:
            wb = openpyxl.load_workbook(f)
        except Exception:
            continue
        for ws in wb.worksheets:
            rows = list(ws.iter_rows())
            if not rows:
                continue
            h = [str(c.value or "").lower() for c in rows[0]]
            col = lambda *m: next((i for i, x in enumerate(h) if any(k in x for k in m)), None)  # noqa: E731
            ce, cv = col("entreprise"), col("ville", "lieu")
            for r in rows[1:]:
                for c in r:
                    lien = str(c.hyperlink.target) if c.hyperlink is not None and c.hyperlink.target else str(c.value or "")
                    if lien.startswith("http"):
                        g = lambda i: str(r[i].value or "").strip() if i is not None and i < len(r) else ""  # noqa: E731
                        out[hashlib.sha1(lien.encode()).hexdigest()[:10]] = {"lien": lien, "entreprise": g(ce), "ville": g(cv)}
                        break
    return out


def a_recuperer(stock, lues, refus, liens):
    limite = time.time() - offres.GARDE_JOURS * 86400
    for i, lu in lues.items():
        if i in stock or i in refus or i not in liens or lu.get("t", 0) < limite:
            continue
        if lu.get("etat") in ("pour_toi", "a_verifier", "ecartee", "erreur"):
            yield i, lu


def recuperer(essai=False):
    s = offres.stock()
    lues, refus = lire_json(DONNEES / "offres-lues.json", {}), lire_json(DONNEES / "offres-pas-pour-moi.json", {})
    liens = liens_des_excel()
    trouves = list(a_recuperer(s, lues, refus, liens))
    if essai or not trouves:
        return trouves
    if not SAUVE.exists():
        SAUVE.parent.mkdir(parents=True, exist_ok=True)
        ecrire_json(SAUVE, s)
    with offres._verrou:
        s = lire_json(offres.STOCK, {})
        for i, lu in trouves:
            e = liens[i]
            vu = datetime.datetime.fromtimestamp(lu["t"]).isoformat(timespec="minutes")
            zone = "Zone secondaire" if offres.region({"lieu": lu.get("lieu") or e["ville"]}, "Zone locale") == "Sud" else "Zone locale"
            s[i] = {"zone": zone, "premiere": vu, "derniere": vu, "recuperee": True,
                    "fiche": {"titre": lu.get("titre", ""), "entreprise": e["entreprise"], "lieu": lu.get("lieu") or e["ville"],
                              "contrat": lu.get("contrat", ""), "salaire": lu.get("salaire", ""), "lien": e["lien"], "vu": vu}}
        ecrire_json(offres.STOCK, s)
    return trouves


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--restaurer" in sys.argv:
        shutil.copy2(SAUVE, offres.STOCK)
        print("Stock d'avant remis.")
    else:
        t = recuperer(essai="--essai" in sys.argv)
        from collections import Counter
        print(f"{len(t)} offre(s) {'à récupérer' if '--essai' in sys.argv else 'revenue(s)'} :", dict(Counter(lu['etat'] for _, lu in t)))
