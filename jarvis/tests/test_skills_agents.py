import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import skills_agents as sa

class TestSkillsAgents(unittest.TestCase):
    """Mission 10 — skills utilisés par les agents."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        # Créer les fichiers SKILL.md
        skills_dir = Path(self.temp_dir.name) / "skills"
        skills_dir.mkdir()

        court_dir = skills_dir / "court"
        court_dir.mkdir()
        (court_dir / "SKILL.md").write_text("---\nname: court\ndescription: Un skill court\n---\nRègle courte.", encoding="utf-8")

        long_dir = skills_dir / "long"
        long_dir.mkdir()
        (long_dir / "SKILL.md").write_text("---\nname: long\ndescription: Un skill long\n---\n" + "Paragraphe.\n\n" * 400, encoding="utf-8")

        # Créer la table JSON
        table_path = Path(self.temp_dir.name) / "skills_agents.json"
        table_path.write_text(json.dumps({"code": ["court"], "tous": ["long"]}), encoding="utf-8")

        # Patcher les variables
        self.patches = [
            mock.patch.object(sa, 'DOSSIER', skills_dir),
            mock.patch.object(sa, 'TABLE', table_path),
            mock.patch.object(sa, 'RESUMES', Path(self.temp_dir.name) / "skills-resumes.json"),
            mock.patch.object(sa, 'USAGE', Path(self.temp_dir.name) / "skills-usage.json")
        ]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_pour_code(self):
        """Test pour l'agent 'code'."""
        with mock.patch('commun.demander', side_effect=OSError):  # mission 11 : sans dépendre du vrai routeur
            texte = sa.pour('code')
            self.assertIn("Règle courte.", texte)
            self.assertIn("Skill « long »", texte)
            self.assertLessEqual(len(texte), sa.MAX_TOTAL + 0)
            self.assertLessEqual(len(sa._court('long', sa._corps('long'))), sa.MAX_SKILL)  # coupé à la fin d'un paragraphe

    def test_pour_mails(self):
        """Test pour l'agent 'mails'."""
        texte = sa.pour('mails')
        self.assertIn("Skill « long »", texte)
        self.assertNotIn("Règle courte.", texte)

    def test_usage(self):
        """Test de la dernière utilisation."""
        sa.pour('code')
        usage = json.loads(sa.USAGE.read_text())
        self.assertIn("court", usage)
        self.assertEqual(usage["court"]["agent"], "code")

    def test_regler(self):
        """Test de la fonction regler."""
        sa.regler('court', 'emploi', True)
        self.assertIn('court', sa.table()['emploi'])

        sa.regler('court', 'emploi', False)
        self.assertNotIn('court', sa.table()['emploi'])

    def test_regler_inconnu(self):
        """Test de la fonction regler avec des valeurs inconnues."""
        with self.assertRaises(ValueError):
            sa.regler('inconnu', 'code', True)
        with self.assertRaises(ValueError):
            sa.regler('court', 'pirate', True)

    def test_lire(self):
        """Test de la fonction lire."""
        texte = sa.lire('court')['texte']
        self.assertTrue(texte.startswith('---'))

        with self.assertRaises(ValueError):
            sa.lire('../x')

    def test_liste(self):
        """Test de la fonction liste."""
        liste = sa.liste()
        self.assertEqual(len(liste['skills']), 2)
        self.assertEqual(liste['skills'][0]['agents'], ['code'])

if __name__ == '__main__':
    unittest.main()
