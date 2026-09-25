# Apple validation: qualitative review of escalated cases

Target run: `runs/20260925T220239Z`. At the point when 122 `appearance` responses had been recorded, the first five cases in log order with a source `healthy` label and guard-rule escalation were selected. That snapshot contained 27 cases meeting this condition and zero source-`infected` cases routed to `routine_observation`. These counts are an **intermediate snapshot**, not final totals.

This is a **convenience-sample review** to investigate possible failure causes. An AI visual reviewer inspected both the original images and the actual model inputs resized to a maximum edge of 512 px. This is not a plant-pathologist assessment, independent relabeling, or disease diagnosis. The observations below did not alter source labels, evaluation results, prompts, rules, or sample selection.

| Case / manifest index | Appearance in original and model input | Recorded model output and guard rule | Possible explanation |
| --- | --- | --- | --- |
| [H277](data/healthy/H277.jpg) / 82 | Several small dark dots and brown marks on a green surface. | `visible_anomaly=yes`; described small brown dots but proposed `routine_observation`. Guard: `strong_analysis`. | A `healthy` label may not imply the absence of every surface mark. Detecting small appearance defects may differ from the folder's infection-label task. The cause of the dots and disease status cannot be established. |
| [H318](data/healthy/H318.jpg) / 32 | Red/yellow color distribution, fine dots, and bright surface marks. | `visible_anomaly=no`; JSON omitted `next_action` and failed validation. Guard: `strong_analysis`. | Escalation was caused by an **output-contract failure**, not an anomaly judgment. It should not be explained solely as a visual false positive. |
| [H201](data/healthy/H201.jpg) / 41 | Small dark dots, a brown mark on the left, and a cluster of brown marks near the bottom. | `visible_anomaly=yes`; described dots and discoloration, speculating about early rot. Proposed `routine_observation`; guard: `strong_analysis`. | Appearance marks may not align with the folder-label task. However, **early rot is not verified by this photo**. |
| [H438](data/healthy/H438.jpg) / 35 | Uneven bright marks and small dots on a yellow/light-red surface. | `visible_anomaly=yes`; described a large brown spot. Proposed `retake_photo`; guard: `strong_analysis`. | The reviewer could not clearly locate the **large brown spot** described by the model. Overinterpretation of natural color or surface markings, or an imprecisely located description, remain possible. |
| [H050](data/healthy/H050.jpg) / 76 | Vertical wrinkles at the top and scattered dark dots remain visible at 512 px. | `visible_anomaly=yes`; described wrinkles and color patterns, then speculated about internal damage or ripening stress. Both model and guard chose `strong_analysis`. | Visible wrinkling makes escalation understandable for appearance screening. The source `healthy` label alone does not establish that escalation was unnecessary. **Internal damage and ripening-related causes remain unverified**. |

Raw responses: [responses.jsonl](runs/20260925T220239Z/responses.jsonl). Actual inputs: [0082](runs/20260925T220239Z/prepared/0082.jpg), [0032](runs/20260925T220239Z/prepared/0032.jpg), [0041](runs/20260925T220239Z/prepared/0041.jpg), [0035](runs/20260925T220239Z/prepared/0035.jpg), and [0076](runs/20260925T220239Z/prepared/0076.jpg).

## Interpreting evaluation results

- Keep the metric name **escalation rate among source-labeled healthy images**. Without a separate expert assessment, do not call every escalation a confirmed misdiagnosis or unnecessary referral.
- Do not attribute the entire escalation rate to source-label issues either. These cases include actual surface marks, omitted output fields, an unconfirmed large-spot description, and internal-state speculation unsupported by RGB.
- Final quantitative results must retain the original labels and predefined denominators. Do not remove or relabel these five cases to improve the metrics.
- Escalation rate measures the workload passed to the detailed model. Final disease status and whether each escalation was necessary require separate evaluation.
- This review does not validate early detection, changes within the same physical fruit over time, memory retention, or actual pathogen infection.

A future validation study could independently annotate `visible mark type / mark location / inspectability / expert-assessed escalation need`, separately from the original infection label. That would distinguish infection classification from appearance-based screening. It is a proposal for a future experiment, not a directive to revise the current run's ground truth retrospectively.
