import ast
import unittest
from pathlib import Path


class ApiErrorDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = Path(__file__).with_name("main.py")
        cls.source = source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.functions = {
            node.name: node
            for node in ast.walk(cls.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

    def test_generic_exception_handlers_do_not_expose_exception_text(self):
        endpoints = (
            "chat",
            "analytics",
            "consolidated_portfolio",
            "risk_analysis",
            "goal_risk_analysis",
            "risk_explanation",
        )
        for name in endpoints:
            with self.subTest(endpoint=name):
                function = self.functions[name]
                handlers = [
                    node for node in ast.walk(function)
                    if isinstance(node, ast.ExceptHandler)
                    and isinstance(node.type, ast.Name)
                    and node.type.id == "Exception"
                ]
                self.assertEqual(len(handlers), 1)
                handler_source = ast.get_source_segment(self.source, handlers[0])
                self.assertNotIn("str(error)", handler_source)
                self.assertNotIn("{error}", handler_source)
                self.assertIn("traceback.print_exc()", handler_source)

    def test_expected_endpoints_use_specific_generic_messages(self):
        expected = {
            "chat": "Question processing failed. Please try again later.",
            "analytics": "Portfolio analytics failed. Please try again later.",
            "consolidated_portfolio": "Portfolio consolidation failed. Please try again later.",
            "risk_analysis": "Risk analysis failed. Please try again later.",
            "goal_risk_analysis": "Goal risk analysis failed. Please try again later.",
            "risk_explanation": "Risk explanation failed. Please try again later.",
        }
        for name, public_message in expected.items():
            with self.subTest(endpoint=name):
                function_source = ast.get_source_segment(
                    self.source, self.functions[name]
                )
                self.assertIn(public_message, function_source)

    def test_explicit_http_errors_are_preserved(self):
        chat_source = ast.get_source_segment(
            self.source, self.functions["chat"]
        )
        self.assertIn("except HTTPException:", chat_source)
        self.assertIn("raise", chat_source)


if __name__ == "__main__":
    unittest.main()
