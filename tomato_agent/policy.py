"""Temporal model recommendation with deterministic quality and budget-independent guards."""
from __future__ import annotations

POLICY_VERSION = "tomato-temporal-v6"
LOW = "LOW_COST_ONLY"
HIGH = "HIGH_COST_ANALYSIS"


def choose_path(observation, cheap_call, memory, variant="C", max_gap_hours=72):
    from .models import _validate
    if variant not in {"A", "B", "C"}:
        raise ValueError("Unknown experiment variant")
    if variant == "A":
        return {"action": HIGH, "rules": ["always_strong_baseline"], "review_required": False,
                "quality_status": "not_assessed_by_liquid"}
    result = cheap_call.get("result") or {}
    decision = {"action": HIGH, "rules": [], "review_required": False,
                "quality_status": result.get("quality", "unknown")}
    if cheap_call.get("status") != "success" or not _validate(result, "liquid"):
        return dict(decision, rules=["invalid_or_failed_cheap_observation"], review_required=True)
    # No expensive model can recover pixels that are not inspectable; request a retake.
    if result["quality"] == "unusable":
        return dict(decision, action=LOW, rules=["unusable_image_request_retake"], review_required=True)
    elapsed = observation["elapsed_seconds"]
    last_strong = memory.get("last_strong_elapsed_seconds")
    anchor = last_strong if last_strong is not None else memory.get("first_observation_elapsed_seconds", elapsed)
    if elapsed - anchor >= max_gap_hours * 3600:
        return dict(decision, rules=["maximum_precision_gap"])
    # Deadlines and known marks are evaluated by Liquid with the prior image and notes.
    # They do not unconditionally invoke GPT. The first image can also remain local.
    recommendation = result["recommendation"]
    if recommendation == LOW and (result["change_level"] == "uncertain"):
        return dict(decision, rules=["uncertain_evidence_requires_second_opinion"], review_required=True)
    return dict(decision, action=recommendation, rules=["liquid_temporal_recommendation"],
                recommendation_reason=result["evidence"])


def update_memory(observation, cheap_call, strong_call, previous, decision, variant="C"):
    """Record each observation, including LOW; never convert monitoring into a health label."""
    import copy
    from .models import _validate
    state = copy.deepcopy(previous)
    elapsed = observation["elapsed_seconds"]
    state.setdefault("first_observation_elapsed_seconds", elapsed)
    state.update(last_observation_elapsed_seconds=elapsed,
                 last_observation_id=observation["observation_id"],
                 review_required=decision["review_required"])
    cheap_result = (cheap_call or {}).get("result") or {}
    valid_cheap = (cheap_call or {}).get("status") == "success" and _validate(cheap_result, "liquid")
    followup_result = None
    if valid_cheap:
        state["last_cheap_elapsed_seconds"] = elapsed
        if variant == "C":
            state.update(previous_evidence=cheap_result["evidence"][:400],
                         temporal_change=cheap_result["change_level"], previous_recommendation=cheap_result["recommendation"])
            if cheap_result["quality"] == "usable":
                # Controller-generated follow-up state, not a claimed Liquid output.
                questions = state.setdefault("open_questions", [])
                unresolved = [q for q in questions if q.get("status") == "open"]
                for q in unresolved:
                    q.update(last_local_review_elapsed_seconds=elapsed)
                if cheap_result["recommendation"] == HIGH and not unresolved:
                    questions.append({"question_id": "followup_" + observation["observation_id"],
                        "question": "Does this visible concern persist or worsen? " + cheap_result["evidence"][:200],
                        "status": "open", "opened_elapsed_seconds": elapsed,
                        "due_elapsed_seconds": elapsed + 24 * 3600,
                        "evidence_observation_id": observation["observation_id"],
                        "source": "controller_template_from_liquid_evidence"})
                state["open_questions"] = questions[-3:]
    if variant == "C":
        # Crucially this is the immediately preceding observation, not last GPT call.
        state["previous_frame_uri"] = observation["frame_uri"]
        state["previous_frame_sha256"] = observation.get("frame_sha256")
        state["previous_observed_at"] = observation.get("observed_at")
    if strong_call and strong_call.get("status") == "success":
        result = strong_call["result"]
        state["last_strong_elapsed_seconds"] = elapsed
        if variant == "C":
            state.update(last_strong_anomaly=result["visible_anomaly"], summary=result["evidence"][:1200],
                         prior_frame_uri=observation["frame_uri"], prior_observation_id=observation["observation_id"],
                         evidence=result["evidence"][:600], review_required=bool(result["review_required"]))
            followup_result = result
    if variant == "C" and followup_result is not None:
        questions = state.setdefault("open_questions", [])
        unresolved = [q for q in questions if q.get("status") == "open"]
        if followup_result["concern_open"]:
            question = followup_result.get("followup_question") or "Does the observed concerning appearance persist or worsen?"
            due = elapsed + followup_result["followup_after_hours"] * 3600
            if unresolved:
                for q in unresolved:
                    q.update(question=question[:300], due_elapsed_seconds=due, last_reviewed_elapsed_seconds=elapsed,
                             evidence_observation_id=observation["observation_id"])
            else:
                questions.append({"question_id": "followup_" + observation["observation_id"],
                    "question": question[:300], "status": "open", "opened_elapsed_seconds": elapsed,
                    "due_elapsed_seconds": due, "evidence_observation_id": observation["observation_id"]})
        else:
            for q in unresolved:
                q.update(status="closed", closed_elapsed_seconds=elapsed,
                         resolution="Current visual assessment reports no remaining concern; not verified diagnosis.")
        state["open_questions"] = questions[-3:]
    if variant != "C":
        state = {key: value for key, value in state.items()
                 if key in {"first_observation_elapsed_seconds", "last_observation_elapsed_seconds", "last_observation_id",
                            "last_cheap_elapsed_seconds", "last_strong_elapsed_seconds", "review_required"}}
    return state
