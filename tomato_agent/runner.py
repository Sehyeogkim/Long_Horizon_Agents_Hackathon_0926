"""Chronological replay with checkpointed calls and a two-path controller."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import uuid

from .policy import POLICY_VERSION, HIGH, choose_path, update_memory

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def without_labels(value):
    if isinstance(value, dict):
        return {k: without_labels(v) for k, v in value.items()
                if "label" not in k.lower() and k.lower() not in {"ground_truth", "future_state", "target"}}
    if isinstance(value, list):
        return [without_labels(v) for v in value]
    return value


def append_durable(path, value):
    with path.open("a") as target:
        target.write(canonical(value) + "\n")
        target.flush()
        os.fsync(target.fileno())


def load_observations(manifest):
    rows = [json.loads(line) for line in Path(manifest).read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("Empty observation manifest")
    seen, clocks = set(), {}
    for row in rows:
        for key in ("dataset_id", "sequence_id", "entity_id", "observation_id", "frame_uri", "frame_sha256"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError("Missing observation field: " + key)
        elapsed = row.get("elapsed_seconds")
        if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid relative observation time")
        identity = (row["dataset_id"], row["sequence_id"], row["entity_id"])
        if row["observation_id"] in seen or elapsed <= clocks.get(identity, -1):
            raise ValueError("Duplicate observation ID or non-increasing entity time")
        clocks[identity] = elapsed
        seen.add(row["observation_id"])
        path = Path(row["frame_uri"])
        path = path if path.is_absolute() else ROOT / path
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["frame_sha256"]:
            raise ValueError("Observation image missing or checksum mismatch: " + row["observation_id"])
        # Labels are never passed to inference or memory, even if a manifest contains them.
    return [without_labels(row) for row in rows]


def event_for(observation, run_id, variant, kind, payload, suffix=""):
    identity = "|".join([run_id, kind, observation["observation_id"], suffix])
    return {
        "event_id": hashlib.sha256(identity.encode()).hexdigest(),
        "run_id": run_id, "variant": variant, "kind": kind, "schema_version": 1,
        "record_version": int(observation["elapsed_seconds"] * 1000) + 1,
        "dataset_id": observation["dataset_id"], "dataset_version": observation.get("dataset_version", "v1"),
        "sequence_id": observation["sequence_id"], "entity_id": observation["entity_id"],
        "observation_id": observation["observation_id"], "elapsed_seconds": observation["elapsed_seconds"],
        "synthetic": observation.get("synthetic", False), **payload,
    }


def report_run(store, run_id, variant):
    events = store.existing_events(run_id)
    decisions = [e for e in events if e["kind"] == "agent_events"]
    calls = [e["call"] for e in events if e["kind"] == "model_calls"]
    costs = [c.get("api_cost_usd_estimate") for c in calls]
    models = {}
    for call in calls:
        name = call["model"]
        item = models.setdefault(name, {"calls": 0, "successes": 0, "errors": 0,
            "input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0, "reasoning_tokens": 0,
            "unknown_usage_calls": 0, "latency_ms": 0, "api_cost_usd_estimate": 0})
        item["calls"] += 1
        item["successes"] += call["status"] == "success"
        item["errors"] += call["status"] != "success"
        usage = call.get("usage") or {}
        if usage.get("input_tokens") is None or usage.get("output_tokens") is None:
            item["unknown_usage_calls"] += 1
        for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens"):
            item[key] += usage.get(key) or 0
        item["latency_ms"] += call.get("latency_ms") or 0
        item["api_cost_usd_estimate"] += call.get("api_cost_usd_estimate") or 0
    completed = [e for e in decisions if e.get("status") == "completed"]
    return {"run_id": run_id, "variant": variant, "policy_version": POLICY_VERSION,
            "completed_observations": len(completed), "decision_count": len(decisions),
            "high_cost_observations": sum(e["action"] == HIGH for e in completed),
            "low_cost_observations": sum(e["action"] != HIGH for e in completed),
            "models": models, "api_cost_usd_estimate": sum(x for x in costs if x is not None),
            "unknown_cost_calls": sum(x is None for x in costs), "cost_basis": "published_price_estimate_not_invoice",
            "quality_metrics": {"recall": None, "false_positive_rate": None, "detection_delay": None},
            "limitations": ["Single specimen; not a disease accuracy benchmark",
                            "No independently verified disease onset/ground truth labels",
                            "Local electricity/device costs are unmeasured",
                            "Policy fixed before replay; this is a development demonstration"]}


def run(manifest, output_dir, variant="C", backend="local", run_id=None, limit=None,
        max_gap_hours=72, max_gpt_calls=20, max_api_cost_usd=1.0, liquid_factory=None,
        strong_factory=None, store_factory=None):
    from .models import LiquidModel, GPT5Model
    from .storage import EventStore
    if max_gap_hours <= 0 or max_gpt_calls < 0 or max_api_cost_usd <= 0:
        raise ValueError("Invalid policy or budget limit")
    rows = load_observations(manifest)
    if len({(r["dataset_id"], r["sequence_id"], r["entity_id"]) for r in rows}) != 1:
        raise ValueError("This MVP replays one sequence per run; split multi-entity manifests")
    run_id = run_id or ("tomato_" + variant.lower() + "_" + uuid.uuid4().hex[:12])
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid run_id")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / run_id
    run_dir.mkdir(exist_ok=True)
    config = {"run_id": run_id, "variant": variant, "backend": backend,
              "manifest_sha256": hashlib.sha256(Path(manifest).read_bytes()).hexdigest(),
              "policy_version": POLICY_VERSION, "max_gap_hours": max_gap_hours,
              "dataset_id": rows[0]["dataset_id"], "manifest": str(Path(manifest).resolve())}
    config_path = run_dir / "run.json"
    if config_path.exists() and json.loads(config_path.read_text()) != config:
        raise ValueError("Resume configuration differs from original run")
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    if limit is not None:
        if limit <= 0:
            raise ValueError("Limit must be positive")
        rows = rows[:limit]
    store_factory = store_factory or EventStore
    liquid_factory = liquid_factory or LiquidModel
    strong_factory = strong_factory or GPT5Model
    with store_factory(run_dir / "store", backend=backend) as store:
        store.flush()
        events = store.existing_events(run_id)
        # The model adapter fsyncs its call record before returning. Recover that
        # record if interrupted before the event journal/remote write completed.
        raw_log = run_dir / "model_calls.jsonl"
        persisted_call_ids = {e["call"]["call_id"] for e in events if e["kind"] == "model_calls"}
        observation_index = {r["observation_id"]: r for r in rows}
        adapter_calls = []
        if raw_log.exists():
            adapter_calls = [json.loads(line) for line in raw_log.read_text().splitlines() if line.strip()]
            for call in adapter_calls:
                oid = call.get("observation_id")
                if call["call_id"] not in persisted_call_ids and oid in observation_index:
                    tier = "strong" if call["provider"] == "openai" else "cheap"
                    event = event_for(observation_index[oid], run_id, variant, "model_calls",
                                      {"tier": tier, "call": call}, suffix=call["call_id"])
                    store.append("model_calls", event)
            events = store.existing_events(run_id)
        # An interrupted paid request without a durable response has unknown
        # outcome. Never silently repeat it (or treat unknown billing as zero).
        intents_path = run_dir / "paid_request_intents.jsonl"
        if intents_path.exists():
            answered = {c.get("request_attempt_id") for c in adapter_calls}
            answered.update(e["call"].get("request_attempt_id") for e in events if e["kind"] == "model_calls")
            intents = [json.loads(line) for line in intents_path.read_text().splitlines() if line.strip()]
            if any(i["request_attempt_id"] not in answered for i in intents):
                raise RuntimeError("An interrupted paid request has unknown outcome; inspect its record before retry")
        finished = {e["observation_id"] for e in events if e["kind"] == "agent_events" and e.get("status") == "completed"}
        prior_calls = [e for e in events if e["kind"] == "model_calls"]
        # Reuse only durable successful calls from this exact run/observation when resuming.
        cache = {(e["observation_id"], e["tier"]): e["call"] for e in prior_calls if e["call"]["status"] == "success"}
        spent = sum(e["call"].get("api_cost_usd_estimate") or 0 for e in prior_calls)
        strong_count = sum(e["tier"] == "strong" for e in prior_calls)
        remaining = [r for r in rows if r["observation_id"] not in finished]
        strong = strong_factory(run_dir, max_calls=max(0, max_gpt_calls - strong_count))
        context = liquid_factory(run_dir) if remaining and variant != "A" else contextlib.nullcontext(None)
        try:
            with context as liquid:
                for observation in remaining:
                    prior = store.latest_memory(run_id, observation["entity_id"], observation["elapsed_seconds"] - .001)
                    memory = (prior or {}).get("state", {})
                    # B does not receive semantic memory, even if storage is accidentally enriched.
                    if variant != "C":
                        memory = {k: v for k, v in memory.items() if k.startswith("last_") and k != "last_strong_anomaly"}
                    obs_event = event_for(observation, run_id, variant, "observations", {"observation": observation})
                    store.append("observations", obs_event)

                    def model_call(tier, fn):
                        nonlocal spent, strong_count
                        key = (observation["observation_id"], tier)
                        if key in cache:
                            return cache[key]
                        if tier == "strong":
                            unknown = any(e["tier"] == "strong" and e["call"].get("api_cost_usd_estimate") is None
                                          for e in prior_calls)
                            if unknown:
                                raise RuntimeError("A previous cloud request has unknown billing; automatic continuation stopped")
                            if strong_count >= max_gpt_calls or spent + .10 > max_api_cost_usd:
                                raise RuntimeError("GPT budget limit reached; checkpoint preserved")
                            attempt_id = uuid.uuid4().hex
                            append_durable(intents_path, {"request_attempt_id": attempt_id,
                                           "observation_id": observation["observation_id"]})
                        else:
                            attempt_id = uuid.uuid4().hex
                        call = fn(dict(observation, _request_attempt_id=attempt_id))
                        call.setdefault("call_id", uuid.uuid4().hex)
                        call.setdefault("request_attempt_id", attempt_id)
                        call.setdefault("observation_id", observation["observation_id"])
                        call_event = event_for(observation, run_id, variant, "model_calls",
                                               {"tier": tier, "call": call}, suffix=call["call_id"])
                        store.append("model_calls", call_event)
                        prior_calls.append(call_event)
                        spent += call.get("api_cost_usd_estimate") or 0
                        strong_count += tier == "strong"
                        if call["status"] == "success":
                            cache[key] = call
                        return call

                    cheap = model_call("cheap", lambda obs: liquid.observe(obs)) if variant != "A" else None
                    decision = choose_path(observation, cheap or {}, memory, variant, max_gap_hours)
                    strong_call = None
                    if decision["action"] == HIGH:
                        strong_call = model_call("strong", lambda obs: strong.analyze(obs, memory if variant == "C" else None))
                        if strong_call["status"] != "success":
                            raise RuntimeError("GPT analysis failed; checkpoint retained; no normal result inferred")
                    state = update_memory(observation, cheap, strong_call, memory, decision, variant)
                    memory_event = event_for(observation, run_id, variant, "memory_events", {"state": state})
                    store.append("memory_events", memory_event)
                    event = event_for(observation, run_id, variant, "agent_events", {
                        **decision, "selected_by": "explicit_policy", "policy_version": POLICY_VERSION,
                        "status": "completed", "memory_event_id": memory_event["event_id"],
                        "prior_memory_event_id": (prior or {}).get("event_id"),
                        "cheap_call_id": (cheap or {}).get("call_id"),
                        "strong_call_id": (strong_call or {}).get("call_id"),
                        "evidence": ((strong_call or cheap or {}).get("result") or {}).get("evidence", ""),
                        "visible_anomaly": ((strong_call or cheap or {}).get("result") or {}).get("visible_anomaly"),
                    })
                    store.append("agent_events", event)
                    store.flush()
                    print(json.dumps({"run_id": run_id, "observation_id": observation["observation_id"],
                                      "action": decision["action"], "rules": decision["rules"],
                                      "api_cost_usd_estimate_so_far": round(spent, 6)}), flush=True)
        finally:
            summary = report_run(store, run_id, variant)
            summary["requested_observations"] = len(rows)
            summary["completed"] = summary["completed_observations"] >= len(rows)
            (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary
