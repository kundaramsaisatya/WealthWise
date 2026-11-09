import unittest

from portfolio_reconciliation import reconcile_portfolio_documents


class PortfolioReconciliationTests(unittest.TestCase):

    def holding(self, name="Example Fund", isin="INF000000001", folio="12345",
                quantity=10, nav=10, value=100, invested=80):
        return {
            "name": name,
            "isin": isin,
            "folio_number": folio,
            "quantity": quantity,
            "current_nav": nav,
            "current_value": value,
            "invested_value": invested,
        }

    def document(self, document_id, report_date, statement_type, holdings,
                 filename=None):
        return {
            "document_id": document_id,
            "filename": filename or f"{document_id}.pdf",
            "report_date": report_date,
            "statement_type": statement_type,
            "currency": "INR",
            "holdings": holdings,
        }

    def test_includes_nearby_statement_dates_without_double_counting(self):
        cas_holding = self.holding(value=105, nav=10.5)
        mf_holding = self.holding(value=104, nav=10.4)
        result = reconcile_portfolio_documents([
            self.document("cas-1", "2026-10-31", "cas", [cas_holding]),
            self.document("mf-1", "2026-10-29", "mutual_fund", [mf_holding]),
        ])

        self.assertEqual(result["report_date"], "2026-10-31")
        self.assertEqual(result["holding_count"], 1)
        self.assertEqual(result["total_current_value"], 105)
        self.assertEqual(result["holdings"][0]["document_id"], "cas-1")
        self.assertEqual(len(result["duplicate_groups"]), 1)

    def test_excludes_documents_outside_date_tolerance(self):
        result = reconcile_portfolio_documents([
            self.document("latest", "2026-10-31", "cas", [self.holding()]),
            self.document("old", "2026-10-20", "cas", [
                self.holding(name="Old Fund", isin="INF000000002")
            ]),
        ])

        self.assertEqual(result["holding_count"], 1)
        self.assertEqual(result["total_current_value"], 100)
        self.assertEqual(len(result["unreconciled_documents"]), 1)

    def test_excludes_future_document_from_explicit_snapshot(self):
        result = reconcile_portfolio_documents([
            self.document("target", "2026-10-31", "cas", [self.holding()]),
            self.document("future", "2026-11-01", "cas", [
                self.holding(name="Future Fund", isin="INF000000002")
            ]),
        ], target_report_date="2026-10-31")

        self.assertEqual(result["holding_count"], 1)
        self.assertEqual(len(result["unreconciled_documents"]), 1)

    def test_keeps_same_isin_in_different_folios_separate(self):
        result = reconcile_portfolio_documents([
            self.document("cas-1", "2026-10-31", "cas", [
                self.holding(folio="11111", value=100)
            ]),
            self.document("cas-2", "2026-10-31", "cas", [
                self.holding(folio="22222", value=200)
            ]),
        ])

        self.assertEqual(result["holding_count"], 2)
        self.assertEqual(result["total_current_value"], 300)

    def test_transaction_documents_never_add_current_holdings(self):
        result = reconcile_portfolio_documents([
            self.document("cas-1", "2026-10-31", "cas", [self.holding()]),
            self.document("txn-1", "2026-10-31", "transactions", [
                self.holding(name="Transaction row", isin="INF000000002")
            ]),
        ])

        self.assertEqual(result["holding_count"], 1)
        self.assertEqual(len(result["excluded_records"]), 1)

    def test_zero_quantity_with_nonzero_value_is_flagged(self):
        result = reconcile_portfolio_documents([
            self.document("cas-1", "2026-10-31", "cas", [
                self.holding(quantity=0, nav=10, value=50)
            ]),
        ])

        self.assertIn("units_x_nav_mismatch", result["holdings"][0]["quality_flags"])
        self.assertEqual(len(result["flagged_records"]), 1)

    def test_missing_cost_basis_does_not_inflate_profit_loss(self):
        known_cost = self.holding(value=100, invested=80)
        missing_cost = self.holding(
            name="No Cost Fund", isin="INF000000002", value=50, invested=None
        )
        result = reconcile_portfolio_documents([
            self.document("cas-1", "2026-10-31", "cas", [known_cost, missing_cost]),
        ])

        self.assertEqual(result["total_current_value"], 150)
        self.assertEqual(result["total_invested_value"], 80)
        self.assertEqual(result["comparable_current_value"], 100)
        self.assertEqual(result["total_profit_loss"], 20)
        self.assertEqual(result["missing_cost_count"], 1)


if __name__ == "__main__":
    unittest.main()
