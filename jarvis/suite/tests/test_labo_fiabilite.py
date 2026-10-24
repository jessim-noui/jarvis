"""Tests du Labo : résultats vérifiables et reprise sans doublons."""
import json, sys, tempfile, unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from suite import labo  # noqa: E402


class TestLaboFiabilite(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)
        self.taches = self.d / "taches.json"
        self.experiences = self.d / "experiences.json"
        self.taches.write_text(json.dumps([{"id": chr(97 + i), "consigne": chr(65 + i), "verifs": []} for i in range(8)]), encoding="utf-8")
        for p in (mock.patch.object(labo, "TACHES", self.taches),
                  mock.patch.object(labo, "EXPERIENCES", self.experiences),
                  mock.patch.object(labo, "arret_actif", return_value=False)):
            p.start()
            self.addCleanup(p.stop)

    def experience(self, taches=None):
        return labo.nouvelle("q", "h", {"profil": "jarvis"}, {"profil": "jarvis"}, taches=taches or ["a"])

    def test_tache_inconnue_refusee_avant_enregistrement(self):
        with self.assertRaisesRegex(ValueError, "inconnue"):
            self.experience(["absente"])
        self.assertFalse(self.experiences.exists())

    def test_limite_reprise_sans_rejouer_les_paires_finies(self):
        e = self.experience()
        appels = []

        def faux(variante, consigne):
            appels.append(variante["profil"])
            return "réponse", variante["profil"], 10, 0.1, ""

        with mock.patch.object(labo, "LIMITE_APPELS", 1):
            e = labo.lancer(e["id"], faux)
        self.assertEqual(e["etat"], "bloquee")
        self.assertEqual(len(e["resultats"]), 1)
        self.assertEqual(e["resultats"][0]["cote"], "reference")

        with mock.patch.object(labo, "LIMITE_APPELS", 4):
            e = labo.lancer(e["id"], faux)
        self.assertEqual(e["etat"], "terminee")
        self.assertEqual(len(e["resultats"]), 2)
        self.assertEqual([r["cote"] for r in e["resultats"]], ["reference", "variante"])
        self.assertEqual(len(appels), 2)

    def test_tache_retiree_bloque_sans_appel_ia(self):
        e = self.experience()
        self.taches.write_text("[]", encoding="utf-8")
        e = labo.lancer(e["id"], lambda *_: self.fail("aucun appel ne doit partir"))
        self.assertEqual(e["etat"], "bloquee")
        self.assertIn("absente", e["resume"]["arret"])

    def test_verification_inconnue_ne_valide_pas_une_reponse(self):
        ok, raisons = labo.verifier("réponse quelconque", [{"type": "contientre", "valeur": "oui"}])
        self.assertFalse(ok)
        self.assertIn("vérification inconnue", raisons[0])

    def test_batteries_annoncent_un_budget_borne(self):
        self.assertEqual([(b["id"], b["taches"], b["repetitions"], b["appels"]) for b in labo.options_batteries()],
                         [("rapide", 2, 1, 4), ("regulier", 4, 1, 8), ("complet", 8, 1, 16)])
        self.assertEqual([b["appels_avec_equipe"] for b in labo.options_batteries()], [8, 16, 32])

    def test_batterie_selectionnee_fixe_taches_et_repetitions(self):
        e = labo.nouvelle("q", "h", {"profil": "jarvis"}, {"profil": "jarvis-rapide"}, batterie="complet")
        self.assertEqual(e["taches"], list("abcdefgh"))
        self.assertEqual(e["repetitions"], 1)
        self.assertEqual(e["batterie"], "complet")

    def test_batterie_inconnue_refusee(self):
        with self.assertRaisesRegex(ValueError, "Batterie inconnue"):
            labo.nouvelle("q", "h", {"profil": "jarvis"}, {"profil": "jarvis"}, batterie="illimitee")

    def test_batterie_complete_reste_sous_la_limite_et_compte_les_tokens(self):
        e = labo.nouvelle("q", "h", {"profil": "jarvis"}, {"profil": "equipe", "equipe": True, "appels": 3}, batterie="complet")
        e = labo.lancer(e["id"], lambda v, c: ("ok", v["profil"], 10, 0.1, ""))
        self.assertEqual(e["etat"], "terminee")
        self.assertEqual(len(e["resultats"]), 16)
        self.assertEqual(e["resume"]["reference"]["appels"], 8)
        self.assertEqual(e["resume"]["variante"]["appels"], 24)
        self.assertEqual(e["resume"]["reference"]["tokens_total"], 80)
        self.assertEqual(e["resume"]["variante"]["tokens_total"], 80)

    def test_deux_equipes_refusees_si_elles_depassent_le_plafond(self):
        with self.assertRaisesRegex(ValueError, "dépasserait la limite"):
            labo.nouvelle("q", "h", {"profil": "equipe", "appels": 3},
                          {"profil": "equipe", "appels": 3}, batterie="complet")

    def test_appel_equipe_utilise_trois_profils_sans_contexte_prive(self):
        appels = []

        def faux(profil, messages, **_):
            appels.append((profil, messages))
            return {"content": "avis"}, profil

        with mock.patch("commun.demander", side_effect=faux), \
             mock.patch.object(labo, "lire_json", return_value=[{"tokens_entree": 2, "tokens_sortie": 3}]):
            reponse = labo.appeler_routeur({"equipe": True, "systeme": "concis"}, "Consigne de test")
        self.assertEqual([x[0] for x in appels], ["jarvis-rapide", "jarvis-code", "jarvis"])
        self.assertTrue(all("Consigne de test" in str(x[1]) for x in appels))
        self.assertNotIn("mails", str(appels).lower())
        self.assertEqual(reponse[2], 15)


if __name__ == "__main__":
    unittest.main(verbosity=2)
