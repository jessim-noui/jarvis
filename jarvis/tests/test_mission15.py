"""Mission 15 : le fil de Jarvis (pastille d'activité). Brouillon délégué (mistral-code-latest), corrigé par Claude."""
import json, sys, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import commun  # noqa: E402
from suite import fil  # noqa: E402

SECRET = "sk-TEST1234567890SECRET"  # gitleaks:allow (fausse clé de test)
JOURNAL = [
    {"agent": "jarvis", "action": "pause", "etat": "info", "statut": "ok", "resume": SECRET, "t": "2026-10-21T07:00:00"},
    {"agent": "jarvis", "action": "pause", "etat": "info", "statut": "ok", "resume": SECRET, "t": "2026-10-21T08:00:00"},
    {"agent": "code", "action": "amelioration", "etat": "info", "statut": "ok", "resume": SECRET, "t": "2026-10-21T09:00:00"},
    {"agent": "veille", "action": "lancement", "etat": "debut", "modele": SECRET, "t": "2026-10-21T09:30:00"},
    {"agent": "veille", "action": "decouvertes2", "etat": "info", "statut": "erreur", "resume": SECRET, "modele": "groq/qwen-3.8", "t": "2026-10-21T10:00:00"},
]
DELEGATIONS = [{"sortie": "test.py", "t": "2026-10-21T11:00:00", "modele": "mistral/mistral-code-latest", "consigne": SECRET}]


def faux_lire(chemin, defaut=None):
    if chemin == commun.JOURNAL:
        return JOURNAL
    return DELEGATIONS if str(chemin).endswith("delegations.json") else defaut


@patch.object(commun, "lire_json", side_effect=faux_lire)
class TestFil(unittest.TestCase):
    def test_arret_si_jarvis_ne_peut_pas_travailler(self, _):
        with patch.object(commun, "peut_travailler", return_value=False):
            r = fil.fil({"labo": True}, {})
        self.assertEqual(r, {"actif": False, "en_cours": None, "lignes": []})

    def test_aucun_secret_ni_contenu(self, _):
        with patch.object(commun, "peut_travailler", return_value=True):
            texte = json.dumps(fil.fil({"decouvertes2": True}, {}), ensure_ascii=False)
        self.assertNotIn(SECRET, texte)
        self.assertNotIn("sk-", texte)

    def test_trois_lignes_plus_recente_d_abord(self, _):
        l = fil.lignes()
        self.assertEqual(len(l), 3)
        self.assertEqual([x["qui"] for x in l], ["Claude", "Découvertes", "Code"])
        self.assertIn("échec", l[1]["quoi"])
        self.assertEqual(l[1]["ia"], "qwen-3.8")

    def test_en_cours(self, _):
        r = fil.en_cours({"decouvertes2": True, "labo": False}, {"decouvertes2": time.time() - 70})
        self.assertEqual(r["qui"], "Découvertes")
        self.assertTrue(69 <= r["depuis"] <= 72)
        self.assertIsNone(fil.en_cours({"labo": False}, {}))

    def test_action_inconnue(self, _):
        r = fil.ligne_journal({"agent": "jarvis", "action": "action inconnue", "resume": SECRET, "t": "2026-10-21T10:00:00"})
        self.assertTrue(r["quoi"])
        self.assertNotIn(SECRET, json.dumps(r))


class TestIndexCtrlK(unittest.TestCase):
    def test_titres_seulement_sans_secret(self):
        from suite import index_site
        faux = [{"id": "x1", "titre": "Support " + SECRET, "etat": "pour_toi", "entreprise": "ACME", "description": "TEXTE-COMPLET"}]
        with patch("offres.liste", return_value=faux), patch.object(commun, "lire_json", side_effect=faux_lire):
            texte = json.dumps(index_site.index(), ensure_ascii=False)
        self.assertNotIn("TEXTE-COMPLET", texte)  # jamais le texte d'une offre
        self.assertNotIn(SECRET, texte)  # masqué même dans un titre


if __name__ == "__main__":
    unittest.main()
