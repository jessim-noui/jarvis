import sys
import unittest
import sqlite3
import hashlib
import tempfile
from pathlib import Path
from array import array
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoire_db import tokens, fait, faits, se_souvenir, rechercher, resume, maj_resume, contexte
from memoire_db import ollama_deja_allume as VRAI_DEJA_ALLUME

class TestMemoireDB(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_memoire.db"
        self.patch_db_path()

        self.conn = sqlite3.connect(self.db_path)
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS faits (cle TEXT PRIMARY KEY, texte TEXT, prive INT DEFAULT 0, maj TEXT);
            CREATE TABLE IF NOT EXISTS resumes (conversation TEXT PRIMARY KEY, resume TEXT, prive INT DEFAULT 0, maj TEXT);
            CREATE TABLE IF NOT EXISTS souvenirs (id INTEGER PRIMARY KEY, source TEXT, texte TEXT, prive INT DEFAULT 0,
                                                  empreinte TEXT UNIQUE, vecteur BLOB, t TEXT);
        """)
        self.conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def patch_db_path(self):
        self.patcher = patch('memoire_db.DB', self.db_path)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def fake_vecteur(self, texte, tache="search_document", delai=3):
        h = hashlib.sha1(texte.encode()).hexdigest()
        v = [float(int(h[i:i+8], 16) % 1000) / 1000 for i in range(0, 32, 4)]
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return array("f", (x / n for x in v))

    def fake_demander(self, agent, consigne, max_tokens=300, temperature=0.2):
        return ({'content': 'résumé test'}, 'ollama_chat/test-local')

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_fait_et_faits(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        mock_demander.side_effect = self.fake_demander

        fait("test", "texte test", prive=False)
        fait("test_prive", "texte privé", prive=True)

        self.assertEqual(faits(prive=False), [("test", "texte test")])
        self.assertEqual(faits(prive=True), [("test", "texte test"), ("test_prive", "texte privé")])

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_se_souvenir(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        mock_demander.side_effect = self.fake_demander

        self.assertFalse(se_souvenir("texte trop court", "source"))
        self.assertTrue(se_souvenir("texte suffisamment long pour être mémorisé", "source"))
        self.assertFalse(se_souvenir("texte suffisamment long pour être mémorisé", "source"))

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_rechercher(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        mock_demander.side_effect = self.fake_demander

        se_souvenir("texte test public, assez long pour compter", "public", prive=False)
        se_souvenir("texte test privé, assez long pour compter", "privé", prive=True)

        resultats = rechercher("question test", prive=False, seuil=-1)  # seuil -1 : tout ce qui est visible
        self.assertEqual([src for _, src, _ in resultats], ["public"])
        self.assertIn("privé", [src for _, src, _ in rechercher("question test", prive=True, seuil=-1)])

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_contexte(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        mock_demander.side_effect = self.fake_demander

        for i in range(30):
            fait(f"f{i}", "un fait volontairement long " * 20)
        se_souvenir("texte suffisamment long pour être mémorisé", "source")

        texte, stats = contexte("question test", budget=50)
        self.assertLessEqual(stats["tokens"], 50)

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_contexte_en_ligne_exclut_profil_et_souvenirs(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        fait("profil", "Profil confidentiel de démonstration")
        fait("style", "Réponses courtes")
        se_souvenir("La personne habite dans une ville confidentielle", "echange:test")
        texte, stats = contexte("qui est la personne ?", "test")
        self.assertNotIn("confidentiel", texte)
        self.assertEqual(texte, "")
        self.assertEqual(stats["souvenirs"], 0)

    @patch('memoire_db.demander')
    def test_resume_refuse_un_modele_distant(self, mock_demander):
        mock_demander.return_value = ({'content': 'résumé test'}, 'provider/model')
        with self.assertRaisesRegex(RuntimeError, "doit rester local"):
            maj_resume("conversation_test", "question", "réponse")
        mock_demander.assert_called_once()
        self.assertEqual(mock_demander.call_args.args[0], "jarvis-prive")

    @patch('memoire_db.vecteur')
    @patch('memoire_db.demander')
    def test_maj_resume(self, mock_demander, mock_vecteur):
        mock_vecteur.side_effect = self.fake_vecteur
        mock_demander.side_effect = self.fake_demander

        maj_resume("conversation_test", "question", "réponse")
        self.assertEqual(resume("conversation_test"), "résumé test")

    def test_tokens(self):
        self.assertEqual(tokens("abcd"*10), 11)

if __name__ == "__main__":
    unittest.main()


class TestMemoireRapideM16(unittest.TestCase):
    """Mission 16 : la mémoire n'allume jamais Ollama et ne fait jamais attendre l’utilisateur."""
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        p = patch('memoire_db.DB', Path(self.temp_dir.name) / "m.db")
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(self.temp_dir.cleanup)
        e = patch('memoire_db.ollama_deja_allume', return_value=False)  # le vrai Ollama peut tourner pendant les tests
        e.start()
        self.addCleanup(e.stop)

    def test_ollama_eteint_memoire_moins_d_une_seconde_et_rien_demarre(self):
        import time, memoire_db, presence
        se_souvenir("L’utilisateur cherche un poste de technicien support à Grenoble", "test")
        with patch('commun.ollama_autorise', return_value=True), patch.object(presence, 'demarrer_ollama') as dem, \
             patch('memoire_db.OLLAMA', "http://127.0.0.1:9"), patch('memoire_db.ollama_deja_allume', VRAI_DEJA_ALLUME):  # port fermé = Ollama éteint
            debut = time.time()
            texte, stats = contexte("technicien support Grenoble ?", "test-m16", prive=True)
            self.assertLess(time.time() - debut, 1)
            dem.assert_not_called()
        self.assertIn("technicien support", texte)  # trouvé par les mots-clés

    def test_souvenir_garde_sans_vecteur_puis_complete(self):
        import memoire_db
        self.assertTrue(se_souvenir("Un souvenir gardé même quand Ollama est éteint", "test"))
        with memoire_db.connexion() as c:
            self.assertIsNone(c.execute("SELECT vecteur FROM souvenirs").fetchone()[0])
        with patch('memoire_db.vecteur', return_value=array("f", [1.0, 0.0])):
            self.assertEqual(memoire_db.completer_vecteurs(), 1)
        with memoire_db.connexion() as c:
            self.assertIsNotNone(c.execute("SELECT vecteur FROM souvenirs").fetchone()[0])

    def test_resume_reste_local_pour_les_conversations_privees(self):
        with patch('memoire_db.demander', return_value=({'content': 'r'}, 'ollama_chat/test-local')) as d:
            maj_resume("c", "q", "r")
            self.assertEqual(d.call_args[0][0], "jarvis-prive")
            maj_resume("c", "q", "r", prive=True)
            self.assertEqual(d.call_args[0][0], "jarvis-prive")
