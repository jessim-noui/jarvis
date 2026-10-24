"""Mission 8 : la pastille des offres du jeu = les offres « pour toi » pas encore ouvertes, hors candidatures envoyées.
Elle baisse quand une offre est ouverte (vue) ou quand l’utilisateur a postulé, pas quand il ouvre seulement le jeu."""
import sys, unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import serveur  # noqa: E402


def offre(i, **k):
    return {"id": i, "titre": f"Offre {i}", "contrat": "CDI", "experience": "débutant", "ville": "Grenoble", "etat": "pour_toi",
            "lien_etat": "ok", "nouvelle": True, "postule": "", **k}


class TestPastilleOffres(unittest.TestCase):
    def n_offres(self, liste):
        with mock.patch.object(serveur, "probleme_items", return_value=[]), mock.patch.object(serveur, "ameliorations", return_value=[]), \
                mock.patch.object(serveur, "refus_semaine", return_value=0), mock.patch.object(serveur.actions, "en_attente", return_value={}):
            vil = serveur.village([], {"offres": liste}, [], {"fait": True, "duree": "5 min"}, set())
        return next(z for z in vil if z["id"] == "offres")["n"]

    def test_vraies_choses_a_traiter(self):
        self.assertEqual(self.n_offres([offre("a"), offre("b"), offre("c")]), 3)

    def test_ouverte_ou_postulee_ne_compte_plus(self):
        self.assertEqual(self.n_offres([offre("a", nouvelle=False), offre("b", postule="2026-10-19T12:38"), offre("c")]), 1)

    def test_rien_a_traiter_pas_de_pastille(self):
        self.assertEqual(self.n_offres([offre("a", nouvelle=False), offre("b", etat="a_verifier")]), 0)


if __name__ == "__main__":
    unittest.main()
