from flask import Blueprint, jsonify, request, session

from vra_editor.core import record_locks

from ..auth import authenticate, config_path_for_request, current_username

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


@auth_bp.post('/login')
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    identity = authenticate(username, password, config_path=config_path_for_request())
    if identity is None:
        return jsonify({'error': 'Invalid username or password'}), 401

    session['username'] = identity['username']
    return jsonify({'username': identity['username']})


@auth_bp.post('/logout')
def logout():
    username = current_username()
    session.pop('username', None)
    if username:
        record_locks.release_all_for_holder(username, config_path_for_request())
    return jsonify({'ok': True})


@auth_bp.get('/whoami')
def whoami():
    username = current_username()
    if username is None:
        return jsonify({'error': 'Not authenticated'}), 401
    return jsonify({'username': username})
