import os
import unittest
from unittest.mock import patch

from processor import classify_ticket


class ProcessorFallbackTests(unittest.TestCase):
    def test_classify_ticket_uses_rule_based_fallback_without_api_keys(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "USE_OLLAMA": "false"}, clear=False):
            cache = {}
            result = classify_ticket(
                {
                    "ticket_id": "T-100",
                    "subject": "Missing package",
                    "message": "My package never arrived and I need a refund today.",
                    "customer_name": "Jane",
                    "email": "jane@example.com",
                },
                repeat_count=0,
                cache=cache,
            )

        self.assertEqual(result["category"], "Refund")
        self.assertEqual(result["urgency"], "High")
        self.assertTrue(result["escalate"])
        self.assertIn("refund", result["summary"].lower())


if __name__ == "__main__":
    unittest.main()
