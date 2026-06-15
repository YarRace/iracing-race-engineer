from ire.metrics.tire import tire_metrics
from ire.metrics.balance import balance_metrics
from ire.metrics.suspension import suspension_metrics
from ire.metrics.inputs import input_metrics
from ire.metrics.consistency import consistency_metrics


def build_symptoms(frames, conditions):
    return {
        "tire": tire_metrics(frames),
        "balance": balance_metrics(frames),
        "suspension": suspension_metrics(frames),
        "inputs": input_metrics(frames),
        "consistency": consistency_metrics(frames),
        "conditions": conditions,
        "frame_count": len(frames),
    }
