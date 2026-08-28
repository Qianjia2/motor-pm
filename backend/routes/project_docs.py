import os, uuid
from datetime import date
from flask import Blueprint, request, jsonify, send_from_directory
from backend import db
from backend.models import ProjectDocument
from backend.audit import log_action, get_username

bp = Blueprint('project_docs', __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

DOC_TYPE_GROUPS = [
    {
        'phase': 'P0',
        'label': 'P0 需求阶段',
        'types': [
            {'value': 'p0_contract', 'label': '开发合同'},
            {'value': 'p0_tech_agreement', 'label': '技术协议'},
            {'value': 'p0_requirement', 'label': '需求规格书'},
            {'value': 'p0_project_init', 'label': '立项报告'},
        ]
    },
    {
        'phase': 'PP1',
        'label': 'PP1 研发阶段',
        'types': [
            {'value': 'pp1_model', 'label': '仿真模型'},
            {'value': 'pp1_design_report', 'label': '设计报告'},
            {'value': 'pp1_drawing', 'label': '工程图纸'},
            {'value': 'pp1_test_plan', 'label': '测试方案'},
        ]
    },
    {
        'phase': 'PP2',
        'label': 'PP2 验证阶段',
        'types': [
            {'value': 'pp2_test_report', 'label': '样机测试报告'},
            {'value': 'pp2_data_regression', 'label': '数据回归分析'},
            {'value': 'pp2_improve_plan', 'label': '改进计划'},
            {'value': 'pp2_improve_report', 'label': '改进方案和报告'},
        ]
    },
]

ALL_DOC_TYPES = []
for g in DOC_TYPE_GROUPS:
    ALL_DOC_TYPES.extend(g['types'])

DOC_TYPE_LABELS = {t['value']: t['label'] for t in ALL_DOC_TYPES}
DOC_TYPE_PHASE = {}
for g in DOC_TYPE_GROUPS:
    for t in g['types']:
        DOC_TYPE_PHASE[t['value']] = g['label']


@bp.route('/projects/<int:pid>/documents', methods=['GET'])
def list_documents(pid):
    docs = ProjectDocument.query.filter_by(project_id=pid).order_by(ProjectDocument.upload_date.desc()).all()
    return jsonify([d.to_dict() for d in docs])


@bp.route('/projects/<int:pid>/documents', methods=['POST'])
def upload_document(pid):
    name = request.form.get('name', '')
    doc_type = request.form.get('doc_type', 'other')
    notes = request.form.get('notes', '')
    uploaded_by = request.form.get('uploaded_by', '')

    file_path = None
    file_size = 0

    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            safe_name = f"{uuid.uuid4().hex}_{file.filename}"
            filepath = os.path.join(UPLOAD_DIR, safe_name)
            file.save(filepath)
            file_path = f'/api/files/download/{safe_name}'
            file_size = os.path.getsize(filepath)
            if not name:
                name = file.filename

    if not name:
        return jsonify({'error': '请提供文档名称'}), 400

    doc = ProjectDocument(
        project_id=pid,
        name=name,
        doc_type=doc_type,
        file_path=file_path,
        file_size=file_size,
        uploaded_by=uploaded_by,
        upload_date=date.today(),
        notes=notes,
    )
    db.session.add(doc)
    db.session.commit()
    log_action(get_username(), 'create', 'document', doc.id, doc.name,
               project_id=pid, summary=f'上传文档 {doc.name}')
    return jsonify(doc.to_dict()), 201


@bp.route('/documents/<int:id>', methods=['PUT'])
def update_document(id):
    d = ProjectDocument.query.get_or_404(id)
    data = request.get_json()
    for f in ['name', 'doc_type', 'notes']:
        if f in data:
            setattr(d, f, data[f])
    db.session.commit()
    log_action(get_username(), 'update', 'document', d.id, d.name,
               project_id=d.project_id, summary=f'编辑文档 {d.name}')
    return jsonify(d.to_dict())


@bp.route('/documents/<int:id>', methods=['DELETE'])
def delete_document(id):
    d = ProjectDocument.query.get_or_404(id)
    pid = d.project_id
    db.session.delete(d)
    db.session.commit()
    log_action(get_username(), 'delete', 'document', id, d.name,
               project_id=pid, summary=f'删除文档 {d.name}')
    return jsonify({'message': 'deleted'})


@bp.route('/documents/<int:id>/deprecate', methods=['POST'])
def deprecate_document(id):
    """Mark a document as deprecated (失效)."""
    d = ProjectDocument.query.get_or_404(id)
    d.status = 'deprecated'
    d.notes = (d.notes or '') + '\n[已标记为失效]'
    db.session.commit()
    log_action(get_username(), 'deprecate', 'document', d.id, d.name,
               project_id=d.project_id, summary=f'标记文档失效 {d.name}')
    return jsonify(d.to_dict())


@bp.route('/documents/<int:id>/replace', methods=['POST'])
def replace_document(id):
    """Upload a new version to replace an old document."""
    old = ProjectDocument.query.get_or_404(id)

    name = request.form.get('name', old.name)
    doc_type = request.form.get('doc_type', old.doc_type)
    notes = request.form.get('notes', f'替换版本 V{old.version + 1}')
    uploaded_by = request.form.get('uploaded_by', old.uploaded_by or '')

    file_path = None
    file_size = 0

    if 'file' in request.files:
        file = request.files['file']
        if file.filename:
            safe_name = f"{uuid.uuid4().hex}_{file.filename}"
            filepath = os.path.join(UPLOAD_DIR, safe_name)
            file.save(filepath)
            file_path = f'/api/files/download/{safe_name}'
            file_size = os.path.getsize(filepath)
            if not name:
                name = file.filename

    new_doc = ProjectDocument(
        project_id=old.project_id,
        name=name,
        doc_type=doc_type,
        file_path=file_path,
        file_size=file_size,
        uploaded_by=uploaded_by,
        upload_date=date.today(),
        notes=notes,
        status='active',
        version=old.version + 1,
    )
    db.session.add(new_doc)
    db.session.flush()

    # Mark old as superseded
    old.status = 'superseded'
    old.replaced_by_id = new_doc.id
    old.notes = (old.notes or '') + f'\n[已被 V{new_doc.version} 替代]'

    db.session.commit()
    log_action(get_username(), 'replace', 'document', new_doc.id, new_doc.name,
               project_id=old.project_id, summary=f'替换文档 {old.name} → V{new_doc.version}')
    return jsonify(new_doc.to_dict()), 201


@bp.route('/lookups/doc-types')
def doc_types():
    return jsonify(DOC_TYPE_GROUPS)
