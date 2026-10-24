import sys, tempfile, unittest, datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import alertes, securite

class TestAlertesEtat(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)
        self.patches = [
            mock.patch.object(alertes, 'LUES', Path(self.d.name) / 'lues.json'),
            mock.patch.object(alertes, 'DONNEES', Path(self.d.name)),
            mock.patch.object(securite, 'ALERTES', Path(self.d.name) / 'alertes.json')
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_probleme_regle_disparait(self):
        problemes = [{'id': 'p:test', 'titre': 'Test en panne', 'texte': 'ça ne marche pas'}]
        lignes = alertes.liste(problemes)
        self.assertEqual(len(lignes), 1)
        self.assertEqual(lignes[0]['etat'], 'ouvert')
        self.assertFalse(lignes[0]['lu'])
        self.assertTrue(alertes.probleme_ouvert('p:test'))
        self.assertEqual(alertes.compteurs(lignes)['non_lues'], 1)

        alertes.changer(lignes[0]['id'], 'regle')
        lignes = alertes.liste(problemes)
        self.assertEqual(lignes[0]['etat'], 'regle')
        self.assertTrue(lignes[0]['lu'])
        self.assertFalse(alertes.probleme_ouvert('p:test'))
        self.assertEqual(alertes.compteurs(lignes)['non_lues'], 0)
        self.assertEqual(alertes.compteurs(lignes)['problemes'], 0)

        lignes = alertes.liste(problemes)
        self.assertEqual(lignes[0]['etat'], 'regle')

    def test_marquer_lue(self):
        problemes = [{'id': 'p:test', 'titre': 'Test en panne', 'texte': 'ça ne marche pas'}]
        lignes = alertes.liste(problemes)
        alertes.marquer_lue(lignes[0]['id'])
        lignes = alertes.liste(problemes)
        self.assertEqual(lignes[0]['etat'], 'ignore')

    def test_ancien_format(self):
        problemes = [{'id': 'p:test', 'titre': 'Test en panne', 'texte': 'ça ne marche pas'}]
        lignes = alertes.liste(problemes)
        id = alertes.ident('p', 'p:test', datetime.date.today().isoformat())
        with open(Path(self.d.name) / 'lues.json', 'w') as f:
            f.write(f'{{"{id}": "2026-10-18T10:00:00"}}')
        lignes = alertes.liste(problemes)
        self.assertEqual(lignes[0]['etat'], 'ignore')

    def test_reponse_jarvis_gardée(self):
        problemes = [{'id': 'p:test', 'titre': 'Test en panne', 'texte': 'ça ne marche pas'}]
        lignes = alertes.liste(problemes)
        id = lignes[0]['id']
        alertes.changer(id, 'ouvert', cause='c', correction='x')
        lignes = alertes.liste(problemes)
        self.assertEqual(lignes[0]['reponse_jarvis'], {'cause': 'c', 'correction': 'x'})
        self.assertEqual(lignes[0]['etat'], 'ouvert')

if __name__ == '__main__':
    unittest.main()
