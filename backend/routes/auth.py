from datetime import datetime
from functools import wraps
from flask import Blueprint, request, jsonify, g
from backend import db
from backend.models import UserAuth, TeamMember

bp = Blueprint('auth', __name__)

# ── Token helper ──────────────────────────────

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': '请先登录'}), 401
        user = UserAuth.query.filter_by(token=token, is_active=True).first()
        if not user:
            return jsonify({'error': '登录已过期，请重新登录'}), 401
        user.last_login = datetime.utcnow()
        db.session.commit()
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


def require_role(*roles):
    def decorator(f):
        @wraps(f)
        @require_auth
        def wrapped(*args, **kwargs):
            if g.current_user.role not in roles and 'admin' not in roles:
                if g.current_user.role != 'admin':
                    return jsonify({'error': '权限不足'}), 403
            # If admin is in the allowed roles, admin can access
            if g.current_user.role == 'admin':
                return f(*args, **kwargs)
            if g.current_user.role not in roles:
                return jsonify({'error': '权限不足'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ── Routes ────────────────────────────────────

@bp.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': '请输入用户名和密码'}), 400

    user = UserAuth.query.filter_by(username=username, is_active=True).first()
    if not user or not UserAuth.verify_password(user.password_hash, password):
        return jsonify({'error': '用户名或密码错误'}), 401

    user.token = UserAuth.generate_token()
    user.last_login = datetime.utcnow()
    db.session.commit()

    return jsonify({
        'token': user.token,
        'user': user.to_dict(),
    })


@bp.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    member_name = data.get('member_name', '').strip()

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(password) < 4:
        return jsonify({'error': '密码至少4位'}), 400

    if UserAuth.query.filter_by(username=username).first():
        return jsonify({'error': '用户名已存在'}), 409

    # Create team member if name provided
    member_id = None
    if member_name:
        member = TeamMember(name=member_name, is_active=True)
        db.session.add(member)
        db.session.flush()
        member_id = member.id

    user = UserAuth(
        username=username,
        password_hash=UserAuth.hash_password(password),
        member_id=member_id,
        role='member',
    )
    db.session.add(user)
    db.session.commit()

    user.token = UserAuth.generate_token()
    db.session.commit()

    return jsonify({'token': user.token, 'user': user.to_dict()}), 201


@bp.route('/auth/me', methods=['GET'])
@require_auth
def me():
    return jsonify(g.current_user.to_dict())


@bp.route('/auth/logout', methods=['POST'])
@require_auth
def logout():
    g.current_user.token = None
    db.session.commit()
    return jsonify({'message': '已退出'})
