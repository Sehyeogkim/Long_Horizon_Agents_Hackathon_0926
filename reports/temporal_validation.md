# Temporal input validation

## Scope

The revised Liquid request includes the immediately previous image, the current image, their available times, and bounded earlier RawTree judgments and open questions. On the first observation only the current image exists. Absolute capture times in the 18-day data are unknown, so the request explicitly uses elapsed time with null absolute timestamps.

This is an integration change, not a disease classifier accuracy result. TR-6 collection is separate: 2,244 source files were downloaded and their metadata verified in RawTree; these files have not all been evaluated by the models.

## Development checks

| Contract | Observed result | Interpretation |
| --- | --- | --- |
| v2, expanded fields | Three live observations produced invalid Liquid output; GPT-5 handled all three | Failed local schema trial; retained under `data/runs/tomato_temporal_v2` |
| v3, schema constraints | Five local outputs failed strict validation | JSON generation did not reliably satisfy semantic value constraints |
| v4, seven fields | Five parseable outputs repeated `no_history` as evidence | Structural success did not establish image-grounded reasoning |
| v5, four fields | Day 1 to day 18 described as stable; first frame used placeholder evidence | Failed semantic spotcheck |
| v6, concise four fields | Day 1 to day 18 identified visible wrinkling/discoloration and requested HIGH; first-frame image quality incorrectly marked unusable | Partial improvement; routing is still unreliable |

The v3–v6 checks made local Liquid calls only. Their saved records are under `data/runs/liquid_temporal_v*_local_validation/`. V6 verified distinct serialized payload hashes for the two images. These development cases informed prompt changes, so they are not a held-out evaluation. Descriptions such as mold growth are unverified model observations.

The final local contract is `quality`, `change_level`, `evidence`, and `recommendation`. Placeholder evidence is rejected. The controller records open-question review without silently postponing an existing deadline; successful GPT-5 output may update follow-up state. A request for another photo remains a review task, not a healthy judgment.

## Comparison rule

The baseline remains every image directly sent to GPT-5. Historical 18-image measurements are preserved in `tomato_v1.html`. A shorter integration check must not be compared to the 18-image baseline as a savings measurement. API estimates are model-response token accounting, not invoices; local hardware and electricity costs are excluded.
