import unittest
from unittest.mock import patch

import pandas as pd

from excel_extractor import extract_workbook_currency


class WorkbookCurrencyTests(unittest.TestCase):

    def workbook(self):
        return type("Workbook", (), {"sheet_names": ["Holdings"]})()

    @patch("excel_extractor.pd.read_excel")
    def test_detects_explicit_inr_marker(self, read_excel):
        read_excel.return_value = pd.DataFrame([["Market Value (INR)"]])
        self.assertEqual(extract_workbook_currency(self.workbook()), "INR")

    @patch("excel_extractor.pd.read_excel")
    def test_detects_explicit_foreign_currency_code(self, read_excel):
        read_excel.return_value = pd.DataFrame([["Currency", "USD"]])
        self.assertEqual(extract_workbook_currency(self.workbook()), "USD")

    @patch("excel_extractor.pd.read_excel")
    def test_rejects_conflicting_currency_markers(self, read_excel):
        read_excel.return_value = pd.DataFrame([
            ["Market Value (INR)"],
            ["Currency", "USD"],
        ])
        self.assertIsNone(extract_workbook_currency(self.workbook()))

    @patch("excel_extractor.pd.read_excel")
    def test_does_not_treat_company_name_rs_as_inr(self, read_excel):
        read_excel.return_value = pd.DataFrame([["RS Software", "Market Value"]])
        self.assertIsNone(extract_workbook_currency(self.workbook()))

    @patch("excel_extractor.pd.read_excel")
    def test_does_not_guess_from_ambiguous_dollar_symbol(self, read_excel):
        read_excel.return_value = pd.DataFrame([["Market Value ($)"]])
        self.assertIsNone(extract_workbook_currency(self.workbook()))


if __name__ == "__main__":
    unittest.main()
