import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import yaml


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import anthropic_work_step  # noqa: E402
import gemini_work_step  # noqa: E402
import openai_work_step  # noqa: E402
import work_step  # noqa: E402
from work_step import WorkStepResult  # noqa: E402


class GeminiWorkStepTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_uses_existing_prompt_and_context_builder(self):
        self.assertIs(
            gemini_work_step.MODEL_INSTRUCTIONS,
            anthropic_work_step.MODEL_INSTRUCTIONS,
        )
        self.assertIs(
            gemini_work_step._build_context,
            openai_work_step._build_context,
        )

    def test_openai_wire_prompt_uses_openai_specific_instructions(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Testantwort",
                                }
                            ],
                        }
                    ]
                }
            ).encode("utf-8")
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return response

        with patch.object(openai_work_step, "urlopen", fake_urlopen):
            openai_work_step._request_model("key", "model", "context")

        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(
            openai_work_step._INSTRUCTIONS,
            payload["instructions"],
        )

    def test_request_sends_context_and_extracts_all_text_parts(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": "Erster Teil"},
                                    {"text": "interner Gedanke", "thought": True},
                                    {"text": "Zweiter Teil"},
                                ]
                            },
                            "finishReason": "STOP",
                        }
                    ]
                }
            ).encode("utf-8")
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return response

        with patch.object(gemini_work_step, "urlopen", fake_urlopen):
            text = gemini_work_step._request_model(
                "secret-test-key",
                "gemini-test/model",
                '{"work_item": {}}',
            )

        self.assertEqual(text, "Erster Teil\nZweiter Teil")
        self.assertEqual(
            captured["timeout"],
            gemini_work_step.REQUEST_TIMEOUT_SECONDS,
        )
        self.assertTrue(
            captured["request"].full_url.endswith(
                "/gemini-test%2Fmodel:generateContent"
            )
        )
        self.assertEqual(
            captured["request"].get_header("X-goog-api-key"),
            "secret-test-key",
        )
        payload = json.loads(captured["request"].data.decode("utf-8"))
        self.assertEqual(
            payload["system_instruction"]["parts"][0]["text"],
            anthropic_work_step.MODEL_INSTRUCTIONS,
        )
        self.assertEqual(
            payload["contents"][0]["parts"][0]["text"],
            '{"work_item": {}}',
        )
        self.assertEqual(payload["generationConfig"]["maxOutputTokens"], 8192)

    def test_max_tokens_response_is_rejected(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "candidates": [
                        {
                            "content": {"parts": [{"text": "Unvollstaendig"}]},
                            "finishReason": "MAX_TOKENS",
                        }
                    ]
                }
            ).encode("utf-8")
        )

        with patch.object(gemini_work_step, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "Tokenlimit"):
                gemini_work_step._request_model("key", "model", "context")

    def test_blocked_response_is_rejected(self):
        response = io.BytesIO(
            json.dumps(
                {
                    "promptFeedback": {
                        "blockReason": "SAFETY",
                    }
                }
            ).encode("utf-8")
        )

        with patch.object(gemini_work_step, "urlopen", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "blockiert \\(SAFETY\\)"):
                gemini_work_step._request_model("key", "model", "context")

    def test_network_error_is_reported(self):
        with patch.object(
            gemini_work_step,
            "urlopen",
            side_effect=URLError("offline"),
        ):
            with self.assertRaisesRegex(RuntimeError, "Netzwerkfehler: offline"):
                gemini_work_step._request_model("key", "model", "context")

    def test_missing_configuration_stops_before_work_item_read(self):
        with patch.object(gemini_work_step, "_read_work_item") as read_work_item:
            self.assertEqual(gemini_work_step.generate("WI-0001"), 1)
            read_work_item.assert_not_called()

        os.environ["GEMINI_API_KEY"] = "test-key"
        with patch.object(gemini_work_step, "_read_work_item") as read_work_item:
            self.assertEqual(gemini_work_step.generate("WI-0001"), 1)
            read_work_item.assert_not_called()

    def test_generate_publishes_model_answer_with_gemini_participant(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["GEMINI_MODEL"] = "gemini-test"
        work_item = {
            "id": "WI-0001",
            "intent": "Test",
            "context_refs": [],
        }
        work_steps = [
            {
                "id": "WS-0001",
                "participant_id": "peer:test",
                "content": "Vorheriger Beitrag",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]

        with (
            patch.object(gemini_work_step, "_read_work_item", return_value=work_item),
            patch.object(
                gemini_work_step,
                "list_for_work_item",
                return_value=work_steps,
            ),
            patch.object(
                gemini_work_step,
                "_request_model",
                return_value="Gemini-Zwischenstand",
            ) as request_model,
            patch.object(
                gemini_work_step,
                "publish",
                return_value=WorkStepResult(
                    success=True,
                    id="WS-TEST",
                    path="test.yaml",
                ),
            ) as publish,
        ):
            self.assertEqual(gemini_work_step.generate("WI-0001"), 0)

        context = json.loads(request_model.call_args.args[2])
        self.assertEqual(context["work_item"]["id"], "WI-0001")
        self.assertEqual(context["existing_work_steps"][0]["id"], "WS-0001")
        publish.assert_called_once_with(
            work_item_id="WI-0001",
            participant_id="gemini:gemini-test",
            content="Gemini-Zwischenstand",
        )

    def test_generate_persists_through_existing_work_step_publish(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["GEMINI_MODEL"] = "gemini-test"

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_items_dir = root / "work_items"
            work_steps_dir = root / "work_steps"
            work_items_dir.mkdir()
            (work_items_dir / "WI-0001.yaml").write_text(
                yaml.dump(
                    {
                        "id": "WI-0001",
                        "intent": "Test",
                        "created_by": "test",
                        "created_at": "2026-01-01T00:00:00Z",
                        "base_commit": "abc",
                        "status": "open",
                        "context_refs": [],
                    },
                    allow_unicode=True,
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            def publish_to_temporary_vault(**kwargs):
                return work_step.publish(
                    **kwargs,
                    work_items_dir=work_items_dir,
                    work_steps_dir=work_steps_dir,
                )

            with (
                patch.object(
                    gemini_work_step,
                    "_read_work_item",
                    return_value={
                        "id": "WI-0001",
                        "intent": "Test",
                        "context_refs": [],
                    },
                ),
                patch.object(
                    gemini_work_step,
                    "list_for_work_item",
                    return_value=[],
                ),
                patch.object(
                    gemini_work_step,
                    "_request_model",
                    return_value="Persistierter Gemini-Zwischenstand",
                ),
                patch.object(
                    gemini_work_step,
                    "publish",
                    side_effect=publish_to_temporary_vault,
                ),
            ):
                self.assertEqual(gemini_work_step.generate("WI-0001"), 0)

            persisted = work_step.list_for_work_item(
                "WI-0001",
                work_steps_dir=work_steps_dir,
            )
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["participant_id"], "gemini:gemini-test")
            self.assertEqual(
                persisted[0]["content"],
                "Persistierter Gemini-Zwischenstand",
            )

    def test_invalid_context_prevents_request_and_publish(self):
        os.environ["GEMINI_API_KEY"] = "test-key"
        os.environ["GEMINI_MODEL"] = "gemini-test"
        work_item = {
            "id": "WI-0001",
            "intent": "Test",
            "context_refs": [r"C:\outside.txt"],
        }

        with (
            patch.object(
                gemini_work_step,
                "_read_work_item",
                return_value=work_item,
            ),
            patch.object(
                gemini_work_step,
                "list_for_work_item",
                return_value=[],
            ),
            patch.object(gemini_work_step, "_request_model") as request_model,
            patch.object(gemini_work_step, "publish") as publish,
        ):
            self.assertEqual(gemini_work_step.generate("WI-0001"), 1)

        request_model.assert_not_called()
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
