import sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suite import conseil

class TestConseil(unittest.TestCase):
    """Mission 10 — la Table du Conseil."""

    def setUp(self):
        self.dossier = tempfile.TemporaryDirectory()
        self.addCleanup(self.dossier.cleanup)
        self.p = mock.patch.object(conseil, 'ROLES_FICHIER', Path(self.dossier.name) / 'roles.json')
        self.p.start()
        self.addCleanup(self.p.stop)

    def test_roles(self):
        """roles() renvoie 5 rôles par défaut avec les clés nom, profil, but ; appels_prevus() == 11."""
        r = conseil.roles()
        self.assertEqual(len(r), 5)
        for role in r:
            self.assertIn('nom', role)
            self.assertIn('profil', role)
            self.assertIn('but', role)
        self.assertEqual(conseil.appels_prevus(), 11)

    def test_changer_role(self):
        """changer_role(0, 'Avocat du diable', 'Cherche les failles.', 'jarvis-rapide') puis roles()[0] == {'nom': 'Avocat du diable', 'profil': 'jarvis-rapide', 'but': 'Cherche les failles.'} et les 4 autres inchangés."""
        r = conseil.changer_role(0, 'Avocat du diable', 'Cherche les failles.', 'jarvis-rapide')
        self.assertEqual(r[0], {'nom': 'Avocat du diable', 'profil': 'jarvis-rapide', 'but': 'Cherche les failles.'})
        self.assertEqual(len(r), 5)
        self.assertEqual(r[1:], [{'nom': n, 'profil': p, 'but': b} for n, p, b in conseil.ROLES[1:]])

    def test_changer_role_invalide(self):
        """changer_role lève ValueError pour : n=9, profil 'jarvis-prive', nom vide."""
        with self.assertRaises(ValueError):
            conseil.changer_role(9, 'Nom', 'But', 'jarvis')
        with self.assertRaises(ValueError):
            conseil.changer_role(0, 'Nom', 'But', 'jarvis-prive')
        with self.assertRaises(ValueError):
            conseil.changer_role(0, '', 'But', 'jarvis')

    def test_depuis_chat(self):
        """depuis_chat('Bonjour') est None ; avec mock.patch.object(conseil, 'lancer', return_value=True) as l : r = depuis_chat('Demande au Conseil : faut-il apprendre Rust ?') → l.assert_called_once_with('faut-il apprendre Rust ?') et r['lien'] == 'conseil.html' ; depuis_chat('pose la question au conseil, quel VPN choisir ?') appelle lancer avec 'quel VPN choisir ?'."""
        self.assertIsNone(conseil.depuis_chat('Bonjour'))
        with mock.patch.object(conseil, 'lancer', return_value=True) as l:
            r = conseil.depuis_chat('Demande au Conseil : faut-il apprendre Rust ?')
            l.assert_called_once_with('faut-il apprendre Rust ?')
            self.assertEqual(r['lien'], 'conseil.html')
        with mock.patch.object(conseil, 'lancer') as l:
            conseil.depuis_chat('pose la question au conseil, quel VPN choisir ?')
            l.assert_called_once_with('quel VPN choisir ?')

    def test_lancer_invalide(self):
        """lancer('court') lève ValueError (moins de 8 caractères)."""
        with self.assertRaises(ValueError):
            conseil.lancer('court')

if __name__ == '__main__':
    unittest.main()
