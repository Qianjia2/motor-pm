from flask import Blueprint, request, jsonify
from backend import db
from backend.models import TeamMember

bp = Blueprint('team', __name__)


@bp.route('/team/members', methods=['GET'])
def list_members():
    members = TeamMember.query.filter_by(is_active=True).order_by(TeamMember.name).all()
    return jsonify([m.to_dict() for m in members])


@bp.route('/team/members', methods=['POST'])
def create_member():
    data = request.get_json()
    m = TeamMember(
        name=data['name'],
        department=data.get('department', ''),
        email=data.get('email', ''),
        phone=data.get('phone', ''),
        title=data.get('title', ''),
        skills=data.get('skills', ''),
        is_active=True,
    )
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@bp.route('/team/members/<int:id>', methods=['PUT'])
def update_member(id):
    m = TeamMember.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['name', 'department', 'email', 'phone', 'title', 'skills']
    for f in str_fields:
        if f in data:
            setattr(m, f, data[f])
    if 'is_active' in data:
        m.is_active = data['is_active']
    db.session.commit()
    return jsonify(m.to_dict())


@bp.route('/team/members/<int:id>', methods=['DELETE'])
def delete_member(id):
    m = TeamMember.query.get_or_404(id)
    m.is_active = False
    db.session.commit()
    return jsonify({'message': 'deactivated'})
