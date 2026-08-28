from datetime import date, datetime, timedelta


def this_week_monday():
    today = date.today()
    return today - timedelta(days=today.weekday())


def week_number(d=None):
    d = d or date.today()
    return d.isocalendar()[1]


def status_light(pct_complete, is_blocked=False):
    """Return traffic-light status: normal / risk / blocked."""
    if is_blocked:
        return 'blocked'
    if pct_complete is None:
        return 'normal'
    return 'normal'


def compute_risk_level(probability, impact):
    matrix = {
        ('high', 'high'): 'critical',
        ('high', 'medium'): 'critical',
        ('medium', 'high'): 'critical',
        ('high', 'low'): 'high',
        ('medium', 'medium'): 'high',
        ('low', 'high'): 'high',
        ('medium', 'low'): 'medium',
        ('low', 'medium'): 'medium',
        ('low', 'low'): 'low',
    }
    return matrix.get((probability, impact), 'medium')


def to_dict(obj, *fields):
    """Convert a model instance to dict with specified fields."""
    result = {}
    for f in fields:
        val = getattr(obj, f, None)
        if isinstance(val, (date, datetime)):
            val = val.isoformat()
        elif hasattr(val, 'isoformat'):
            val = val.isoformat() if val else None
        result[f] = val
    return result
