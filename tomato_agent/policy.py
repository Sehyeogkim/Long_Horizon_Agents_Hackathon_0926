"""Versioned, deterministic two-path policy. No model chooses its own action."""
from __future__ import annotations

POLICY_VERSION = "tomato-two-path-v1"
LOW = "LOW_COST_ONLY"
HIGH = "HIGH_COST_ANALYSIS"


def choose_path(observation, cheap_call, memory, variant="C", max_gap_hours=72):
    if variant not in {"A", "B", "C"}:
        raise ValueError("Unknown experiment variant")
    if variant == "A":
        return {"action": HIGH, "rules": ["always_strong_baseline"], "review_required": False,
                "quality_status": "not_assessed_by_liquid"}
    result = cheap_call.get("result") or {}
    decision = {"action": LOW, "rules": [], "review_required": False,
                "quality_status": result.get("quality", "unknown")}
    # Unusable pictures are observations, not evidence of no change.
    if result.get("quality") == "unusable" and cheap_call.get("status") == "success":
        return dict(decision, rules=["unusable_image_request_retake"], review_required=True)
    reasons = []
    if cheap_call.get("status") != "success":
        reasons.append("invalid_or_failed_cheap_observation")
    elapsed = observation["elapsed_seconds"]
    last_strong = memory.get("last_strong_elapsed_seconds")
    if last_strong is None:
        reasons.append("initial_precision_check")
    elif elapsed - last_strong >= max_gap_hours * 3600:
        reasons.append("maximum_precision_gap")
    anomaly = result.get("visible_anomaly")
    if anomaly == "uncertain":
        reasons.append("uncertain_current_observation")
    if anomaly == "yes":
        known = (variant == "C" and memory.get("last_strong_anomaly") == "yes"
                 and memory.get("previous_anomaly") == "yes")
        if not known:
            reasons.append("new_visible_anomaly")
    if variant == "C":
        current_features = set(result.get("features", [])) - {"none"}
        previous_features = set(memory.get("previous_features", [])) - {"none"}
        if memory.get("last_observation_elapsed_seconds") is not None:
            if current_features - previous_features and anomaly in {"yes", "uncertain"}:
                reasons.append("new_concerning_feature")
        for question in memory.get("open_questions", []):
            if question.get("status") == "open" and elapsed >= question["due_elapsed_seconds"]:
                reasons.append("unresolved_question_due")
                break
    if reasons:
        decision.update(action=HIGH, rules=list(dict.fromkeys(reasons)))
    else:
        decision["rules"] = ["no_precision_trigger"]
    return decision


def update_memory(observation, cheap_call, strong_call, previous, decision, variant="C"):
    """No diagnosis is inferred from a low-cost path. Times update only on success."""
    import copy
    state = copy.deepcopy(previous)
    elapsed = observation["elapsed_seconds"]
    state["last_observation_elapsed_seconds"] = elapsed
    state["last_observation_id"] = observation["observation_id"]
    state["review_required"] = decision["review_required"]
    cheap_result = (cheap_call or {}).get("result") or {}
    if cheap_call and cheap_call.get("status") == "success":
        state["last_cheap_elapsed_seconds"] = elapsed
        if variant == "C":
            state["previous_features"] = cheap_result.get("features", [])
            state["previous_anomaly"] = cheap_result.get("visible_anomaly")
    if strong_call and strong_call.get("status") == "success":
        result = strong_call["result"]
        state["last_strong_elapsed_seconds"] = elapsed
        if variant == "C":
            state["last_strong_anomaly"] = result["visible_anomaly"]
            state["summary"] = result["evidence"][:1200]
            state["prior_frame_uri"] = observation["frame_uri"]
            state["prior_observation_id"] = observation["observation_id"]
            state["evidence"] = result["evidence"][:600]
            state["review_required"] = bool(result["review_required"])
            questions = state.setdefault("open_questions", [])
            unresolved = [q for q in questions if q.get("status") == "open"]
            if result["concern_open"]:
                due = elapsed + result["followup_after_hours"] * 3600
                if unresolved:
                    for q in unresolved:
                        q.update(due_elapsed_seconds=due, last_reviewed_elapsed_seconds=elapsed,
                                 evidence_observation_id=observation["observation_id"])
                else:
                    questions.append({"question_id": "followup_" + observation["observation_id"],
                                      "question": "Does the observed concerning appearance persist or worsen?",
                                      "status": "open", "opened_elapsed_seconds": elapsed,
                                      "due_elapsed_seconds": due,
                                      "evidence_observation_id": observation["observation_id"]})
            else:
                for q in unresolved:
                    q.update(status="closed", closed_elapsed_seconds=elapsed,
                             resolution="Model follow-up reports no remaining concern; not verified diagnosis.")
    # A/B retain only operational timing, never semantic history or open questions.
    if variant != "C":
        state = {key: value for key, value in state.items()
                 if key in {"last_observation_elapsed_seconds", "last_observation_id",
                            "last_cheap_elapsed_seconds", "last_strong_elapsed_seconds", "review_required"}}
    return state
