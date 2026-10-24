"""Mission 12 : compétences confirmées par l’utilisateur, textes du magazine validés (rien n'est changé avant « Valider »)."""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import moi_decisions  # noqa: E402


class TestMoiDecisions(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        d = Path(self.dir.name)
        self.moi = d / "moi.json"
        self.moi.write_text(json.dumps({"competences": [{"domaine": "Réseau", "items": ["DHCP / DNS", "Wireshark"]},
                                                        {"domaine": "Systèmes", "items": ["VMware"]}]}), encoding="utf-8")
        self.p = [patch.object(moi_decisions, "MOI", self.moi), patch.object(moi_decisions, "DONNEES", d)]
        for x in self.p:
            x.start()

    def tearDown(self):
        for x in self.p:
            x.stop()
        self.dir.cleanup()

    def lire(self):
        return json.loads(self.moi.read_text(encoding="utf-8"))

    def test_enlever_des_competences(self):
        moi_decisions.appliquer({"sujet": "moi-competences", "choix": "valider"}, {"enlever": ["Wireshark", "VMware"]})
        m = self.lire()
        self.assertEqual(m["competences"], [{"domaine": "Réseau", "items": ["DHCP / DNS"]}])
        self.assertTrue((Path(self.dir.name) / "moi-avant.json").exists())

    def test_reporter_ne_change_rien(self):
        avant = self.lire()
        moi_decisions.appliquer({"sujet": "moi-competences", "choix": ""}, {"enlever": ["Wireshark"]})
        self.assertEqual(self.lire(), avant)

    def test_texte_du_magazine_modifie(self):
        moi_decisions.appliquer({"sujet": "moi-magazine:2", "choix": "valider", "titre": "Ce qu'il cherche", "texte": "proposé"},
                                {"texte": "mon texte à moi"})
        self.assertEqual(self.lire()["magazine"]["2"], {"titre": "Ce qu'il cherche", "texte": "mon texte à moi"})


if __name__ == "__main__":
    unittest.main()
