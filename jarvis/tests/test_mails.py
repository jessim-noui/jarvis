"""Mails : seuls ceux qui valent une réponse remontent, jamais un refus ; pas de brouillon pour un refus."""
import sys, json, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import mails, securite  # noqa: E402


class TestMails(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tri = Path(self.tmp.name) / "tri.json"
        for attr, val in (("TRI", self.tri), ("BROUILLONS", Path(self.tmp.name) / "b.json"), ("ADRESSES", Path(self.tmp.name) / "a.json")):
            p = mock.patch.object(mails, attr, val)
            p.start()
            self.addCleanup(p.stop)

    def test_refus_jamais(self):
        self.tri.write_text(json.dumps({"1": {"vaut": True}}), encoding="utf-8")
        self.assertFalse(mails.action_requise({"id": "1", "statut": "refus", "action": "Proposer un entretien"}))

    def test_avis_de_l_ia_locale_prioritaire(self):
        self.tri.write_text(json.dumps({"2": {"vaut": False}, "3": {"vaut": True}}), encoding="utf-8")
        self.assertFalse(mails.action_requise({"id": "2", "statut": "attente", "action": "Répondre pour un entretien"}))
        self.assertTrue(mails.action_requise({"id": "3", "statut": "attente", "action": ""}))

    def test_regle_stricte_sans_tri(self):
        self.assertFalse(mails.action_requise({"id": "4", "statut": "attente", "action": "Attendre leur réponse",
                                               "resume": "Candidature bien reçue, pour plus d'informations contactez-nous."}))
        self.assertTrue(mails.action_requise({"id": "5", "statut": "attente", "action": "Donner tes disponibilités pour un entretien"}))
        self.assertTrue(mails.action_requise({"id": "6", "statut": "positif"}))

    def test_accuse_de_reception_jamais_une_tache(self):
        """Même si l'IA locale s'est trompée, un accusé de réception ne devient jamais une tâche (constat Business France)."""
        self.tri.write_text(json.dumps({"8": {"vaut": True}}), encoding="utf-8")
        self.assertFalse(mails.action_requise({"id": "8", "statut": "attente", "sujet": "Confirmation de transmission de votre candidature"}))
        self.assertTrue(mails.action_requise({"id": "8", "statut": "attente", "sujet": "Candidature bien reçue",
                                              "action": "Proposer tes disponibilités pour un entretien"}))
        self.assertEqual(mails.etape({"statut": "attente", "sujet": "Votre candidature est en cours d'analyse"}), "en analyse")

    def test_pas_de_brouillon_pour_un_refus(self):
        faux = {"maj": "", "etat": "ok", "items": [{"id": "7", "statut": "refus", "adresse": "rh@exemple.fr", "repondu": False}]}
        with mock.patch.object(mails, "reponses", return_value=faux), mock.patch.object(mails, "demander") as d:
            with self.assertRaises(securite.ActionRefusee):
                mails.brouillon("7")
            d.assert_not_called()


class TestEnvoiRestreint(unittest.TestCase):
    """Mission 5 : le site n'envoie plus de candidature, seulement une réponse à un mail reçu, vers son expéditeur."""
    faux = {"maj": "", "etat": "ok", "items": [{"id": "9", "statut": "positif", "adresse": "rh@exemple.fr", "repondu": False}]}

    def envoyer(self, a, ref):
        with mock.patch.object(mails, "reponses", return_value=self.faux), mock.patch.object(mails, "mon_adresse", return_value="moi@exemple.fr"), \
                mock.patch.object(mails, "identifiants", return_value=("", "")):
            return mails.envoyer(a, "Objet", "Bonjour", ref)

    def test_adresse_quelconque_refusee(self):
        with self.assertRaises(securite.ActionRefusee):
            self.envoyer("entreprise@autre.fr", "9")

    def test_sans_mail_recu_refuse(self):
        with self.assertRaises(securite.ActionRefusee):
            self.envoyer("rh@exemple.fr", "inconnu")

    def test_expediteur_accepte_jusqu_a_gmail(self):  # passe le contrôle, puis s'arrête faute de Gmail configuré (aucun envoi)
        with self.assertRaisesRegex(securite.ActionRefusee, "Gmail n'est pas configuré"):
            self.envoyer("rh@exemple.fr", "9")


if __name__ == "__main__":
    unittest.main()
