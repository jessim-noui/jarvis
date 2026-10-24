"""Mission 12 : lettre sans info inventée (brouillon mistral-code-latest, relu et réécrit par Claude)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import verif_lettre  # noqa: E402

MOI = {'formation': [{'titre': 'Formation informatique', 'periode': '2023 – 2025'}],
       'experiences': [{'titre': 'Stage', 'lieu': 'Entreprise Exemple, Ville Exemple', 'periode': '2024', 'detail': 'Support et petits dépannages informatiques.'}],
       'competences': [{'domaine': 'Web', 'items': ['HTML', 'PHP', 'Python']}],
       'projets': [{'titre': 'Labo réseau', 'resume': 'pare-feu pfSense et serveur Debian en Python et interface web'}]}
HONNETE = ["Votre école forme des jeunes depuis cent ans.", "Je suis diplômé d'une formation informatique.",
           "J'ai effectué un stage en support et dépannage informatique.",
           "Pour mon projet de labo réseau, j'ai relié un serveur Debian à une interface web en Python.",
           "Le contact avec les utilisateurs me plaît.", "Je suis disponible rapidement.", "Je serais content d'en parler avec vous."]


def lettre(*lignes):
    return "Madame, Monsieur,\n\n" + "\n".join(lignes)


def verif(*lignes, offre=""):
    return verif_lettre.verifier(lettre(*lignes), MOI, offre)


class TestVerifLettre(unittest.TestCase):
    def test_lettre_honnete_intacte(self):
        r = verif(*HONNETE)
        self.assertEqual(r["retire"], [])
        self.assertEqual(r["lignes"], 7)
        self.assertEqual(r["alertes"], [])
        self.assertEqual(r["texte"], lettre(*HONNETE))

    def test_fait_de_stage_invente_est_retire(self):
        r = verif(*HONNETE[:2], "Pendant mon stage, j'ai configuré des postes Windows.", *HONNETE[3:])
        self.assertNotIn("configuré", r["texte"])
        self.assertIn("pas dans ton profil", r["retire"][0][1])

    def test_outil_absent_du_profil_retire(self):
        r = verif(*HONNETE, "J’ai administré un Active Directory.")  # apostrophe typographique
        self.assertNotIn("Active Directory", r["texte"])
        self.assertIn("active directory", r["retire"][0][1])

    def test_chiffre_invente_retire(self):
        r = verif(*HONNETE, "J'ai géré 50 postes.")
        self.assertNotIn("50", r["texte"])
        self.assertIn("50", r["retire"][0][1])

    def test_phrases_interdites(self):
        r = verif(*HONNETE, "Je suis dynamique et motivé.", "Je me permets de vous écrire.", "Je peux vous montrer mes travaux.")
        self.assertEqual([x[1] for x in r["retire"]], ["phrase interdite"] * 3)
        self.assertEqual(r["lignes"], 7)

    def test_ia_seulement_si_le_poste_en_parle(self):
        self.assertEqual(verif(*HONNETE, "J'ai monté un routeur d'IA avec Ollama.")["retire"][0][1], "parle d'IA alors que le poste n'en parle pas")
        r = verif(*HONNETE, "J'aime l'IA.", offre="poste en intelligence artificielle")
        self.assertEqual(r["retire"], [])

    def test_trop_longue_coupee_a_8(self):
        lignes = [f"Ligne {i}." for i in range(1, 11)]
        r = verif(*lignes)
        self.assertEqual(r["lignes"], 8)
        self.assertTrue(r["texte"].endswith("Ligne 10."))

    def test_trop_courte_signalee(self):
        self.assertIn("courte", verif("Ligne 1.", "Ligne 2.", "Ligne 3.")["alertes"][0])

    def test_tiret_long_enleve(self):
        self.assertNotIn("—", verif(*HONNETE[:-1], "Je serais content d'en parler — vraiment.")["texte"])

    def test_a_refaire(self):
        self.assertEqual(verif_lettre.a_refaire(lettre("Pendant mon stage, j'ai installé des PC.")), "")
        self.assertEqual(verif_lettre.a_refaire(lettre("Je peux vous montrer mes travaux.")), "propose de montrer des travaux")
        self.assertEqual(verif_lettre.a_refaire(lettre(*HONNETE)), "")


class TestEcrireLettre(unittest.TestCase):
    def test_question_au_lieu_d_inventer(self):
        import candidature
        from unittest.mock import patch
        o = {"id": "x", "titre": "Technicien support", "entreprise": ""}
        self.assertIn("question", candidature.ecrire_lettre(o, "texte"))  # entreprise inconnue : aucune IA appelée
        o["entreprise"] = "ACME"
        with patch.object(candidature, "demander", return_value=({"content": "QUESTION: Que fait ACME ?"}, "m")), \
                patch.object(candidature, "garder") as garder:
            self.assertEqual(candidature.ecrire_lettre(o, "texte")["question"], "Que fait ACME ?")
            garder.assert_not_called()

    def test_lettre_verifiee_avant_d_etre_gardee(self):
        import candidature
        from unittest.mock import patch
        brut = lettre(*HONNETE, "Je suis dynamique.")
        with patch.object(candidature, "demander", return_value=({"content": brut}, "m")), patch.object(candidature, "garder") as garder, \
                patch.object(candidature, "lire_json", return_value=MOI):
            r = candidature.ecrire_lettre({"id": "x", "titre": "T", "entreprise": "ACME"}, "texte")
        self.assertNotIn("dynamique", r["texte"])
        self.assertEqual(len(r["retire"]), 1)
        garder.assert_called_once_with("x", r["texte"])


if __name__ == "__main__":
    unittest.main()
