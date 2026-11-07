import os
import tempfile
import unittest

import pandas as pd

from excel_extractor import extract_excel


class AccountHolderExtractionTests(unittest.TestCase):
    def create_workbook(self, sheets):
        handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        handle.close()

        with pd.ExcelWriter(handle.name, engine="openpyxl") as writer:
            for name, rows in sheets.items():
                pd.DataFrame(rows).to_excel(
                    writer,
                    sheet_name=name,
                    header=False,
                    index=False,
                )

        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_extracts_explicit_investor_name(self):
        path = self.create_workbook({
            "Investor Info": [
                ["Statement type", "Account Statement"],
                ["Investor name", "Vikrant Anand Sathe"],
            ],
            "Holdings": [
                ["Scheme", "ISIN", "Market Value (INR)"],
                ["Sample Fund", "INF000000001", 1000],
            ],
        })

        result = extract_excel(path)

        self.assertEqual(result["account_holder"], "Vikrant Anand Sathe")

    def test_conflicting_explicit_names_are_not_guessed(self):
        path = self.create_workbook({
            "Investor Info": [["Investor name", "Person One"]],
            "Account Info": [["Account holder", "Person Two"]],
        })

        result = extract_excel(path)

        self.assertIsNone(result["account_holder"])

    def test_holding_name_is_not_mistaken_for_account_holder(self):
        path = self.create_workbook({
            "Holdings": [
                ["Name", "ISIN", "Market Value (INR)"],
                ["Person One Equity Fund", "INF000000001", 1000],
            ],
        })

        result = extract_excel(path)

        self.assertIsNone(result["account_holder"])


if __name__ == "__main__":
    unittest.main()
