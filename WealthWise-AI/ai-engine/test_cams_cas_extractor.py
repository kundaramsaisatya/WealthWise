import unittest

from cams_cas_extractor import extract_cams_cas


class CamsCasExtractorTests(unittest.TestCase):
    def test_parses_cams_cas_holding_without_ai(self):
        pages = [{
            "page": 1,
            "text": """Consolidated Account Summary
As on 31-Oct-2026
Saisatya Bhumeshwar Kundaram

Folio No. ISIN Scheme Name Cost Value Unit Balance NAV Date NAV Market Value Registrar
1047521975 INF209KB1O82 B66Y - Aditya Birla Sun Life PSU Equity 0.990 0.025 30-Oct-2026 37.52 0.94 CAMS
Fund Direct-Growth (Demat)
Total 0.99 0.94
"""
        }]
        result = extract_cams_cas(pages)
        self.assertIsNotNone(result)
        self.assertEqual(result["account_holder"], "Saisatya Bhumeshwar Kundaram")
        self.assertEqual(result["report_date"], "2026-10-31")
        holding = result["holdings"][0]
        self.assertEqual(holding["isin"], "INF209KB1O82")
        self.assertEqual(holding["folio_number"], "1047521975")
        self.assertAlmostEqual(holding["quantity"], 0.025)
        self.assertAlmostEqual(holding["invested_value"], 0.99)
        self.assertAlmostEqual(holding["current_nav"], 37.52)
        self.assertAlmostEqual(holding["current_value"], 0.94)
        self.assertEqual(holding["source"], "CAMS")
        self.assertEqual(result["total_value"], 0.94)


    def test_parses_column_aligned_layout_text(self):
        pages = [{
            "page": 1,
            "text": """Consolidated Account Summary
Saisatya Bhumeshwar Kundaram
1047521975
0.94
B66Y - Aditya Birla Sun Life PSU Equity
Fund Direct-Growth (Demat)
0.025 30-Oct-2026
37.52
CAMS
INF209KB1O82
0.990
""",
            "layout_text": """Consolidated Account Summary
As on 31-Oct-2026
Saisatya Bhumeshwar Kundaram
Folio No.      ISIN            Scheme Name                                          Cost Value        Unit Balance     NAV Date           NAV          Market Value    Registrar
1047521975     INF209KB1O82    B66Y - Aditya Birla Sun Life PSU Equity                    0.990              0.025  30-Oct-2026          37.52                  0.94       CAMS
                               Fund Direct-Growth (Demat)
Total                             0.99                                                                 0.94
"""
        }]
        result = extract_cams_cas(pages)
        self.assertIsNotNone(result)
        holding = result["holdings"][0]
        self.assertEqual(holding["isin"], "INF209KB1O82")
        self.assertEqual(holding["folio_number"], "1047521975")
        self.assertAlmostEqual(holding["quantity"], 0.025)
        self.assertAlmostEqual(holding["invested_value"], 0.99)
        self.assertAlmostEqual(holding["current_nav"], 37.52)
        self.assertAlmostEqual(holding["current_value"], 0.94)
        self.assertEqual(holding["source"], "CAMS")

    def test_ignores_long_explanatory_column_when_finding_holder(self):
        pages = [{
            "page": 1,
            "text": """Consolidated Account Summary
As on 31-Oct-2026
Email Id: kundaram@example.com The Consolidated Account Summary is brought to you as an investor friendly initiative by CAMS and KFintech, and lists the balances and valuation of Mutual Funds
Saisatya Bhumeshwar Kundaram
1047521975 INF209KB1O82 B66Y - Aditya Birla Sun Life PSU Equity 0.990 0.025 30-Oct-2026 37.52 0.94 CAMS
Fund Direct-Growth (Demat)
""",
            "layout_text": "Consolidated Account Summary"
        }]
        result = extract_cams_cas(pages)
        self.assertEqual(result["account_holder"], "Saisatya Bhumeshwar Kundaram")

    def test_ignores_non_cas_pdf(self):
        self.assertIsNone(extract_cams_cas([{"page": 1, "text": "Investment Portfolio Statement"}]))


if __name__ == "__main__":
    unittest.main()
