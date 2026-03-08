"""TutorWorker — teaches knowledge to humans and agents.

Adaptive knowledge delivery: assesses learner baselines,
generates teaching content tailored to gaps, and verifies
understanding through targeted assessment. Uses KB claims
as source of truth and LLM for content generation.
"""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone

from grove.uwp import Worker, skill

# Mastery levels (from pedagogy spec §2.2)
MASTERY_NOVICE = "novice"
MASTERY_DEVELOPING = "developing"
MASTERY_PROFICIENT = "proficient"
MASTERY_EXPERT = "expert"

# Teaching strategies
STRATEGY_DIRECT = "direct"
STRATEGY_SOCRATIC = "socratic"
STRATEGY_EXAMPLE = "example_driven"
STRATEGY_ANALOGY = "analogy"

# Anti-patterns from the spec
ANTI_PATTERN_FIREHOSE = "firehose"
ANTI_PATTERN_NO_ASSESSMENT = "no_assessment"
ANTI_PATTERN_STALE_CONTENT = "stale_content"

DEFAULT_DB_PATH = os.environ.get(
    "LOOM_DB_PATH",
    os.path.join(
        os.path.expanduser("~"),
        "loom", "data", "loom.db"),
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _get_topic_claims(db_path, topic, limit=20):
    """Retrieve claims related to a topic from the KB.

    Uses both category match and LIKE search on statements.
    Returns list of claim dicts.
    """
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # Category match + keyword search.
        rows = conn.execute(
            "SELECT claim_id, statement, confidence, "
            "status, category, source_tier "
            "FROM claims "
            "WHERE category LIKE ? "
            "OR statement LIKE ? "
            "ORDER BY confidence DESC "
            "LIMIT ?",
            (f"%{topic}%", f"%{topic}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _get_claim_evidence(db_path, claim_id):
    """Get evidence for a specific claim."""
    path = db_path or DEFAULT_DB_PATH
    if not os.path.exists(path):
        return []

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT source_url, source_tier, excerpt "
            "FROM evidence WHERE claim_id = ? "
            "AND retracted = 0",
            (claim_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def _resolve_model():
    """Resolve the tutor LLM model."""
    explicit = os.environ.get("LOOM_MODEL")
    if explicit:
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            __import__("anthropic")
            return "claude-haiku-4-5-20251001"
        except ImportError:
            pass
    if os.environ.get("GEMINI_API_KEY"):
        try:
            __import__("google.generativeai")
            return "gemini-2.5-flash"
        except ImportError:
            pass
    return None


def _call_llm(system, prompt, model_name):
    """Call an LLM API. Returns (text, error)."""
    if model_name.startswith("claude-"):
        return _call_anthropic(system, prompt, model_name)
    return _call_gemini(system, prompt, model_name)


def _call_anthropic(system, prompt, model_name):
    try:
        import anthropic
    except ImportError:
        return None, "anthropic package not installed"
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None, "ANTHROPIC_API_KEY not set"
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model_name, max_tokens=4096,
            system=system,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return response.content[0].text, None
    except Exception as e:
        return None, str(e)


def _call_gemini(system, prompt, model_name):
    try:
        import google.generativeai as genai
    except ImportError:
        return None, "google-generativeai not installed"
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None, "GEMINI_API_KEY not set"
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name, system_instruction=system)
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.3),
        )
        return response.text, None
    except Exception as e:
        return None, str(e)


def _confidence_label(score):
    """Map confidence score to human-readable label."""
    if score >= 0.85:
        return "well-established"
    if score >= 0.65:
        return "supported by multiple sources"
    if score >= 0.40:
        return "reported but not fully confirmed"
    if score >= 0.15:
        return "disputed or contested"
    return "unverified"


def _generate_questions(claims, level, count=5):
    """Generate assessment questions from claims.

    Returns list of question dicts without LLM — uses
    deterministic templates based on mastery level.
    """
    questions = []
    for claim in claims[:count]:
        stmt = claim["statement"]
        conf = claim.get("confidence", 0.5)
        conf_label = _confidence_label(conf)

        if level in (MASTERY_NOVICE, None):
            questions.append({
                "type": "recognition",
                "question": (
                    f"Is the following statement "
                    f"{conf_label}?\n\n\"{stmt}\""),
                "claim_id": claim["claim_id"],
                "expected": "yes" if conf >= 0.65 else "uncertain",
            })
        elif level == MASTERY_DEVELOPING:
            questions.append({
                "type": "recall",
                "question": (
                    f"What do you know about: "
                    f"{claim.get('category', 'this topic')}"
                    f"? (Hint: {stmt[:50]}...)"),
                "claim_id": claim["claim_id"],
                "expected_keywords": [
                    w for w in stmt.lower().split()
                    if len(w) > 4
                ][:3],
            })
        else:
            questions.append({
                "type": "application",
                "question": (
                    f"How would you verify the claim: "
                    f"\"{stmt}\"? What sources would "
                    f"you check?"),
                "claim_id": claim["claim_id"],
                "source_tier": claim.get(
                    "source_tier", "T5"),
            })
    return questions


def _score_responses(questions, responses):
    """Score learner responses against expected answers.

    Returns (score 0-1, list of scored items).
    """
    if not questions or not responses:
        return 0.0, []

    scored = []
    correct = 0
    total = min(len(questions), len(responses))

    for i in range(total):
        q = questions[i]
        r = responses[i] if i < len(responses) else ""
        response_text = (
            r if isinstance(r, str) else str(r))

        is_correct = False
        if q["type"] == "recognition":
            expected = q.get("expected", "yes")
            is_correct = (
                expected.lower() in response_text.lower())
        elif q["type"] == "recall":
            keywords = q.get("expected_keywords", [])
            if keywords:
                matches = sum(
                    1 for kw in keywords
                    if kw in response_text.lower()
                )
                is_correct = matches >= len(keywords) / 2
        else:
            # Application: any substantive response.
            is_correct = len(response_text.strip()) > 20

        if is_correct:
            correct += 1
        scored.append({
            "question": q["question"],
            "response": response_text[:200],
            "correct": is_correct,
            "type": q["type"],
        })

    score = correct / total if total > 0 else 0.0
    return score, scored


def _determine_mastery(score, previous_level=None):
    """Determine mastery level from assessment score."""
    if score >= 0.95:
        return MASTERY_EXPERT
    if score >= 0.80:
        return MASTERY_PROFICIENT
    if score >= 0.50:
        return MASTERY_DEVELOPING
    return MASTERY_NOVICE


def _select_strategy(level, topic_type=None):
    """Select teaching strategy based on level."""
    if level == MASTERY_NOVICE:
        return STRATEGY_DIRECT
    if level == MASTERY_DEVELOPING:
        return STRATEGY_EXAMPLE
    if level == MASTERY_PROFICIENT:
        return STRATEGY_SOCRATIC
    return STRATEGY_SOCRATIC


def _build_teaching_content(claims, level, strategy,
                            topic, model_name=None):
    """Build teaching content from KB claims.

    Uses LLM when available for rich explanations,
    falls back to structured claim presentation.
    """
    if not claims:
        return {
            "explanation": f"No claims found for topic "
                           f"'{topic}' in the knowledge "
                           f"base.",
            "key_claims": [],
            "confidence_note": None,
            "strategy": strategy,
            "source": "empty_kb",
        }

    # Build structured claim summaries.
    key_claims = []
    for c in claims[:10]:
        key_claims.append({
            "claim_id": c["claim_id"],
            "statement": c["statement"],
            "confidence": c.get("confidence", 0.0),
            "confidence_label": _confidence_label(
                c.get("confidence", 0.0)),
            "status": c.get("status", "unknown"),
            "source_tier": c.get("source_tier", "T5"),
        })

    # Epistemic honesty: flag low-confidence claims.
    contested = [
        c for c in key_claims
        if c["confidence"] < 0.40
    ]
    confidence_note = None
    if contested:
        confidence_note = (
            f"{len(contested)} of {len(key_claims)} "
            f"claims have low confidence and should be "
            f"treated as uncertain."
        )

    # Try LLM for rich explanation.
    model = model_name or _resolve_model()
    if model:
        claims_text = "\n".join(
            f"- [{c['confidence_label']}] "
            f"{c['statement']}"
            for c in key_claims
        )
        system = (
            f"You are a tutor teaching about '{topic}'. "
            f"The learner's level is {level}. "
            f"Use a {strategy} teaching strategy. "
            f"IMPORTANT: Preserve epistemic honesty — "
            f"indicate confidence levels when citing "
            f"claims. Never present uncertain claims as "
            f"settled facts."
        )
        prompt = (
            f"Teach the following claims to a {level} "
            f"learner using {strategy} strategy:\n\n"
            f"{claims_text}\n\n"
            f"Provide a clear explanation, key "
            f"takeaways, and one practice question."
        )
        text, err = _call_llm(system, prompt, model)
        if text:
            return {
                "explanation": text,
                "key_claims": key_claims,
                "confidence_note": confidence_note,
                "strategy": strategy,
                "source": "llm",
            }

    # Fallback: structured presentation.
    explanation_parts = [
        f"## {topic.title()}\n",
    ]
    for c in key_claims:
        explanation_parts.append(
            f"**[{c['confidence_label']}]** "
            f"{c['statement']}\n"
            f"  Source tier: {c['source_tier']}, "
            f"Status: {c['status']}"
        )

    return {
        "explanation": "\n\n".join(explanation_parts),
        "key_claims": key_claims,
        "confidence_note": confidence_note,
        "strategy": strategy,
        "source": "structured",
    }


class TutorWorker(Worker):
    worker_type = "tutor"

    @skill("loom.tutor.assess",
           "Diagnostic assessment of learner knowledge")
    def tutor_assess(self, handle):
        """Assess a learner's knowledge on a topic.

        Queries the KB for claims in the topic domain,
        generates diagnostic questions, and optionally
        scores provided responses.

        Params:
            learner_id (str): Learner identifier.
            topic (str): Topic area to assess.
            db_path (str, optional): Source KB path.
            responses (list, optional): Answers to
                a previous assessment's questions.
            previous_level (str, optional): Known
                mastery level.

        Returns:
            dict with questions, score, mastery_level,
            and recommended strategy.
        """
        p = handle.params
        learner_id = p.get("learner_id", "")
        topic = p.get("topic", "")

        if not learner_id:
            return {"error": "learner_id is required"}
        if not topic:
            return {"error": "topic is required"}

        db_path = p.get("db_path", "")
        claims = _get_topic_claims(db_path, topic)
        previous_level = p.get("previous_level")
        responses = p.get("responses", [])

        questions = _generate_questions(
            claims, previous_level, count=5)

        if responses:
            score, scored = _score_responses(
                questions, responses)
            level = _determine_mastery(
                score, previous_level)
        else:
            score = None
            scored = None
            level = previous_level or MASTERY_NOVICE

        strategy = _select_strategy(level)

        return {
            "learner_id": learner_id,
            "topic": topic,
            "claims_found": len(claims),
            "questions": questions,
            "score": score,
            "scored_responses": scored,
            "mastery_level": level,
            "recommended_strategy": strategy,
            "assessed_at": _now_iso(),
        }

    @skill("loom.tutor.teach",
           "Generate adaptive teaching content")
    def tutor_teach(self, handle):
        """Generate teaching content for a topic.

        Retrieves relevant claims from the KB,
        selects teaching strategy based on mastery
        level, and generates explanation content
        (LLM-backed when available).

        Params:
            learner_id (str): Learner identifier.
            topic (str): Topic to teach.
            db_path (str, optional): Source KB path.
            mastery_level (str, optional): Current level.
            strategy (str, optional): Override strategy.

        Returns:
            dict with content, key_claims, exercises.
        """
        p = handle.params
        topic = p.get("topic", "")

        if not topic:
            return {"error": "topic is required"}

        db_path = p.get("db_path", "")
        level = p.get(
            "mastery_level", MASTERY_NOVICE)
        strategy = p.get(
            "strategy") or _select_strategy(level)

        claims = _get_topic_claims(db_path, topic)
        content = _build_teaching_content(
            claims, level, strategy, topic,
            model_name=p.get("model"),
        )

        # Generate exercises from claims.
        exercises = _generate_questions(
            claims, level, count=3)

        return {
            "learner_id": p.get("learner_id", ""),
            "topic": topic,
            "content": content,
            "exercises": exercises,
            "claims_used": len(claims),
            "mastery_level": level,
            "taught_at": _now_iso(),
        }

    @skill("loom.tutor.verify",
           "Verify learner understanding")
    def tutor_verify(self, handle):
        """Verify understanding via post-teaching quiz.

        Generates verification questions, scores
        responses, and identifies knowledge gaps.

        Params:
            learner_id (str): Learner identifier.
            topic (str): Topic to verify.
            db_path (str, optional): Source KB path.
            responses (list): Learner's responses.
            previous_level (str, optional): Pre-teach
                mastery level.

        Returns:
            dict with score, mastery_level, gaps.
        """
        p = handle.params
        learner_id = p.get("learner_id", "")
        topic = p.get("topic", "")
        responses = p.get("responses", [])

        if not learner_id:
            return {"error": "learner_id is required"}
        if not topic:
            return {"error": "topic is required"}

        db_path = p.get("db_path", "")
        claims = _get_topic_claims(db_path, topic)
        previous_level = p.get("previous_level")

        questions = _generate_questions(
            claims, previous_level, count=5)
        score, scored = _score_responses(
            questions, responses)
        new_level = _determine_mastery(
            score, previous_level)

        # Identify gaps: questions answered incorrectly.
        gaps = []
        if scored:
            for item in scored:
                if not item["correct"]:
                    gaps.append({
                        "question": item["question"],
                        "type": item["type"],
                        "needs_review": True,
                    })

        # Determine if mastery improved.
        level_order = [
            MASTERY_NOVICE, MASTERY_DEVELOPING,
            MASTERY_PROFICIENT, MASTERY_EXPERT,
        ]
        prev_idx = (
            level_order.index(previous_level)
            if previous_level in level_order
            else 0
        )
        new_idx = level_order.index(new_level)
        improved = new_idx > prev_idx

        return {
            "learner_id": learner_id,
            "topic": topic,
            "score": score,
            "scored_responses": scored,
            "mastery_level": new_level,
            "previous_level": previous_level,
            "improved": improved,
            "knowledge_gaps": gaps,
            "verified_at": _now_iso(),
        }


worker = TutorWorker(worker_id="loom-tutor-1")

if __name__ == "__main__":
    worker.run()
