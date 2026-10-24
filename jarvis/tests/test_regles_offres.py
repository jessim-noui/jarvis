import sys, unittest, tempfile, pathlib, json
from unittest.mock import patch

sys.path.append(str(pathlib.Path(__file__).parent.parent))

import regles_offres

class TestReglesOffres(unittest.TestCase):
    def test_candidates_mot(self):
        entrees = [
            {"titre": "Technicien télécom H/F", "raison": "pas mon domaine"},
            {"titre": "Technicien Télécom fibre", "raison": "pas mon domaine"},
            {"titre": "Monteur télécom", "raison": "pas mon domaine"},
        ]
        regles = regles_offres.candidates(entrees)
        self.assertEqual(len(regles), 1)
        self.assertEqual(regles[0][:3], ("mot", "telecom", "les postes « telecom » ne t'intéressent pas"))
        self.assertEqual(regles[0][3], 3)

        entrees = [
            {"titre": "Technicien télécom H/F", "raison": "pas mon domaine"},
            {"titre": "Technicien Télécom fibre", "raison": "pas mon domaine"},
        ]
        regles = regles_offres.candidates(entrees)
        self.assertEqual(len(regles), 0)

        entrees = [
            {"titre": "Technicien support", "raison": "pas mon domaine"},
        ]
        regles = regles_offres.candidates(entrees)
        self.assertEqual(len(regles), 0)

    def test_candidates_entreprise(self):
        entrees = [
            {"entreprise": "ACME", "raison": "entreprise"},
            {"entreprise": "ACME", "raison": "entreprise"},
        ]
        regles = regles_offres.candidates(entrees)
        self.assertEqual(len(regles), 1)
        self.assertEqual(regles[0][:3], ("entreprise", "ACME", "les offres de ACME ne t'intéressent pas"))
        self.assertEqual(regles[0][3], 2)

    def test_candidates_contrat(self):
        entrees = [
            {"contrat": "Intérim", "raison": "contrat"},
            {"contrat": "Intérim", "raison": "contrat"},
            {"contrat": "Intérim", "raison": "contrat"},
        ]
        regles = regles_offres.candidates(entrees)
        self.assertEqual(len(regles), 1)
        self.assertEqual(regles[0][:3], ("contrat", "intérim", "les offres en intérim ne t'intéressent pas"))
        self.assertEqual(regles[0][3], 3)

    def test_regle_pour(self):
        regles = {
            "regle-offres:mot:telecom": {
                "type": "mot",
                "valeur": "telecom",
                "texte": "les postes « telecom » ne t'intéressent pas"
            }
        }
        offre = {"titre": "Technicien TÉLÉCOM"}
        self.assertEqual(regles_offres.regle_pour(offre, regles), "les postes « telecom » ne t'intéressent pas")

        offre = {"titre": "Technicien support"}
        self.assertEqual(regles_offres.regle_pour(offre, regles), "")

    def test_repondu(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            regles_path = pathlib.Path(tmpdir) / "offres-regles.json"
            with patch.object(regles_offres, "REGLES", regles_path):
                d = {
                    "choix": "oui",
                    "sujet": "regle-offres:mot:telecom",
                    "questions": ["J'ai compris que les postes « telecom » ne t'intéressent pas. Je les mets de côté ?"]
                }
                regles_offres.repondu(d)
                self.assertTrue(regles_path.exists())
                with open(regles_path, "r", encoding="utf-8") as f:
                    regles = json.load(f)
                self.assertIn("regle-offres:mot:telecom", regles)
                self.assertEqual(regles["regle-offres:mot:telecom"]["type"], "mot")
                self.assertEqual(regles["regle-offres:mot:telecom"]["valeur"], "telecom")
                self.assertEqual(regles["regle-offres:mot:telecom"]["texte"], "les postes « telecom » ne t'intéressent pas")

                d = {
                    "choix": "non",
                    "sujet": "regle-offres:mot:telecom",
                    "questions": ["J'ai compris que les postes « telecom » ne t'intéressent pas. Je les mets de côté ?"]
                }
                regles_path.unlink()  # « non » sur une règle neuve : rien n'est écrit
                regles_offres.repondu(d)
                self.assertFalse(regles_path.exists())

    def test_trois_raisons_proposent_une_regle_dans_decisions(self):  # écrit par Claude (mission 12)
        import lecture_offres
        from suite import directeur
        with tempfile.TemporaryDirectory() as d:
            d = pathlib.Path(d)
            (d / "ppm.json").write_text(json.dumps({str(i): {"titre": t, "entreprise": "X"} for i, t in enumerate(
                ["Technicien télécom H/F", "Monteur Télécom", "Technicien télécom fibre"])}), encoding="utf-8")
            with patch.object(lecture_offres, "PAS_POUR_MOI", d / "ppm.json"), patch.object(directeur, "DECISIONS", d / "dec.json"),                     patch.object(regles_offres, "REGLES", d / "regles.json"):
                self.assertIsNone(regles_offres.noter_raison("0", "pas mon domaine"))
                regles_offres.noter_raison("1", "pas mon domaine")
                x = regles_offres.noter_raison("2", "pas mon domaine")
                self.assertEqual(x["sujet"], "regle-offres:mot:telecom")
                self.assertIn("Je les mets de côté ?", x["questions"][0])
                self.assertFalse((d / "regles.json").exists())  # rien d'appliqué avant le oui de l’utilisateur
                self.assertIsNone(regles_offres.proposer())  # jamais reproposée

    def test_noter_raison_inconnue(self):
        with self.assertRaises(ValueError):
            regles_offres.noter_raison("ident", "inconnue")

if __name__ == "__main__":
    unittest.main()
