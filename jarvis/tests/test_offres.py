"""Offres : une offre qui demande 3 ans n'est jamais « pour toi » ; le web privé n'est jamais ouvert (anti-SSRF)."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import lecture_offres as L  # noqa: E402
import commun  # noqa: E402

TEXTE = "Technicien support. Profil : 3 ans d'expérience exigée sur un poste similaire. CDI à Grenoble. " * 4


class TestTri(unittest.TestCase):
    def test_fiche_france_travail_3_ans(self):
        fiche = {"typeContrat": "MIS", "experienceExige": "E", "experienceLibelle": "3 An(s)"}
        etat, raison, _ = L.trier(fiche, {}, L.texte_ft({**fiche, "intitule": "Technicien", "description": TEXTE}))
        self.assertEqual((etat, raison), ("ecartee", "trop d'expérience demandée"))

    def test_ia_qui_se_trompe_sur_le_chiffre(self):
        ia = {"contrat": "CDI", "experience_annees": 0, "experience_obligatoire": True, "experience_phrase": "3 ans d'expérience exigée"}
        self.assertEqual(L.trier(None, ia, TEXTE)[0], "ecartee")
        ia["experience_annees"] = "nan"
        self.assertEqual(L.trier(None, ia, TEXTE)[0], "ecartee")

    def test_phrase_inventee_a_verifier(self):
        ia = {"contrat": "CDI", "experience_annees": 0, "experience_phrase": "Débutants bienvenus, aucune expérience requise"}
        self.assertEqual(L.trier(None, ia, TEXTE)[0], "a_verifier")

    def test_debutant_accepte_cdi(self):
        fiche = {"typeContrat": "CDI", "experienceExige": "D"}
        texte = L.texte_ft({**fiche, "intitule": "Technicien", "description": "Support N1 pour nos utilisateurs. " * 20})
        self.assertEqual(L.trier(fiche, {"pourquoi": "ok"}, texte)[0], "pour_toi")

    def test_reponse_ia_bizarre_ne_plante_pas(self):
        self.assertFalse(L.phrase_ok(["liste"], TEXTE))


class TestSSRF(unittest.TestCase):
    def test_adresses_privees_refusees(self):
        for u in ("http://127.0.0.1:4100/candidatures", "http://localhost:11434/", "http://192.168.1.1/", "file:///C:/x", "http://169.254.169.254/"):
            self.assertFalse(commun.adresse_publique(u), u)


if __name__ == "__main__":
    unittest.main()
