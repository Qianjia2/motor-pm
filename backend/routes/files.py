import os
import uuid
from flask import Blueprint, request, jsonify, send_from_directory
from backend import db
from backend.models import Deliverable
from backend.routes.auth import require_auth

bp = Blueprint('files', __name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB per file
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'dwg', 'dxf', 'step', 'stp', 'igs', 'iges', 'zip', 'rar', 'jpg', 'jpeg', 'png', 'txt', 'csv', 'json', 'xml', 'py', 'c', 'h', 'cpp', 'm', 'sim', 'sch', 'pcb', 'brd'}


@bp.route('/files/upload', methods=['POST'])
@require_auth
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '未选择文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '文件名为空'}), 400

    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件类型: .{ext}'}), 400

    # Check file size (read first to get actual size)
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return jsonify({'error': f'文件过大（{size // 1024 // 1024}MB），单文件上限100MB'}), 413

    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)
    file.save(filepath)

    deliverable_id = request.form.get('deliverable_id', type=int)
    if deliverable_id:
        d = Deliverable.query.get(deliverable_id)
        if d:
            d.file_path = f'/api/files/download/{safe_name}'
            d.status = 'submitted'
            db.session.commit()

    return jsonify({
        'url': f'/api/files/download/{safe_name}',
        'filename': file.filename,
        'size': os.path.getsize(filepath),
    }), 201


@bp.route('/files/download/<filename>')
def download_file(filename):
    return send_from_directory(UPLOAD_DIR, filename, as_attachment=True)


@bp.route('/files/list')
def list_files():
    files = []
    for f in sorted(os.listdir(UPLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(UPLOAD_DIR, x)), reverse=True):
        path = os.path.join(UPLOAD_DIR, f)
        files.append({
            'name': f,
            'size': os.path.getsize(path),
            'modified': os.path.getmtime(path),
            'url': f'/api/files/download/{f}',
        })
    return jsonify(files[:50])


@bp.route('/files/stats')
def storage_stats():
    """Return storage usage statistics."""
    total_size = 0
    file_count = 0
    by_type = {}
    for f in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, f)
        if os.path.isfile(path):
            sz = os.path.getsize(path)
            total_size += sz
            file_count += 1
            ext = f.rsplit('.', 1)[-1].lower() if '.' in f else 'other'
            by_type[ext] = by_type.get(ext, 0) + sz

    # Get disk free space
    try:
        import shutil
        disk = shutil.disk_usage(UPLOAD_DIR)
        free_gb = round(disk.free / (1024**3), 1)
        total_gb = round(disk.total / (1024**3), 1)
    except Exception:
        free_gb = total_gb = 0

    return jsonify({
        'file_count': file_count,
        'total_size': total_size,
        'total_size_mb': round(total_size / (1024**2), 1),
        'by_type': {k: round(v / (1024**2), 1) for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:10]},
        'disk_free_gb': free_gb,
        'disk_total_gb': total_gb,
        'max_file_size_mb': MAX_FILE_SIZE // (1024**2),
    })
