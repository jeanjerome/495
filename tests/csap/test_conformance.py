import unittest

from csap import InProcessAdapter, run_conformance
from tests.csap.support import description


class ConformanceKitTest(unittest.TestCase):
    def test_reference_adapter_passes_syntax_kit_without_security_claim(self):
        report = run_conformance(InProcessAdapter(description()))
        self.assertTrue(report.syntax_conformant, report.cases)
        self.assertTrue(all(case.passed for case in report.cases))
        self.assertEqual(
            {case.case_id for case in report.cases},
            {
                "accuse_annulation_non_terminal",
                "champ_inconnu",
                "conflit_idempotence",
                "controle_fail_transporte",
                "curseur",
                "extension_obligatoire_inconnue",
                "extension_optionnelle",
                "idempotence",
                "pass_incomplet_refuse",
                "references_completes",
                "refus_url_blob",
                "resultat_terminal",
                "retour_non_bloquant",
                "separation_ports",
                "terminalite",
                "transition_cancelled",
                "transition_failed",
                "transition_running",
                "version_commune",
                "version_incompatible",
                "vocabulaire_erreurs",
                "vocabulaire_etats",
            },
        )
        self.assertFalse(report.security_qualified)
