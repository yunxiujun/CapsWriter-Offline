import unittest
from unittest.mock import patch

from core.client.llm.llm_minimax_search import model_options, prepare_messages


class MiniMaxSearchTest(unittest.TestCase):
    def test_search_context_is_inserted_without_mutating_user_message(self):
        prefix = "\u7528\u6237\u8f93\u5165\uff1a"
        query = "\u67e5\u8be2 MiniMax \u6700\u65b0\u6a21\u578b"
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "selection\n\n" + prefix + query},
        ]
        original = [dict(message) for message in messages]
        results = [
            {
                "title": "Result",
                "url": "https://example.com/result",
                "snippet": "Summary",
                "date": "2026-08-01",
            }
        ]

        with patch(
            "core.client.llm.llm_minimax_search._search",
            return_value=results,
        ) as search:
            prepared = prepare_messages(
                messages,
                "test-key",
                {"minimax_web_search": True},
                prefix,
            )

        self.assertEqual(search.call_args.args[2], query)
        self.assertEqual([item["role"] for item in prepared], ["system", "system", "user"])
        self.assertIn("https://example.com/result", prepared[-2]["content"])
        self.assertEqual(prepared[-1], messages[-1])
        self.assertEqual(messages, original)

    def test_control_options_are_not_sent_to_model(self):
        options = {
            "minimax_web_search": True,
            "minimax_search_max_results": 8,
            "temperature": 0.3,
        }

        filtered = model_options(options)

        self.assertNotIn("minimax_web_search", filtered)
        self.assertNotIn("minimax_search_max_results", filtered)
        self.assertEqual(filtered["temperature"], 0.3)

    def test_empty_search_results_fail_instead_of_faking_web_access(self):
        with patch(
            "core.client.llm.llm_minimax_search._search",
            return_value=[],
        ):
            with self.assertRaisesRegex(RuntimeError, "no usable results"):
                prepare_messages(
                    [{"role": "user", "content": "query"}],
                    "test-key",
                    {"minimax_web_search": True},
                )


if __name__ == "__main__":
    unittest.main()
