"""LDAP and/or local-OS-account authentication for the web backend.

authenticate() tries each configured backend in a fixed order -- LDAP
first (if [ldap] is configured), then local OS accounts (if
[local_auth] enabled = true) -- collapsing every failure mode from
every backend (wrong password, unknown user, backend unreachable, any
other rejection) into the same generic None, so a caller can never
learn which backends exist, which usernames are valid on any of them,
or which specific backend rejected a request.

Session state is deliberately minimal: only the authenticated username
is stored (Flask's signed-cookie session, no server-side session
store) -- no password, bind DN, or OS credential handle persists past
the call that produced it.
"""

import platform
from functools import wraps
from typing import Optional

import ldap3
from flask import current_app, jsonify, session

from vra_editor.config import DEFAULT_CONFIG_PATH

from .config import load_ldap_config, local_auth_enabled


def authenticate(username: str, password: str, config_path=None) -> Optional[dict]:
    """{'username': username} if either configured backend accepts the
    credentials, None otherwise (wrong password, unknown user, no
    backend configured, or every configured backend rejecting it)."""
    if not username or not password:
        return None
    config_path = config_path or DEFAULT_CONFIG_PATH

    ldap_cfg = load_ldap_config(config_path)
    if ldap_cfg is not None and _authenticate_ldap(username, password, ldap_cfg):
        return {'username': username}

    if local_auth_enabled(config_path) and _authenticate_local(username, password):
        return {'username': username}

    return None


def _authenticate_ldap(username: str, password: str, cfg: dict) -> bool:
    """A plain LDAP simple bind -- covers both a generic test-server DN
    pattern and Active Directory's UPN/NetBIOS forms purely through
    cfg['bind_pattern'], with no dev/prod code branch."""
    try:
        bind_dn = cfg['bind_pattern'].format(username=username)
    except (KeyError, IndexError) as e:
        # A malformed bind_pattern (e.g. "{usename}" instead of
        # "{username}") is a configuration bug, not a wrong password --
        # every login attempt would hit this identically, so it's
        # worth a clear server-side log line, but it still shouldn't
        # 500 the request: fail this backend the same way an
        # unreachable LDAP server already does, so local auth (if
        # enabled) still gets a chance.
        current_app.logger.error(
            "Invalid [ldap] bind_pattern %r in config -- %s: %s", cfg['bind_pattern'], type(e).__name__, e,
        )
        return False
    server = ldap3.Server(cfg['server'], use_ssl=cfg['use_ssl'], get_info=ldap3.NONE)
    conn = ldap3.Connection(server, user=bind_dn, password=password)
    try:
        return conn.bind()
    except ldap3.core.exceptions.LDAPException:
        return False
    finally:
        conn.unbind()


def _authenticate_local(username: str, password: str) -> bool:
    """Platform dispatch -- PAM on Linux, Win32 LogonUser on Windows.
    Each backend's own module is imported lazily inside its function,
    not here or at module top level, so `import webapp.auth` never
    hard-fails on the "wrong" OS even when local auth isn't enabled
    (e.g. running the test suite on a Mac dev machine)."""
    if platform.system() == 'Windows':
        return _authenticate_windows_local(username, password)
    return _authenticate_pam(username, password)


def _authenticate_pam(username: str, password: str) -> bool:
    """PAM bind via the python-pam package (PyPI: python-pam, import
    name `pam`) -- a ctypes wrapper around libpam with no compiled
    extension, matching this codebase's existing preference for
    pure-Python deps (ldap3, dulwich) over shelling out.

    Requires the calling process to be root (or in the 'shadow' group)
    to read /etc/shadow -- see InstallOptions.service_user and the
    generated Linux install script's own runtime warning
    (web_installer.py) for the operator-facing side of this."""
    import pam
    try:
        return pam.pam().authenticate(username, password, service='login')
    except Exception:
        return False


def _authenticate_windows_local(username: str, password: str) -> bool:
    """Local Windows account validation via win32security.LogonUser
    (pywin32). LOGON32_LOGON_NETWORK (not LOGON32_LOGON_INTERACTIVE) is
    used deliberately: it validates the password without loading a user
    profile or needing "Allow log on locally" rights, which is all a
    login-form check needs. domain=None targets local (SAM) accounts on
    this machine, not a domain.

    No extra privilege grant is needed to call this: the SE_TCB_NAME
    requirement LogonUser used to have was removed on Windows XP and
    later for a normal (non-Passport) logon, and the NSSM service's
    fixed account (LocalSystem -- see WindowsInstallOptions, no
    service_user field) holds that privilege anyway regardless."""
    import pywintypes
    import win32security
    try:
        handle = win32security.LogonUser(
            username, None, password,
            win32security.LOGON32_LOGON_NETWORK,
            win32security.LOGON32_PROVIDER_DEFAULT,
        )
    except pywintypes.error:
        return False
    handle.Close()
    return True


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
