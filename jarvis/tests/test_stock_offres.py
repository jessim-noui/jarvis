"""Mission 8 : le stock d'offres. Deux recherches de suite ne perdent rien ; une candidature ne disparaît jamais ;
une erreur de lecture ne fait pas disparaître l'annonce ; analyser_offres fusionne au lieu d'écraser.
(Brouillon de mistral-code-latest via deleguer.py, réécrit par Claude.)"""
import sys, json, shutil, tempfile, datetime, unittest, importlib.util
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import offres  # noqa: E402


def il_y_a(jours):
    return (datetime.datetime.now() - datetime.timedelta(days=jours)).isoformat(timespec="minutes")


def offre(n, vu):
    return {"titre": f"Offre {n}", "entreprise": f"Entreprise {n}", "lieu": "38 - Grenoble", "lien": f"https://exemple.fr/{n}", "vu": vu}


class TestStock(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.d, True)
        p = patch.multiple(offres, SITE=self.d, DONNEES=self.d, STOCK=self.d / "stock.json", POSTULEES=self.d / "postulees.json",
                           LIENS=self.d / "liens.json", VUES=self.d / "vues.json")
        p.start()
        self.addCleanup(p.stop)

    def recherche(self, *fiches):
        (self.d / "offres-data.js").write_text("window.OFFRES = " + json.dumps({"zones": {"Grenoble": {"date": il_y_a(0), "retenues": list(fiches)}}}) + ";",
                                               encoding="utf-8")

    def ecrire(self, nom, donnees):
        (self.d / nom).write_text(json.dumps(donnees), encoding="utf-8")

    def titres(self):
        return sorted(o["titre"] for o in offres.liste(brut=True))

    def test_deux_recherches_aucune_perte(self):
        self.recherche(offre(1, il_y_a(1)))
        offres.liste(brut=True)
        self.recherche(offre(2, il_y_a(0)))
        self.assertEqual(self.titres(), ["Offre 1", "Offre 2"])

    def test_doublon_fusionne_la_plus_recente_gagne(self):
        self.recherche(offre(1, il_y_a(2)))
        offres.stock()
        self.recherche(dict(offre(1, il_y_a(0)), titre="Offre 1 (mise à jour)"))
        s = offres.stock()
        self.assertEqual(len(s), 1)
        self.assertEqual(s[offres.ident_de(offre(1, ""))]["fiche"]["titre"], "Offre 1 (mise à jour)")
        self.recherche(dict(offre(1, il_y_a(5)), titre="vieille copie"))  # une copie plus ancienne ne gagne pas
        self.assertEqual(offres.stock()[offres.ident_de(offre(1, ""))]["fiche"]["titre"], "Offre 1 (mise à jour)")

    def test_trente_jours_etiquette_pas_archivee(self):  # mission 10 : plus aucun archivage automatique
        self.recherche(offre(1, il_y_a(40)), offre(2, il_y_a(0)))
        self.assertEqual(self.titres(), ["Offre 1", "Offre 2"])
        x = next(o for o in offres.liste(brut=True) if o["titre"] == "Offre 1")
        self.assertEqual(x["etiquettes"], ["+30 jours"])
        self.assertNotIn("archivee", offres.stock()[offres.ident_de(offre(1, ""))])

    def test_trois_recherches_aucune_offre_perdue(self):  # mission 10
        self.recherche(offre(1, il_y_a(50)), offre(2, il_y_a(2)))
        offres.liste(brut=True)
        self.recherche(offre(3, il_y_a(1)))
        offres.liste(brut=True)
        self.ecrire("liens.json", {offre(2, "")["lien"]: {"etat": "casse", "t": 0}})
        self.recherche(offre(4, il_y_a(0)))
        self.assertEqual(self.titres(), ["Offre 1", "Offre 2", "Offre 3", "Offre 4"])

    def test_enlever_puis_remettre(self):  # mission 10 : seul l’utilisateur enlève, la corbeille garde tout
        self.recherche(offre(1, il_y_a(0)), offre(2, il_y_a(0)))
        i = offres.ident_de(offre(1, ""))
        offres.choisir(i, "enlever")
        self.assertEqual(self.titres(), ["Offre 2"])
        self.assertEqual([o["titre"] for o in offres.corbeille()], ["Offre 1"])
        offres.choisir(i, "remettre")
        self.assertEqual(self.titres(), ["Offre 1", "Offre 2"])
        offres.choisir(i, "garder")
        self.assertTrue(offres.liste(brut=True)[0]["gardee"])
        with self.assertRaises(ValueError):
            offres.choisir(i, "supprimer")

    def test_ancienne_archive_automatique_revient(self):
        o = offre(1, il_y_a(0))
        self.recherche(o)
        self.ecrire("stock.json", {offres.ident_de(o): {"zone": "Grenoble", "fiche": o, "premiere": il_y_a(0), "derniere": il_y_a(0),
                                                       "archivee": {"t": "x", "pourquoi": "lien mort"}}})
        self.assertEqual(self.titres(), ["Offre 1"])

    def test_postulee_jamais_archivee(self):
        o = offre(1, il_y_a(40))
        self.ecrire("postulees.json", {offres.ident_de(o): {"t": il_y_a(40), "titre": "Offre 1", "lien": o["lien"]}})
        self.ecrire("liens.json", {o["lien"]: {"etat": "casse", "t": 0}})  # même si l'annonce est retirée
        self.recherche(o)
        self.assertEqual(self.titres(), ["Offre 1"])

    def test_candidature_sans_annonce_reste(self):
        self.ecrire("postulees.json", {"abc1234567": {"t": il_y_a(3), "titre": "ACME", "entreprise": "ACME", "ville": "38 Grenoble 8e", "lien": "https://x.fr/9"}})
        self.recherche()
        self.assertEqual(self.titres(), ["ACME"])

    def test_erreur_de_lecture_garde_l_annonce(self):
        o = offre(1, il_y_a(0))
        self.ecrire("offres-lues.json", {offres.ident_de(o): {"etat": "erreur", "raison": "HTTPError", "t": 0}})
        self.recherche(o)
        self.assertEqual(self.titres(), ["Offre 1"])

    def test_lien_mort_etiquette(self):
        o = offre(1, il_y_a(0))
        self.ecrire("liens.json", {o["lien"]: {"etat": "casse", "t": 0}})
        self.recherche(o)
        self.assertEqual(self.titres(), ["Offre 1"])
        self.assertEqual(offres.liste(brut=True)[0]["etiquettes"], ["expirée"])  # mission 12


class TestAnalyserFusionne(unittest.TestCase):
    """analyser_offres.exporter_site : la liste France Travail n'efface plus celle d'Adzuna dans la même zone."""

    @unittest.skipUnless((Path(__file__).resolve().parents[2] / 'routeur-ia' / 'outils' / 'analyse-offres').exists(), 'analyser_offres.py est dans le dépôt tri-offres-emploi')
    def test_deux_sources_meme_zone(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "site").mkdir(); (d / "site" / "candidatures.html").write_text("", encoding="utf-8")
        (d / "outils" / "analyse").mkdir(parents=True)
        src = Path(__file__).resolve().parents[2] / "routeur-ia" / "outils" / "analyse-offres" / "analyser_offres.py"
        spec = importlib.util.spec_from_file_location("analyser_test", src)
        a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(a)
        a.BASE = str(d / "outils" / "analyse")
        fiche = lambda n: {"titre": f"T{n}", "entreprise": "E", "lien": f"https://exemple.fr/{n}", "score": 80}  # noqa: E731
        a.exporter_site([fiche(1)], [], [], str(d / "adzuna" / "emplois_7.xlsx"))
        a.exporter_site([fiche(2)], [], [], str(d / "france travail" / "emplois_zone.xlsx"))
        t = (d / "site" / "offres-data.js").read_text(encoding="utf-8")
        z = json.loads(t[t.index("{"): t.rindex("}") + 1])["zones"]["Grenoble"]["retenues"]
        self.assertEqual(sorted(x["titre"] for x in z), ["T1", "T2"])
        self.assertTrue(all(x["vu"] for x in z))


if __name__ == "__main__":
    unittest.main()
