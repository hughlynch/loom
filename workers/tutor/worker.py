"""TutorWorker — teaches knowledge to humans and agents.

Responsible for adaptive knowledge delivery: assessing learner baselines,
generating teaching content tailored to gaps, and verifying understanding
through targeted assessment.
"""

import os
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Mastery levels
MASTERY_NONE = "none"                # No demonstrated knowledge
MASTERY_RECOGNITION = "recognition"  # Can recognize correct information
MASTERY_RECALL = "recall"            # Can recall without prompts
MASTERY_APPLICATION = "application"  # Can apply in new contexts
MASTERY_SYNTHESIS = "synthesis"      # Can combine and extend knowledge

# Anti-patterns from the spec
ANTI_PATTERN_FIREHOSE = "firehose"  # Teaching everything at once
ANTI_PATTERN_NO_ASSESSMENT = "no_assessment"  # Teaching without baseline check
ANTI_PATTERN_STALE_CONTENT = "stale_content"  # Teaching from outdated snapshot


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TutorWorker(Worker):
    worker_type = "tutor"

    @skill("loom.tutor.assess", "Diagnostic assessment of learner baseline")
    def tutor_assess(self, handle):
        """Perform a diagnostic assessment of a learner's baseline knowledge.

        Identifies knowledge gaps relative to the current KB snapshot
        and recommends a learning path.

        Params (from handle.params):
            learner_id (str): Identifier for the learner.
            topic (str): Topic area to assess.
            snapshot_id (str, optional): KB snapshot to assess against.

        Returns:
            dict with learner_id, knowledge_gaps, recommended_path.
        """
        params = handle.params
        learner_id = params.get("learner_id", "")
        topic = params.get("topic", "")

        if not learner_id:
            return {"error": "learner_id is required"}
        if not topic:
            return {"error": "topic is required"}

        # Stub: in production, this queries the KB for the topic's
        # concept graph, generates diagnostic questions, and maps
        # the learner's responses to knowledge gaps.
        knowledge_gaps = [
            {
                "concept_id": f"concept-{topic}-001",
                "concept_name": f"[stub] Core concept in {topic}",
                "current_mastery": MASTERY_NONE,
                "target_mastery": MASTERY_APPLICATION,
            }
        ]

        recommended_path = [
            {
                "step": 1,
                "concept_id": f"concept-{topic}-001",
                "action": "teach",
                "estimated_duration_minutes": 15,
            }
        ]

        return {
            "learner_id": learner_id,
            "topic": topic,
            "knowledge_gaps": knowledge_gaps,
            "recommended_path": recommended_path,
            "assessed_at": _now_iso(),
        }

    @skill("loom.tutor.teach", "Generate adaptive teaching content")
    def tutor_teach(self, handle):
        """Generate adaptive teaching content for a specific concept.

        Tailors content to the learner's current mastery level, using
        claims from the KB as the source of truth.

        Params (from handle.params):
            concept_id (str): The concept to teach.
            learner_id (str): Identifier for the learner.
            current_mastery (str, optional): Learner's current mastery level.
            snapshot_id (str, optional): KB snapshot to teach from.

        Returns:
            dict with concept_id, content, exercises, confidence_level.
        """
        params = handle.params
        concept_id = params.get("concept_id", "")
        learner_id = params.get("learner_id", "")
        current_mastery = params.get("current_mastery", MASTERY_NONE)

        if not concept_id:
            return {"error": "concept_id is required"}

        # Stub: in production, retrieves relevant claims from the KB,
        # generates explanatory content via LLM, and creates exercises
        # appropriate to the learner's mastery level.
        content = {
            "explanation": f"[stub] Teaching content for {concept_id}",
            "key_claims": [],
            "examples": [],
            "analogies": [],
        }

        # Exercises scaled to mastery level
        exercises = []
        if current_mastery == MASTERY_NONE:
            exercises.append({
                "type": "recognition",
                "question": "[stub] Which of these statements is correct?",
                "options": [],
            })
        elif current_mastery == MASTERY_RECOGNITION:
            exercises.append({
                "type": "recall",
                "question": "[stub] Explain this concept in your own words.",
            })
        else:
            exercises.append({
                "type": "application",
                "question": "[stub] Apply this concept to the following scenario.",
                "scenario": "",
            })

        return {
            "concept_id": concept_id,
            "learner_id": learner_id,
            "content": content,
            "exercises": exercises,
            "confidence_level": 0.0,  # From KB claim confidence
            "taught_at": _now_iso(),
        }

    @skill("loom.tutor.verify", "Verify learner understanding")
    def tutor_verify(self, handle):
        """Verify a learner's understanding via targeted assessment.

        Generates questions based on the taught concept and evaluates
        responses to determine mastery level and identify misconceptions.

        Params (from handle.params):
            learner_id (str): Identifier for the learner.
            concept_id (str): The concept to verify.
            responses (list, optional): Learner's responses to exercises.

        Returns:
            dict with learner_id, concept_id, mastery_level, misconceptions.
        """
        params = handle.params
        learner_id = params.get("learner_id", "")
        concept_id = params.get("concept_id", "")
        responses = params.get("responses", [])

        if not learner_id:
            return {"error": "learner_id is required"}
        if not concept_id:
            return {"error": "concept_id is required"}

        # Stub: in production, evaluates responses against KB claims
        # using LLM, determining mastery level and identifying
        # specific misconceptions.
        mastery_level = MASTERY_RECOGNITION if responses else MASTERY_NONE

        misconceptions = []
        # Example misconception structure:
        # {
        #     "claim_id": "claim-xxx",
        #     "learner_belief": "...",
        #     "correct_statement": "...",
        #     "severity": "minor" | "major" | "critical",
        # }

        return {
            "learner_id": learner_id,
            "concept_id": concept_id,
            "mastery_level": mastery_level,
            "misconceptions": misconceptions,
            "responses_evaluated": len(responses),
            "verified_at": _now_iso(),
        }


worker = TutorWorker(worker_id="loom-tutor-1")

if __name__ == "__main__":
    worker.run()
