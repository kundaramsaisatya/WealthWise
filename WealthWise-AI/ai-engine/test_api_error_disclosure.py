import ast
import unittest
from pathlib import Path


class ApiErrorDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source_path = Path(__file__).with_name("main.py")
        cls.source = source_path.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_internal_error_responses_do_not_expose_exception_text(self):
        self.assertNotIn("str(error)", self.source)
        self.assertNotIn("{error}", self.source)

    def test_expected_endpoints_use_generic_internal_error_messages(self):
        expected = {
            "chat": "Question processing failed. Please try again later.",
            "analytics": "Portfolio analytics failed. Please try again later.",
            "consolidated_portfolio": "Portfolio consolidation failed. Please try again later.",
            "risk_analysis": "Risk analysis failed. Please try again later.",
            "goal_risk_analysis": "Goal risk analysis failed. Please try again later.",
            "risk_explanation": "Risk explanation failed. Please try again later.",
        }
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for function_name, public_message in expected.items():
            with self.subTest(endpoint=function_name):
                function = functions[function_name]
                segment = ast.get_source_segment(self.source, function)
                self.assertIn(public_message, segment)
                self.assertIn("traceback.print_exc()", segment)

    def test_explicit_http_errors_are_not_rewritten(self):
        functions = {
            node.name: node
            for node in ast.walk(self.tree)
            if isinstance(node, ast.FunctionDef)
        }
        chat_source = ast.get_source_segment(self.source, functions["chat"])
        self.assertIn("except HTTPException:", chat_source)
        self.assertIn("raise", chat_source)


if __name__ == "__main__":
    unittest.main()
