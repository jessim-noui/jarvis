"""Découvertes : une trouvaille par source si possible, 5 au plus, et les bonnes non choisies ne sont pas oubliées."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents"))
import veille  # noqa: E402

C = [{"source": s, "titre": f"t{i}", "lien": f"l{i}", "desc": ""} for i, s in enumerate(
    ["GitHub", "GitHub", "GitHub", "Web", "YouTube · Micode", "CERT-FR avis", "GitHub", "Web"])]


class TestDecouvertes(unittest.TestCase):
    def test_melanger_alterne_les_sources(self):
        groupes = [veille.groupe(c["source"]) for c in veille.melanger(C)[:4]]
        self.assertEqual(sorted(groupes), sorted(veille.GROUPES))

    def test_seulement_ce_qui_vaut_une_fiche(self):  # mission 6 : ≥ 8, une par source d'abord ; 5 à 8 → résumé de la semaine
        notes = {0: 9, 1: 9, 2: 8, 3: 8.5, 4: 5, 5: 8, 6: 2, 7: 4}
        choix = veille.choisir(C, notes, 5)
        self.assertLessEqual(len(choix), 5)
        self.assertEqual(choix[:3], [0, 3, 5])  # GitHub, Web, alerte cyber (la vidéo à 5 n'est pas une fiche)
        self.assertNotIn(4, choix)
        self.assertNotIn(6, choix)

    def test_une_fiche_cyber_par_semaine_sauf_faille_grave(self):
        self.assertNotIn(5, veille.choisir(C, {0: 9, 5: 8}, 5, cyber_ok=False))
        self.assertIn(5, veille.choisir(C, {0: 9, 5: 9.5}, 5, cyber_ok=False))

    def test_doublons_fusionnes_par_titre(self):
        self.assertEqual(veille.norme("bl4ckr0ss3/TTPScope"), veille.norme("ttpscope"))

    def test_trop_faible_ecarte(self):
        self.assertEqual(veille.choisir(C, {0: 2, 3: 1}, 5), [])


if __name__ == "__main__":
    unittest.main()
