"""Mission 13 : anti-boucle du serveur (au plus 3 redémarrages en 10 min)."""
import sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from outils import redemarrer_serveur as rs


class TestAntiBoucle(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        p = mock.patch.object(rs, "RELANCES", Path(self.dossier.name) / "relances_serveur.json")
        p.start(); self.addCleanup(p.stop)

    def test_trois_relances_puis_plus_rien(self):
        self.assertEqual([rs.relance_permise(1000 + i) for i in range(4)], [True, True, True, False])

    def test_permis_de_nouveau_apres_10_min(self):
        for i in range(3):
            rs.relance_permise(1000 + i)
        self.assertTrue(rs.relance_permise(1000 + 601))

    def test_bloque_ne_touche_pas_au_serveur(self):
        for i in range(3):
            rs.relance_permise()
        with mock.patch.object(rs, "arreter") as arreter, mock.patch.object(rs, "demarrer") as demarrer, \
                mock.patch.object(rs.time, "sleep"), mock.patch("securite.alerter") as alerter, \
                mock.patch("suite.modifier._histo", return_value={}), mock.patch("suite.modifier._maj") as maj:
            rs.main("d-1", "abc")
        arreter.assert_not_called(); demarrer.assert_not_called(); alerter.assert_called_once()
        self.assertIn("3 en 10 min", maj.call_args.kwargs["resume"])


if __name__ == "__main__":
    unittest.main()
