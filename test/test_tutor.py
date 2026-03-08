"""Tests for the tutor worker (i16).

Verifies assessment, teaching, and verification skills
with KB integration and deterministic question generation.
"""

import os
import sys
import tempfile
import unittest

# Set up paths
LOOM_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LOOM_DIR)
sys.path.insert(0, os.path.join(
    os.path.expanduser("~"), "grove", "python"))

from workers.kb.worker import LoomKBWorker, _vector_indices
from workers.tutor.worker import (
    TutorWorker,
    _generate_questions,
    _score_responses,
    _determine_mastery,
    _confidence_label,
    _select_strategy,
    MASTERY_NOVICE,
    MASTERY_DEVELOPING,
    MASTERY_PROFICIENT,
    MASTERY_EXPERT,
    STRATEGY_DIRECT,
    STRATEGY_EXAMPLE,
    STRATEGY_SOCRATIC,
)


class MockHandle:
    def __init__(self, params):
        self.params = params


def _make_db_with_claims(claims_data):
    """Create a temp DB with claims for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    _vector_indices.clear()
    kb = LoomKBWorker(worker_id="test")
    for data in claims_data:
        kb.kb_store_claim(MockHandle({
            "db_path": path, **data,
        }))
    return path


class TestConfidenceLabel(unittest.TestCase):
    def test_high_confidence(self):
        self.assertEqual(
            _confidence_label(0.90),
            "well-established")

    def test_medium_confidence(self):
        self.assertEqual(
            _confidence_label(0.70),
            "supported by multiple sources")

    def test_low_confidence(self):
        self.assertEqual(
            _confidence_label(0.50),
            "reported but not fully confirmed")

    def test_contested(self):
        self.assertEqual(
            _confidence_label(0.10),
            "unverified")


class TestSelectStrategy(unittest.TestCase):
    def test_novice_gets_direct(self):
        self.assertEqual(
            _select_strategy(MASTERY_NOVICE),
            STRATEGY_DIRECT)

    def test_developing_gets_examples(self):
        self.assertEqual(
            _select_strategy(MASTERY_DEVELOPING),
            STRATEGY_EXAMPLE)

    def test_proficient_gets_socratic(self):
        self.assertEqual(
            _select_strategy(MASTERY_PROFICIENT),
            STRATEGY_SOCRATIC)


class TestDetermineMastery(unittest.TestCase):
    def test_perfect_score(self):
        self.assertEqual(
            _determine_mastery(1.0), MASTERY_EXPERT)

    def test_high_score(self):
        self.assertEqual(
            _determine_mastery(0.85), MASTERY_PROFICIENT)

    def test_medium_score(self):
        self.assertEqual(
            _determine_mastery(0.60), MASTERY_DEVELOPING)

    def test_low_score(self):
        self.assertEqual(
            _determine_mastery(0.20), MASTERY_NOVICE)


class TestGenerateQuestions(unittest.TestCase):
    def setUp(self):
        self.claims = [
            {
                "claim_id": "c1",
                "statement": "The city budget is $4 million",
                "confidence": 0.85,
                "status": "corroborated",
                "category": "budget",
                "source_tier": "T2",
            },
            {
                "claim_id": "c2",
                "statement": "Population grew 12% last year",
                "confidence": 0.70,
                "status": "reported",
                "category": "demographics",
                "source_tier": "T3",
            },
        ]

    def test_novice_gets_recognition(self):
        qs = _generate_questions(
            self.claims, MASTERY_NOVICE, count=2)
        self.assertEqual(len(qs), 2)
        self.assertEqual(qs[0]["type"], "recognition")

    def test_developing_gets_recall(self):
        qs = _generate_questions(
            self.claims, MASTERY_DEVELOPING, count=2)
        self.assertEqual(qs[0]["type"], "recall")
        self.assertIn(
            "expected_keywords", qs[0])

    def test_proficient_gets_application(self):
        qs = _generate_questions(
            self.claims, MASTERY_PROFICIENT, count=1)
        self.assertEqual(qs[0]["type"], "application")

    def test_question_references_claim(self):
        qs = _generate_questions(
            self.claims, MASTERY_NOVICE, count=1)
        self.assertEqual(qs[0]["claim_id"], "c1")

    def test_empty_claims(self):
        qs = _generate_questions([], MASTERY_NOVICE)
        self.assertEqual(qs, [])


class TestScoreResponses(unittest.TestCase):
    def test_recognition_correct(self):
        qs = [{
            "type": "recognition",
            "question": "Is this well-established?",
            "expected": "yes",
            "claim_id": "c1",
        }]
        score, scored = _score_responses(qs, ["yes"])
        self.assertEqual(score, 1.0)
        self.assertTrue(scored[0]["correct"])

    def test_recognition_incorrect(self):
        qs = [{
            "type": "recognition",
            "question": "Is this well-established?",
            "expected": "yes",
            "claim_id": "c1",
        }]
        score, scored = _score_responses(qs, ["no"])
        self.assertEqual(score, 0.0)

    def test_recall_keyword_matching(self):
        qs = [{
            "type": "recall",
            "question": "What about the budget?",
            "expected_keywords": ["budget", "million"],
            "claim_id": "c1",
        }]
        score, scored = _score_responses(
            qs, ["The budget is 4 million dollars"])
        self.assertEqual(score, 1.0)

    def test_application_needs_substance(self):
        qs = [{
            "type": "application",
            "question": "How would you verify?",
            "claim_id": "c1",
            "source_tier": "T2",
        }]
        # Short response = incorrect.
        score, scored = _score_responses(qs, ["idk"])
        self.assertEqual(score, 0.0)

        # Substantive response = correct.
        score, scored = _score_responses(
            qs,
            ["I would check government records and "
             "public financial disclosures"])
        self.assertEqual(score, 1.0)

    def test_empty_responses(self):
        score, scored = _score_responses(
            [{"type": "recognition", "expected": "yes",
              "question": "?", "claim_id": "c1"}],
            [])
        self.assertEqual(score, 0.0)

    def test_no_questions(self):
        score, scored = _score_responses([], ["answer"])
        self.assertEqual(score, 0.0)


class TestTutorAssess(unittest.TestCase):
    """Test the assess skill with real KB data."""

    def setUp(self):
        self.db_path = _make_db_with_claims([
            {
                "statement": "City budget is $4 million",
                "category": "budget",
                "confidence": 0.85,
                "status": "corroborated",
            },
            {
                "statement": "Budget increased 5% from last year",
                "category": "budget",
                "confidence": 0.70,
                "status": "reported",
            },
        ])
        self.tutor = TutorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_assess_returns_questions(self):
        result = self.tutor.tutor_assess(self._params(
            learner_id="learner-1",
            topic="budget",
        ))
        self.assertEqual(result["topic"], "budget")
        self.assertGreater(result["claims_found"], 0)
        self.assertGreater(len(result["questions"]), 0)
        self.assertEqual(
            result["mastery_level"], MASTERY_NOVICE)

    def test_assess_with_responses(self):
        result = self.tutor.tutor_assess(self._params(
            learner_id="learner-1",
            topic="budget",
            responses=["yes", "yes", "yes", "yes", "yes"],
        ))
        self.assertIsNotNone(result["score"])
        self.assertIn(result["mastery_level"], [
            MASTERY_NOVICE, MASTERY_DEVELOPING,
            MASTERY_PROFICIENT, MASTERY_EXPERT,
        ])

    def test_assess_empty_topic_errors(self):
        result = self.tutor.tutor_assess(self._params(
            learner_id="learner-1", topic="",
        ))
        self.assertIn("error", result)

    def test_assess_no_claims_still_works(self):
        result = self.tutor.tutor_assess(self._params(
            learner_id="learner-1",
            topic="nonexistent_topic_xyz",
        ))
        self.assertEqual(result["claims_found"], 0)
        self.assertEqual(len(result["questions"]), 0)


class TestTutorTeach(unittest.TestCase):
    """Test the teach skill."""

    def setUp(self):
        self.db_path = _make_db_with_claims([
            {
                "statement": "Water boils at 100 degrees Celsius",
                "category": "science",
                "confidence": 0.95,
                "status": "verified",
            },
            {
                "statement": "Water freezes at 0 degrees Celsius",
                "category": "science",
                "confidence": 0.95,
                "status": "verified",
            },
        ])
        self.tutor = TutorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_teach_returns_content(self):
        result = self.tutor.tutor_teach(self._params(
            learner_id="learner-1",
            topic="science",
        ))
        self.assertIn("content", result)
        self.assertIn("exercises", result)
        self.assertGreater(result["claims_used"], 0)
        self.assertIn(
            "key_claims", result["content"])

    def test_teach_novice_uses_direct(self):
        result = self.tutor.tutor_teach(self._params(
            learner_id="learner-1",
            topic="science",
            mastery_level=MASTERY_NOVICE,
        ))
        self.assertEqual(
            result["content"]["strategy"],
            STRATEGY_DIRECT)

    def test_teach_preserves_epistemic_honesty(self):
        """Low-confidence claims get flagged."""
        db = _make_db_with_claims([
            {
                "statement": "Disputed claim about topic X",
                "category": "contested_topic",
                "confidence": 0.25,
                "status": "contested",
            },
        ])
        try:
            result = self.tutor.tutor_teach(MockHandle({
                "db_path": db,
                "topic": "contested_topic",
            }))
            note = result["content"]["confidence_note"]
            self.assertIsNotNone(note)
            self.assertIn("low confidence", note)
        finally:
            _vector_indices.clear()
            os.unlink(db)

    def test_teach_empty_kb_graceful(self):
        result = self.tutor.tutor_teach(self._params(
            topic="nonexistent_xyz",
        ))
        self.assertEqual(result["claims_used"], 0)
        self.assertIn("No claims found",
                       result["content"]["explanation"])

    def test_teach_missing_topic_errors(self):
        result = self.tutor.tutor_teach(self._params(
            topic="",
        ))
        self.assertIn("error", result)


class TestTutorVerify(unittest.TestCase):
    """Test the verify skill."""

    def setUp(self):
        self.db_path = _make_db_with_claims([
            {
                "statement": "The Federal Reserve sets interest rates",
                "category": "economics",
                "confidence": 0.90,
                "status": "verified",
            },
        ])
        self.tutor = TutorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_verify_with_correct_responses(self):
        result = self.tutor.tutor_verify(self._params(
            learner_id="learner-1",
            topic="economics",
            responses=["yes"],
            previous_level=MASTERY_NOVICE,
        ))
        self.assertIsNotNone(result["score"])
        self.assertIn("mastery_level", result)
        self.assertIn("knowledge_gaps", result)

    def test_verify_tracks_improvement(self):
        result = self.tutor.tutor_verify(self._params(
            learner_id="learner-1",
            topic="economics",
            responses=["yes"],
            previous_level=MASTERY_NOVICE,
        ))
        # Score of 1.0 with one question → expert.
        if result["score"] == 1.0:
            self.assertTrue(result["improved"])

    def test_verify_identifies_gaps(self):
        result = self.tutor.tutor_verify(self._params(
            learner_id="learner-1",
            topic="economics",
            responses=["wrong answer"],
            previous_level=MASTERY_NOVICE,
        ))
        if result["score"] < 1.0:
            self.assertGreater(
                len(result["knowledge_gaps"]), 0)

    def test_verify_no_responses(self):
        result = self.tutor.tutor_verify(self._params(
            learner_id="learner-1",
            topic="economics",
            responses=[],
        ))
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(
            result["mastery_level"], MASTERY_NOVICE)


class TestFullTutorLoop(unittest.TestCase):
    """Test the assess → teach → verify loop."""

    def setUp(self):
        self.db_path = _make_db_with_claims([
            {
                "statement": "The mayor serves a four-year term",
                "category": "civics",
                "confidence": 0.90,
                "status": "verified",
            },
            {
                "statement": "City council has nine members",
                "category": "civics",
                "confidence": 0.85,
                "status": "corroborated",
            },
        ])
        self.tutor = TutorWorker(worker_id="test")

    def tearDown(self):
        _vector_indices.clear()
        os.unlink(self.db_path)

    def _params(self, **kw):
        kw["db_path"] = self.db_path
        return MockHandle(kw)

    def test_full_loop(self):
        """Assess → Teach → Verify progression."""
        # 1. Assess baseline.
        assess = self.tutor.tutor_assess(self._params(
            learner_id="learner-1",
            topic="civics",
        ))
        self.assertEqual(
            assess["mastery_level"], MASTERY_NOVICE)
        self.assertGreater(
            len(assess["questions"]), 0)

        # 2. Teach.
        teach = self.tutor.tutor_teach(self._params(
            learner_id="learner-1",
            topic="civics",
            mastery_level=assess["mastery_level"],
        ))
        self.assertGreater(teach["claims_used"], 0)

        # 3. Verify with correct responses.
        verify = self.tutor.tutor_verify(self._params(
            learner_id="learner-1",
            topic="civics",
            responses=["yes", "yes"],
            previous_level=MASTERY_NOVICE,
        ))
        self.assertIsNotNone(verify["score"])
        self.assertIn("mastery_level", verify)


if __name__ == "__main__":
    unittest.main()
