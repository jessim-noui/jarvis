"""Mission 12 : doublons fusionnés, déjà postulé jamais reproposé, expirée hors de « À regarder »."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import offres  # noqa: E402

FT = "https://candidat.francetravail.fr/offres/recherche/detail/"


def offre(i, titre, entreprise, lieu, lien, etat="pour_toi", **k):
    return {"id": i, "titre": titre, "entreprise": entreprise, "lieu": lieu, "lien": lien, "etat": etat, "lien_etat": "ok", "postule": "", **k}


def faux_infos(lieu, zone=""):
    commune = {"38 - Grenoble 1er Arrondissement": "Grenoble 1er", "Grenoble 1er, Grenoble": "Grenoble 1er", "13 - Marseille": "Marseille"}.get(lieu, "")
    return {"region": "Sud" if "Marseille" in (lieu or "") else "Grenoble", "commune": commune, "trajet": {}, "loin": False}


@patch.object(offres.lieux, "infos", faux_infos)
class TestM12(unittest.TestCase):
    def test_doublon_deux_sources_une_carte(self):
        a = offre("a", "Technicien Helpdesk N1 (H/F)", "LTd", "38 - Grenoble 1er Arrondissement", FT + "1")
        b = offre("b", "Technicien helpdesk N1 F/H", "LTd", "Grenoble 1er, Grenoble", "https://www.adzuna.fr/land/ad/2")
        r = offres.fusionner([a, b])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["sources"], ["Adzuna", "France Travail"])
        self.assertEqual(r[0]["doublons"], ["b"])

    def test_meme_lien_fusionne(self):
        r = offres.fusionner([offre("a", "Support", "", "x", FT + "9"), offre("b", "Support IT", "", "y", FT + "9")])
        self.assertEqual(len(r), 1)

    def test_meme_titre_autre_ville_pas_fusionne(self):
        a = offre("a", "Technicien Helpdesk N1 (H/F)", "LTd", "38 - Grenoble 1er Arrondissement", FT + "1")
        b = offre("b", "Technicien Helpdesk N1 (H/F)", "LTd", "13 - Marseille", FT + "2")
        self.assertEqual(len(offres.fusionner([a, b])), 2)

    def test_entreprise_inconnue_pas_fusionne(self):
        a = offre("a", "Technicien support", "non precise", "38 - Grenoble 1er Arrondissement", FT + "1")
        b = offre("b", "Technicien support", "non precise", "38 - Grenoble 1er Arrondissement", FT + "2")
        self.assertEqual(len(offres.fusionner([a, b])), 2)

    def test_deja_postule_par_id_lien_ou_proche(self):
        post = {"p1": {"t": "2026-10-19T12:38", "titre": "Technicien Helpdesk N1 (H/F)", "entreprise": "LTd",
                       "ville": "38 - Grenoble 1er Arrondissement", "lien": FT + "1"}}
        self.assertEqual(offres.deja_postule(offre("p1", "x", "y", "z", ""), post), "2026-10-19T12:38")
        self.assertEqual(offres.deja_postule(offre("q", "autre", "autre", "z", FT + "1"), post), "2026-10-19T12:38")
        adz = offre("r", "Technicien helpdesk N1 F/H", "LTd", "Grenoble 1er, Grenoble", "https://www.adzuna.fr/land/ad/2")
        self.assertEqual(offres.deja_postule(adz, post), "2026-10-19T12:38")
        self.assertEqual(offres.deja_postule(offre("s", "Développeur web", "LTd", "Grenoble 1er, Grenoble", FT + "5"), post), "")

    def test_deux_sources_apres_candidature_jamais_reproposee(self):
        post = {"p1": {"t": "2026-10-19T12:38", "titre": "Technicien Helpdesk N1 (H/F)", "entreprise": "LTd",
                       "ville": "38 - Grenoble 1er Arrondissement", "lien": FT + "1"}}
        a = offre("a", "Technicien Helpdesk N1 (H/F)", "LTd", "38 - Grenoble 1er Arrondissement", FT + "7")
        b = offre("b", "Technicien helpdesk N1 F/H", "LTd", "Grenoble 1er, Grenoble", "https://www.adzuna.fr/land/ad/8")
        for x in (a, b):
            x["postule"] = offres.deja_postule(x, post)
        r = offres.fusionner([a, b])
        self.assertEqual(len(r), 1)
        self.assertTrue(r[0]["postule"])
        self.assertEqual(offres.pour_toi(r), [])

    def test_page_plus_disponible(self):
        self.assertTrue(offres.PLUS_DISPO.search("Désolé, cette offre n'est plus disponible"))
        self.assertTrue(offres.PLUS_DISPO.search("This job is no longer available"))
        self.assertFalse(offres.PLUS_DISPO.search("Technicien support, CDI, disponible rapidement"))

    def test_expiree_pas_pour_toi(self):
        x = offre("a", "Support", "LTd", "z", FT + "1", region="Grenoble")
        x["lien_etat"] = "casse"
        self.assertEqual(offres.pour_toi([x]), [])


if __name__ == "__main__":
    unittest.main()
