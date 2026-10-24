"""Mission 10 — les trois niveaux."""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from suite import politique

class TestNiveaux(unittest.TestCase):
    def test_seul(self):
        tests = [
            ("mets le bouton Envoyer en vert", ("seul", "")),
            ("rends l'agent Emploi plus court dans ses réponses", ("seul", "")),
            ("supprime le bouton Plus tard de la page Accueil", ("seul", "")),
            (r"regarde cette vidéo : https://youtu.be/abc", ("seul", ""))
        ]
        for texte, attendu in tests:
            with self.subTest(texte=texte):
                self.assertEqual(politique.niveau(texte), attendu)

    def test_demande(self):
        tests = [
            ("installe VLC", ("demande", "installer")),
            ("supprime mes fichiers de test", ("demande", "supprimer")),
            (r"modifie C:\Users\x\a.txt", ("demande", "hors-projet"))
        ]
        for texte, attendu in tests:
            with self.subTest(texte=texte):
                self.assertEqual(politique.niveau(texte), attendu)

    def test_jamais(self):
        tests = [
            ("envoie un mail à Paul", ("jamais", "envoyer")),
            ("paie l'abonnement Netflix", ("jamais", "payer")),
            (r"ouvre C:\SECRETS\cles.env", ("jamais", "secrets")),
            ("range mes photos", ("jamais", "photos")),
            ("postule chez Orange", ("jamais", "postuler")),
            ("prépare la lettre puis envoie-la", ("jamais", "envoyer")),
        ]
        for texte, attendu in tests:
            with self.subTest(texte=texte):
                self.assertEqual(politique.niveau(texte), attendu)

if __name__ == "__main__":
    unittest.main()
