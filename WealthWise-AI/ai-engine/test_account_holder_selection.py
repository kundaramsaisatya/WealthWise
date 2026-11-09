import unittest

from account_holder_selection import select_account_holder_documents


class AccountHolderDocumentSelectionTests(unittest.TestCase):
    def test_selects_only_latest_identified_account_holder(self):
        documents = [
            {"filename": "older-owner", "account_holder": "Person One", "report_date": "2026-01-01"},
            {"filename": "latest-owner", "account_holder": "Jane Doe", "report_date": "2026-03-01"},
            {"filename": "same-owner", "account_holder": " jane   doe ", "report_date": "2026-02-01"},
            {"filename": "unknown-owner", "account_holder": None, "report_date": "2026-03-01"},
        ]
        selected, active = select_account_holder_documents(documents)
        self.assertEqual(active, "Jane Doe")
        self.assertEqual([item["filename"] for item in selected], ["latest-owner", "same-owner"])

    def test_uses_only_newest_document_when_owner_is_unknown(self):
        documents = [
            {"filename": "older", "account_holder": None, "report_date": "2026-01-01"},
            {"filename": "newest", "account_holder": "", "report_date": "2026-02-01"},
        ]
        selected, active = select_account_holder_documents(documents)
        self.assertIsNone(active)
        self.assertEqual([item["filename"] for item in selected], ["newest"])

    def test_empty_documents(self):
        self.assertEqual(select_account_holder_documents([]), ([], None))

    def test_rejects_invalid_collection(self):
        with self.assertRaisesRegex(ValueError, "must be a list"):
            select_account_holder_documents(None)


if __name__ == "__main__":
    unittest.main()
