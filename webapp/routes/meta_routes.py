"""App metadata for the web app's About panel (see App.vue's
AboutModal) -- currently just the version. No @login_required: this
is static, non-sensitive info, harmless to expose before login too.
"""

from flask import Blueprint, jsonify

from vra_editor.core.update_check import get_app_version

meta_bp = Blueprint('meta', __name__, url_prefix='/api')


@meta_bp.get('/version')
def version():
    return jsonify({'version': get_app_version()})
