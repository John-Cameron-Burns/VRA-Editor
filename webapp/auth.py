"""LDAP authentication for the web backend -- a plain simple bind via
ldap3 against whatever [ldap] server is configured (see
webapp/config.py), covering both a generic test-server DN pattern and
Active Directory's UPN/NetBIOS forms purely through bind_pattern
config, with no dev/prod code branch.

Session state is deliberately minimal: only the authenticated username
is stored (Flask's signed-cookie session, no server-side session
store) -- no password or bind DN persists past the initial bind.
"""

from functools import wraps
from typing import Optional

import ldap3
from flask import current_app, jsonify, session

from vra_editor.config import DEFAULT_CONFIG_PATH

from .config import load_ldap_config


def authenticate(username: str, password: str, config_path=None) -> Optional[dict]:
    """Attempts an LDAP simple bind as username/password. Returns
    {'username': username} on success, None on a bad bind (wrong
    password, unknown user, or any LDAP-level rejection) -- deliberately
    collapses all of those into the same "authentication failed"
    result, since distinguishing them to the caller would leak
    information about which usernames exist."""
    if not username or not password:
        return None
    cfg = load_ldap_config(config_path or DEFAULT_CONFIG_PATH)
    bind_dn = cfg['bind_pattern'].format(username=username)
    server = ldap3.Server(cfg['server'], use_ssl=cfg['use_ssl'], get_info=ldap3.NONE)
    conn = ldap3.Connection(server, user=bind_dn, password=password)
    try:
        return {'username': username} if conn.bind() else None
    except ldap3.core.exceptions.LDAPException:
        return None
    finally:
        conn.unbind()


def current_username() -> Optional[str]:
    return session.get('username')


def login_required(view):
    """Route decorator: 401s with a JSON body if there's no
    authenticated session, instead of letting the view run."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_username() is None:
            return jsonify({'error': 'Not authenticated'}), 401
        return view(*args, **kwargs)
    return wrapped


def config_path_for_request():
    """The VRA_CONFIG_PATH the current Flask app was created with (see
    app.py's create_app), or vra_editor.config.DEFAULT_CONFIG_PATH if
    none was set -- always a real Path, so every call site can do
    load_locations(config_path_for_request()) unconditionally rather
    than special-casing "no override". Lets tests point every
    config-reading call at an isolated temp config.ini without
    monkeypatching module-level defaults (which doesn't work reliably:
    Python binds default argument values once, at function-definition
    time, not at call time)."""
    return current_app.config.get('VRA_CONFIG_PATH') or DEFAULT_CONFIG_PATH
