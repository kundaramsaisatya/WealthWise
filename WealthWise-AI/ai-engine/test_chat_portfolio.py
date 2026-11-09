import unittest

from chat_portfolio import build_chat_portfolio


class ChatPortfolioCurrencyTests(unittest.TestCase):
    def setUp(self):
        self.holdings = [{"name": "Example Fund", "current_value": 1250}]
        self.consolidation = {"report_date": "2026-10-31", "currency": "EUR"}

    def test_uses_verified_snapshot_currency(self):
        portfolio = build_chat_portfolio(
            "CLIENT-12345678-1234-1234-1234-123456789012",
            self.holdings,
            self.consolidation,
        )
        self.assertEqual(portfolio["currency"], "EUR")
        self.assertEqual(portfolio["report_date"], "2026-10-31")
        self.assertEqual(portfolio["holdings"], self.holdings)

    def test_normalizes_currency_whitespace_and_case(self):
        portfolio = build_chat_portfolio(
            "client", self.holdings, {"currency": " usd "}
        )
        self.assertEqual(portfolio["currency"], "USD")

    def test_does_not_assume_inr_when_currency_is_missing(self):
        self.assertIsNone(
            build_chat_portfolio("client", self.holdings, {"report_date": "2026-10-31"})
        )

    def test_rejects_empty_or_non_string_currency(self):
        for currency in ("", "   ", None, 123):
            with self.subTest(currency=currency):
                self.assertIsNone(
                    build_chat_portfolio(
                        "client", self.holdings, {"currency": currency}
                    )
                )

    def test_requires_holdings_and_consolidation(self):
        self.assertIsNone(build_chat_portfolio("client", [], self.consolidation))
        self.assertIsNone(build_chat_portfolio("client", self.holdings, None))


if __name__ == "__main__":
    unittest.main()
