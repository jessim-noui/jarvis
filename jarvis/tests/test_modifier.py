"""Mission 8 : modifier une page depuis le chat (suite/modifier.py) — reconnaissance, remplacements, classement, contrôle de
page, une seule exécution par demande. (Brouillon mistral-code-latest via deleguer.py, 2 points corrigés par Claude.)"""
import sys, unittest, tempfile, shutil
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import modifier

class TestModifier(unittest.TestCase):
    def setUp(self):
        self.dossier_temporaire = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dossier_temporaire, True)
        p = mock.patch.object(modifier, 'generateur', return_value='jarvis-code')  # mission 8 : générateur gratuit, pages seulement
        p.start()
        self.addCleanup(p.stop)

    def test_analyser_claude(self):  # mission 10 : avec Claude Code, tout le dossier du projet ; il trouve lui-même le fichier
        with mock.patch.object(modifier, 'generateur', return_value='claude'):
            self.assertEqual(modifier.analyser('Mets le bouton Envoyer en vert'), {'fichier': None})
            self.assertEqual(modifier.analyser("Rends l'agent Emploi plus court dans ses réponses"), {'fichier': None})
            self.assertEqual(modifier.analyser('Modifie la page Accueil : réduis le titre'), {'fichier': 'routeur-ia/site/accueil.html'})
            self.assertIsNone(modifier.analyser('Écris une lettre de motivation pour Orange'))  # rédaction, pas une modification
            self.assertIsNone(modifier.analyser('Comment changer le bouton ?'))
            self.assertIn('refus', modifier.analyser('Modifie C:\\SECRETS\\cles.env'))
            self.assertIn('refus', modifier.analyser('Modifie offres-data.js'))
            self.assertIsNone(modifier.lancer('Envoie un mail à Paul'))  # « jamais » : passe au chef, qui prépare un brouillon

    def test_controler(self):
        self.assertEqual(modifier.controler('jarvis/x.py', 'x = 1\n'), [])
        self.assertTrue(modifier.controler('jarvis/x.py', 'x = \n'))
        self.assertTrue(modifier.controler('jarvis/suite/reglages.json', '{"a": }'))
        self.assertTrue(modifier.controler('routeur-ia/routeur/config.yaml', 'a: [1, 2'))
        self.assertTrue(modifier.controler('.claude/skills/x/SKILL.md', 'pas de frontmatter'))
        self.assertEqual(modifier.controler('.claude/skills/x/SKILL.md', '---\nname: x\n---\n'), [])

    def test_chemin_ok(self):
        self.assertTrue(modifier._chemin_ok('jarvis/jarvis.py'))
        for f in ('../hors.py', 'jarvis/donnees/offres.json', '.git/config', 'routeur-ia/site/offres-data.js', 'C:/SECRETS/cles.env'):
            self.assertFalse(modifier._chemin_ok(f), f)

    def test_analyser(self):
        self.assertEqual(modifier.analyser('Modifie la page Accueil : réduis le titre'), {'fichier': 'routeur-ia/site/accueil.html'})
        self.assertIsNone(modifier.analyser('Comment modifier la page Accueil ?'))
        self.assertIn('ambigu', modifier.analyser('Change le bouton'))
        self.assertIn('refus', modifier.analyser('Modifie C:\\SECRETS\\cles.env'))
        self.assertIn('refus', modifier.analyser('Mets ma photo sur la page Moi'))
        self.assertEqual(modifier.analyser('Modifie serveur.py'), {'refus': 'pour l\'instant je ne modifie que les pages du site, pas le code de Jarvis (dis-le à Claude Code)'})
        self.assertEqual(modifier.analyser('Modifie offres-data.js'), {'refus': 'ce fichier n\'est pas une page du site que je peux modifier'})

    def test_appliquer(self):
        texte = 'a\nb\nc'
        remplacements = [{'chercher': 'b', 'remplacer': 'B'}]
        self.assertEqual(modifier.appliquer(texte, remplacements), ('a\nB\nc', ''))

        texte = 'a\r\nb\r\nc'
        remplacements = [{'chercher': 'b', 'remplacer': 'B'}]
        self.assertEqual(modifier.appliquer(texte, remplacements), ('a\r\nB\r\nc', ''))

        texte = 'a\nb\nc'
        remplacements = [{'chercher': 'd', 'remplacer': 'D'}]
        self.assertEqual(modifier.appliquer(texte, remplacements), ('a\nb\nc', 'un passage à remplacer n\'existe pas tel quel (ou plusieurs fois) dans la page'))

        texte = 'a\nb\nb\nc'
        remplacements = [{'chercher': 'b', 'remplacer': 'B'}]
        self.assertEqual(modifier.appliquer(texte, remplacements), ('a\nb\nb\nc', 'un passage à remplacer n\'existe pas tel quel (ou plusieurs fois) dans la page'))

    def test_classer(self):
        diff = 'diff --git a/routeur-ia/site/accueil.html b/routeur-ia/site/accueil.html\n--- a/routeur-ia/site/accueil.html\n+++ b/routeur-ia/site/accueil.html\n@@ -1 +1 @@\n-<h1>a</h1>\n+<h1>b</h1>\n'
        self.assertEqual(modifier.classer(diff)['niveau'], 'auto')

        diff = 'diff --git a/routeur-ia/site/accueil.html b/routeur-ia/site/accueil.html\n--- a/routeur-ia/site/accueil.html\n+++ b/routeur-ia/site/accueil.html\n@@ -1 +1 @@\n-<h1>a</h1>\n+<h1>b</h1>\n+<script src="https://x.fr/a.js"></script>\n'
        self.assertEqual(modifier.classer(diff)['niveau'], 'decision')

        diff = 'diff --git a/jarvis/donnees/x.json b/jarvis/donnees/x.json\n--- a/jarvis/donnees/x.json\n+++ b/jarvis/donnees/x.json\n@@ -1 +1 @@\n-{"a": 1}\n+{"a": 2}\n'
        self.assertEqual(modifier.classer(diff)['niveau'], 'interdit')

        diff = 'diff --git a/jarvis/securite.py b/jarvis/securite.py\n--- a/jarvis/securite.py\n+++ b/jarvis/securite.py\n@@ -1 +1 @@\n-print("a")\n+print("b")\n'
        self.assertEqual(modifier.classer(diff)['niveau'], 'sensible')

    def test_controler_page(self):
        if not shutil.which('node'):
            self.skipTest('node non installé')

        texte = '<script>let a = ;</script>'
        self.assertTrue(modifier.controler_page('test.html', texte))

        texte = '<script>let a = 1;</script>'
        self.assertFalse(modifier.controler_page('test.html', texte))

    @mock.patch.object(modifier.threading, 'Thread')
    @mock.patch.object(modifier, 'journaliser')
    def test_lancer(self, mock_journaliser, mock_thread):
        p = mock.patch.object(modifier, 'HISTO', Path(self.dossier_temporaire) / 'h.json')
        p.start()
        self.addCleanup(p.stop)
        self.assertIsNone(modifier.lancer('Comment ça va ?'))

        reponse = modifier.lancer('Change le bouton')
        self.assertTrue(reponse['reponse'].startswith('Je ne modifie rien'))

        reponse = modifier.lancer('Modifie la page Accueil : titre plus petit')
        self.assertIn('modif', reponse)
        premier = reponse['modif']['id']
        mock_thread.assert_called_once()

        modifier._en_cours.clear()
        reponse = modifier.lancer('Modifie la page Accueil : titre plus petit')
        self.assertIn('déjà prise en charge', reponse['reponse'])
        self.assertEqual(reponse['modif']['id'], premier)
        mock_thread.assert_called_once()  # pas relancée

        modifier._en_cours.clear()

if __name__ == '__main__':
    unittest.main()
