from flask import Blueprint
from backend.models import Phase, Gate, TechnicalLine, Role

bp = Blueprint('lookups', __name__)


@bp.route('/lookups/phases')
def get_phases():
    phases = Phase.query.order_by(Phase.sort_order).all()
    return [p.to_dict() for p in phases]


@bp.route('/lookups/gates')
def get_gates():
    gates = Gate.query.order_by(Gate.sort_order).all()
    return [g.to_dict() for g in gates]


@bp.route('/lookups/lines')
def get_lines():
    lines = TechnicalLine.query.order_by(TechnicalLine.sort_order).all()
    return [l.to_dict() for l in lines]


@bp.route('/lookups/roles')
def get_roles():
    roles = Role.query.order_by(Role.sort_order).all()
    return [r.to_dict() for r in roles]
