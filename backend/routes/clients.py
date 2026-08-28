from flask import Blueprint, request, jsonify
from backend import db
from backend.models import Client

bp = Blueprint('clients', __name__)


@bp.route('/clients', methods=['GET'])
def list_clients():
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    return jsonify([c.to_dict() for c in clients])


@bp.route('/clients', methods=['POST'])
def create_client():
    data = request.get_json()
    c = Client(
        name=data['name'],
        abbreviation=data.get('abbreviation', ''),
        address=data.get('address', ''),
        phone=data.get('phone', ''),
        contact_person=data.get('contact_person', ''),
        contact_phone=data.get('contact_phone', ''),
        contact_email=data.get('contact_email', ''),
        notes=data.get('notes', ''),
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(c.to_dict()), 201


@bp.route('/clients/<int:id>', methods=['PUT'])
def update_client(id):
    c = Client.query.get_or_404(id)
    data = request.get_json()
    str_fields = ['name', 'abbreviation', 'address', 'phone',
                  'contact_person', 'contact_phone', 'contact_email', 'notes']
    for f in str_fields:
        if f in data:
            setattr(c, f, data[f])
    db.session.commit()
    return jsonify(c.to_dict())


@bp.route('/clients/<int:id>', methods=['DELETE'])
def delete_client(id):
    c = Client.query.get_or_404(id)
    c.is_active = False
    db.session.commit()
    return jsonify({'message': 'deleted'})
