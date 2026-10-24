import sys, json, tempfile, unittest, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import jeu

class TestJeu(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        p = mock.patch.object(jeu, 'ETAT', Path(self.tmp.name) / 'jeu.json')
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(jeu, 'DONNEES', Path(self.tmp.name))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(jeu, 'demander', side_effect=RuntimeError("IA désactivée"))
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_niveau(self):
        self.assertEqual(jeu.niveau(0), 1)
        self.assertEqual(jeu.niveau(50), 2)
        self.assertEqual(jeu.niveau(200), 3)

    def test_gagner(self):
        e = jeu.lire()
        self.assertEqual(e["xp"], 0)
        jeu.gagner('exercice', '2026-10-18')
        e = jeu.lire()
        self.assertEqual(e["xp"], 30)
        jeu.gagner('exercice', '2026-10-18')
        e = jeu.lire()
        self.assertEqual(e["xp"], 30)
        with self.assertRaises(ValueError):
            jeu.gagner('triche')

    def test_serie(self):
        aujourdhui = datetime.date.today().isoformat()
        hier = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        avant_hier = (datetime.date.today() - datetime.timedelta(days=2)).isoformat()
        self.assertEqual(jeu.serie([aujourdhui, hier, avant_hier]), 3)
        self.assertEqual(jeu.serie([hier]), 1)
        self.assertEqual(jeu.serie([]), 0)

    def test_classer(self):
        taches = [
            {"id": "1", "agent": "alerte", "titre": "Alerte de sécurité"},
            {"id": "2", "agent": "veille", "titre": "Veille technologique"},
            {"id": "3", "agent": "mails", "titre": "Réponse à un recruteur"},
            {"id": "4", "agent": "offres", "titre": "Nouvelle offre"},
            {"id": "5", "agent": "exercice", "titre": "Exercice cyber"}
        ]
        resultat = jeu.classer(taches, fond=False)  # sans fil de fond : il écrirait dans le dossier temporaire après le test
        self.assertIn("alerte", [t["agent"] for t in resultat["maintenant"]])
        self.assertIn("mails", [t["agent"] for t in resultat["maintenant"]])
        self.assertIn("veille", [t["agent"] for t in resultat["attendre"]])
        self.assertLessEqual(len(resultat["maintenant"]), 3)

    def test_exercice_du_jour(self):
        exercice = jeu.exercice_du_jour()
        self.assertIn("titre", exercice)
        self.assertIn("duree", exercice)
        self.assertIn("fait", exercice)
        self.assertIn("id", exercice)

if __name__ == '__main__':
    unittest.main()
