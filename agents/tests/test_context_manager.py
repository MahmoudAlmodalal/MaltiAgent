"""
Unit tests for agents.context_manager.ContextManager.

Uses stdlib `unittest` (no pytest, no Django) so it runs in a clean environment
with `python3 -m unittest agents.tests.test_context_manager`.
"""
import json
import unittest

from agents.context_manager import (
    ContextManager,
    MissingContextError,
    UnknownAgentError,
)


def _seed(cm: ContextManager) -> None:
    """Populate the minimum prerequisites for late-stage agents."""
    cm.save_output(
        "research", {"summary": "x", "risks": [], "ambiguities": []}
    )
    cm.save_output("pm", {"user_stories": [], "scope": ""})
    cm.save_output(
        "system_designer", {"tech_stack": [], "components": []}
    )


class RequirementInitTests(unittest.TestCase):
    def test_requirement_initially_present(self):
        cm = ContextManager(requirement="Build a todo app for couples.")
        self.assertEqual(cm.requirement, "Build a todo app for couples.")

    def test_requirement_default_empty(self):
        cm = ContextManager()
        self.assertEqual(cm.requirement, "")


class ResearchSliceTests(unittest.TestCase):
    def test_research_slice_only_has_requirement(self):
        cm = ContextManager(requirement="Build X.")
        s = cm.get_slice("research")
        self.assertEqual(s, {"requirement": "Build X."})


class PMSliceTests(unittest.TestCase):
    def test_pm_slice_requires_research(self):
        cm = ContextManager(requirement="x")
        with self.assertRaises(MissingContextError):
            cm.get_slice("pm")

    def test_pm_slice_after_research(self):
        cm = ContextManager(requirement="todo app")
        cm.save_output(
            "research",
            {
                "summary": "todo app for couples; need shared lists",
                "risks": ["data privacy"],
                "ambiguities": ["mobile vs web?"],
                "best_practices": ["use OAuth"],
            },
        )
        s = cm.get_slice("pm")
        self.assertIn("research", s)
        self.assertTrue(s["research"]["summary"].startswith("todo app"))
        self.assertEqual(s["research"]["risks"], ["data privacy"])
        self.assertEqual(s["research"]["ambiguities"], ["mobile vs web?"])
        # PM should NOT see best_practices (not in the slice rule).
        self.assertNotIn("best_practices", s["research"])


class SystemDesignerSliceTests(unittest.TestCase):
    def test_system_designer_combines_pm_and_research_risks(self):
        cm = ContextManager(requirement="x")
        cm.save_output(
            "research",
            {"summary": "x", "risks": ["r1"], "ambiguities": []},
        )
        cm.save_output(
            "pm",
            {
                "user_stories": ["as a user I want X"],
                "scope": "mvp",
                "out_of_scope": ["payments"],
            },
        )
        s = cm.get_slice("system_designer")
        self.assertEqual(s["user_stories"], ["as a user I want X"])
        self.assertEqual(s["scope"], "mvp")
        self.assertEqual(s["risks"], ["r1"])
        # The whole research output should NOT leak into this slice.
        self.assertNotIn("research", s)


class DBSchemaSliceTests(unittest.TestCase):
    def test_db_schema_slice_has_architecture(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output(
            "system_designer",
            {"tech_stack": ["django"], "components": ["api"]},
        )
        s = cm.get_slice("db_schema")
        self.assertEqual(
            s["architecture"],
            {"tech_stack": ["django"], "components": ["api"]},
        )


class APIDesignerSliceTests(unittest.TestCase):
    def test_api_designer_slice_has_db_schema_only(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": [{"name": "Todo"}]})
        s = cm.get_slice("api_designer")
        self.assertEqual(s["db_schema"], {"models": [{"name": "Todo"}]})
        # No earlier stages should leak into the slice.
        self.assertNotIn("user_stories", s)
        self.assertNotIn("research", s)


class CodeReviewSliceTests(unittest.TestCase):
    def test_code_review_requires_target_artifact(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": []})
        with self.assertRaises(ValueError):
            cm.get_slice("code_review")

    def test_code_review_returns_target_artifact(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        s = cm.get_slice("code_review", target_artifact="db_schema")
        self.assertEqual(s["target_artifact"], "db_schema")
        self.assertEqual(s["artifact"], {"models": ["Todo"]})

    def test_code_review_appends_to_list(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        cm.save_output(
            "code_review", {"target_artifact": "db_schema", "issues": ["a"]}
        )
        cm.save_output(
            "code_review", {"target_artifact": "db_schema", "issues": ["b"]}
        )
        reviews = cm.output_for("code_review")
        self.assertIsInstance(reviews, list)
        self.assertEqual(len(reviews), 2)
        self.assertEqual(reviews[0]["issues"], ["a"])
        self.assertEqual(reviews[1]["issues"], ["b"])


class BugFixerSliceTests(unittest.TestCase):
    def test_bug_fixer_returns_latest_review_for_target(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        cm.save_output(
            "code_review",
            {
                "target_artifact": "db_schema",
                "issues": ["missing index on user_id"],
                "severity": "medium",
            },
        )
        s = cm.get_slice("bug_fixer", target_artifact="db_schema")
        self.assertEqual(s["artifact"], {"models": ["Todo"]})
        self.assertEqual(
            s["latest_review"]["issues"], ["missing index on user_id"]
        )

    def test_bug_fixer_filters_reviews_by_target(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        cm.save_output("api_designer", {"endpoints": ["GET /todos"]})
        cm.save_output(
            "code_review",
            {"target_artifact": "db_schema", "issues": ["db issue"]},
        )
        cm.save_output(
            "code_review",
            {"target_artifact": "api_designer", "issues": ["api issue"]},
        )
        s = cm.get_slice("bug_fixer", target_artifact="api_designer")
        self.assertEqual(s["latest_review"]["issues"], ["api issue"])

    def test_bug_fixer_latest_review_is_none_if_no_review(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        s = cm.get_slice("bug_fixer", target_artifact="db_schema")
        self.assertIsNone(s["latest_review"])


class TestingSliceTests(unittest.TestCase):
    def test_testing_slice_has_db_and_api(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        cm.save_output("api_designer", {"endpoints": ["GET /todos"]})
        s = cm.get_slice("testing")
        self.assertIn("db_schema", s)
        self.assertIn("api_design", s)
        self.assertEqual(s["db_schema"], {"models": ["Todo"]})
        self.assertEqual(s["api_design"], {"endpoints": ["GET /todos"]})


class DocumentationSliceTests(unittest.TestCase):
    def test_documentation_slice_has_everything(self):
        cm = ContextManager(requirement="x")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        cm.save_output("api_designer", {"endpoints": ["GET /todos"]})
        cm.save_output("testing", {"unit_tests": ["test_x"]})
        s = cm.get_slice("documentation")
        self.assertIn("all_outputs", s)
        keys = set(s["all_outputs"].keys())
        self.assertGreaterEqual(
            keys,
            {
                "research",
                "pm",
                "system_designer",
                "db_schema",
                "api_designer",
                "testing",
            },
        )


class UnknownAgentTests(unittest.TestCase):
    def test_unknown_agent_raises_on_get_slice(self):
        cm = ContextManager(requirement="x")
        with self.assertRaises(UnknownAgentError):
            cm.get_slice("nonexistent")

    def test_unknown_agent_raises_on_save_output(self):
        cm = ContextManager(requirement="x")
        with self.assertRaises(UnknownAgentError):
            cm.save_output("nonexistent", {})


class SnapshotRoundTripTests(unittest.TestCase):
    def test_snapshot_round_trip(self):
        cm = ContextManager(requirement="todo")
        _seed(cm)
        cm.save_output("db_schema", {"models": ["Todo"]})
        snap = cm.snapshot()

        # Snapshot must be JSON-serializable.
        json.dumps(snap)

        cm2 = ContextManager(snapshot=snap)
        self.assertEqual(cm2.requirement, cm.requirement)
        self.assertEqual(cm2.output_for("db_schema"), {"models": ["Todo"]})
        # Snapshots should be deep copies — mutating one must not affect the other.
        snap["outputs"]["db_schema"]["models"].append("Mutated")
        self.assertEqual(
            cm.output_for("db_schema"), {"models": ["Todo"]}
        )


class TokenGuardTests(unittest.TestCase):
    def test_token_guard_truncates_oversized_slices(self):
        cm = ContextManager(requirement="x", max_slice_tokens=500)
        huge = "lorem ipsum " * 5000  # ~60k chars → way over budget
        cm.save_output(
            "research",
            {"summary": huge, "risks": [], "ambiguities": []},
        )
        s = cm.get_slice("pm")
        # The structural keys are preserved.
        self.assertIn("research", s)
        self.assertIn("summary", s["research"])
        # And the serialized slice is much smaller than the raw input.
        serialized = json.dumps(s, ensure_ascii=False)
        self.assertLess(len(serialized), len(huge) // 2)

    def test_summarizer_callback_used_when_provided(self):
        calls = []

        def fake_summarizer(text: str, target_chars: int) -> str:
            calls.append((len(text), target_chars))
            return "[SUMMARIZED]"

        cm = ContextManager(
            requirement="x",
            max_slice_tokens=200,
            summarizer=fake_summarizer,
        )
        cm.save_output(
            "research",
            {
                "summary": "lorem ipsum " * 5000,
                "risks": [],
                "ambiguities": [],
            },
        )
        s = cm.get_slice("pm")
        self.assertTrue(calls, "summarizer should have been invoked")
        self.assertEqual(s["research"]["summary"], "[SUMMARIZED]")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
