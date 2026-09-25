# Temporal observation algorithm v6

The main comparison remains direct GPT-5 for every image (A) versus local Liquid with persisted memory and selective GPT-5 (C). Existing v1 and failed development-version results are historical measurements, not results of this implementation. The GPT-5 model, prompt, image detail, and output budget remain unchanged.

For C, the runner reads the latest same-run, same-entity memory strictly before the current observation. Liquid receives the immediately previous observation image and current image in that order, both resized to a maximum dimension of 512 pixels. The prior image advances after every completed observation, including LOW_COST_ONLY. It is independent of the last GPT-5 reference image. The first observation has one image and must return `change_level=no_history`.

Timing includes relative elapsed seconds and `observed_at` when supplied; missing absolute times remain null. Liquid receives bounded prior GPT evidence, the previous local evidence/reason, and at most three open questions with their deadlines and whether they are due. No class labels, future state, or arbitrary manifest metadata are included in its prompt.

Liquid returns exactly four fields: `quality`, `change_level`, `evidence`, and `recommendation`. Evidence is the recorded recommendation reason; no local anomaly label or feature list is fabricated. The response schema enforces structure, while application validation rejects enum-only or placeholder evidence such as `no_history` and `no_evidence`. The recommendation is LOW_COST_ONLY or HIGH_COST_ANALYSIS. A deadline is context for reassessment, not an automatic escalation trigger.

The controller validates the result. Invalid calls or uncertain evidence escalate; an uninspectable image requests a retake and human review without treating the image as healthy. The maximum precision interval remains a safety guard: it starts at the first observation if no successful GPT-5 call exists, otherwise at the last successful GPT-5 call. There is no unconditional first-image GPT call and no unconditional escalation when a question becomes due. Clear new concerning evidence should cause Liquid to recommend analysis, with its reason recorded.

Every completed observation writes memory, including its image reference, timing, evidence and pending question state. Liquid does not generate follow-up questions in the simplified contract. A controller template opens a question from a HIGH recommendation with a 24-hour deadline; its source is explicitly recorded. Subsequent local reviews preserve that deadline and unresolved status. Only a successful GPT judgment changes or closes an existing concern. On a successful GPT-5 call its assessment takes precedence for follow-up state. Unusable images preserve unresolved questions. Failed GPT-5 calls never advance the successful precision clock or complete the observation.

## Auditability and resuming

The model journal records `input_context.previous`, `input_context.current`, and `input_context.prior_notes`. Notes are the same bounded values sent to Liquid; image bytes and credentials are excluded. The event journal preserves model recommendations and the controller's final action separately.

New run configurations pin SHA256 of the adapter, controller, runner and storage code; prompt versions/hashes; model names; inference settings; and local runtime/model file size and modification time. Artifact metadata is a change detector, not a cryptographic weight checksum. Any configuration mismatch blocks resume, including legacy run configurations. Use a new run ID for changed code or settings. Do not rewrite historical run files.

Paid request intents and responses remain durable. Successful responses are recovered without duplicate calls after interruption. Unanswered paid intents, unknown billing, or damaged journals require inspection rather than automatic reissue. The $0.10 per-call reservation is a soft guard, not a contractual billing maximum.

## Verification and limits

Offline tests cover ordered image pairs, bounded notes and timestamps, no label leakage, first-image behavior, memory advancing after local-only observations, deadlines that can stay local, maximum-gap behavior, invalid responses, failed precision-clock updates, resume configuration changes, and paid-call recovery. Offline tests do not establish savings or diagnostic accuracy. Local-only development checks were also run; see the limitations below. The output budget remains 512 tokens.

TR-6 collection can be displayed independently, but its multi-angle acquisition stream must not be treated as one verified physical fruit trajectory without resolving identity and view assumptions. The existing 18-day single-tomato stream remains the initial replay fixture.

## Real local validation and limitations

The v2 cloud integration check had invalid local schemas. The v3 local-only trial also failed schema validation (repeated feature codes and zero-hour follow-up). The v4 seven-field trial passed structure but returned placeholder evidence, and v5 four-field output missed the clear late change. These artifacts remain in `data/runs/`; they are failed development checks, not successful efficiency evidence.

The final v6 check at `data/runs/liquid_temporal_v6_local_validation/validation.json` compared days 1 and 18, verifying that the serialized resized images were distinct. Liquid reported a changed surface with wrinkling/discoloration and visible growth, recommending HIGH. Direct image inspection supports those broad visible differences; it does not confirm pathology. The first-image check described no visible damage but incorrectly marked the photograph unusable. The controller therefore requests retake/review. This remaining quality inconsistency means the local model is not validated as reliable. No GPT calls were made in these local trials, and no cost savings are claimed from selected examples. A subsequent small RawTree integration run can verify dataflow but cannot establish detection quality.

See the [temporal validation record](../reports/temporal_validation.md) for preserved development trials, observed limitations, and the subsequent integration-check status.
