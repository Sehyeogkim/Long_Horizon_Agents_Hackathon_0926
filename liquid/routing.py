"""Prototype rule guard: never trust the small VLM's action suggestion alone.

The scheduler must supply the real unresolved/due state from external memory.
This guard does not establish diagnostic accuracy or turn 'no' into 'healthy'.
"""

def choose_action(result, *, unresolved_concern=False, review_due=False):
    if unresolved_concern or review_due:
        return 'strong_analysis'
    if not isinstance(result, dict):
        return 'strong_analysis'
    if result.get('visible_anomaly') in ('yes', 'uncertain'):
        return 'strong_analysis'
    if result.get('visible_anomaly') != 'no':
        return 'strong_analysis'
    if result.get('next_action') in ('strong_analysis', 'retake_photo'):
        return result['next_action']
    if result.get('next_action') != 'routine_observation':
        return 'strong_analysis'
    return 'routine_observation'
