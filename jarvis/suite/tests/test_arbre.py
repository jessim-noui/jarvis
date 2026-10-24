"""Mission 12 : l'arbre céleste n'allume une branche que pour un vrai travail en cours (journal), rien de simulé."""
import json, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

from suite import arbre


class TestArbre(unittest.TestCase):
    def lancer(self, journal, usage):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "j.json").write_text(json.dumps(journal), encoding="utf-8")
            (d / "usage.json").write_text(json.dumps(usage), encoding="utf-8")
            with patch.object(arbre, "JOURNAL", d / "j.json"), patch.object(arbre, "DONNEES", d):
                return {a["id"]: a for a in arbre.arbre()["agents"]}

    def test_travail_en_cours_seulement_avec_un_debut_ouvert(self):
        t = time.strftime("%Y-%m-%dT%H:%M:%S")
        a = self.lancer([{"id": "1", "agent": "emploi", "action": "lecture des offres", "etat": "debut", "t": t, "modele": ""}], [])
        self.assertEqual(a["emploi"]["etat"], "travail")
        self.assertEqual(a["emploi"]["taches"][0][2], "en cours")
        self.assertTrue(a["emploi"]["de"].startswith(("Jarvis", "Directeur")))
        self.assertEqual(a["code"]["etat"], "repos")
        fini = self.lancer([{"id": "1", "agent": "emploi", "action": "lecture", "etat": "debut", "t": t},
                            {"id": "1", "agent": "emploi", "action": "lecture", "etat": "fin", "statut": "ok", "resume": "3 offres", "t": t}], [])
        self.assertEqual(fini["emploi"]["etat"], "repos")

    def test_ia_comptees_depuis_usage(self):
        t = time.strftime("%Y-%m-%dT%H:%M:%S")
        u = [{"t": t, "profil": "jarvis-code", "modele": "mistral/mistral-code-latest", "tokens_entree": 900, "tokens_sortie": 100, "duree": 2, "erreur": ""},
             {"t": t, "profil": "jarvis-code", "modele": "mistral/mistral-code-latest", "duree": 4, "erreur": "x"}]
        a = self.lancer([], u)["code"]
        self.assertEqual(a["ias"], [["mistral-code-latest", 2, "50 %"]])
        self.assertEqual(dict((l, v) for l, v in a["stats"])["erreurs"], "1")


if __name__ == "__main__":
    unittest.main()
