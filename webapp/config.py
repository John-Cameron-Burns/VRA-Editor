"""Web-backend-specific configuration -- the [ldap] and [web] sections
of the same vra-config.ini format vra_editor/config.py already reads
(see that module's own load_config). Kept separate from
vra_editor/config.py itself rather than added to it, since these
sections only mean anything to the web backend, not the desktop app.
"""

import secrets
from pathlib import Path
from typing import Optional

from vra_editor.config import DEFAULT_CONFIG_PATH, load_config


def load_ldap_config(config_path: Path = DEFAULT_CONFIG_PATH) -> Optional[dict]:
    """{'server': ..., 'use_ssl': bool, 'bind_pattern': ...} from the
    [ldap] section, or None if [ldap] simply isn't configured at all --
    LDAP is optional now that local-OS-account auth (see auth.py) can
    stand in for it, or the two can be configured together. bind_pattern
    is a template with {username} substituted from the login form --
    e.g. 'cn={username},ou=people,dc=vra,dc=local' for a generic/test
    server, or '{username}@example.org' / 'EXAMPLE\\{username}' for
    Active Directory's UPN/NetBIOS simple-bind forms. Same code path
    either way; only this config differs between dev and prod targets.

    Still raises ValueError if [ldap] IS present but missing a required
    key -- a section that's there-but-broken is a misconfiguration, not
    "LDAP disabled", unlike vra_editor.config's location keys (which do
    have sensible defaults).
    """
    parser = load_config(config_path)
    if not parser.has_section('ldap'):
        return None
    section = parser['ldap']
    server = section.get('server', '').strip()
    bind_pattern = section.get('bind_pattern', '').strip()
    if not server or not bind_pattern:
        raise ValueError(f"[ldap] section in {config_path} needs both 'server' and 'bind_pattern'.")
    return {
        'server': server,
        'use_ssl': section.getboolean('use_ssl', fallback=False),
        'bind_pattern': bind_pattern,
    }


def local_auth_enabled(config_path: Path = DEFAULT_CONFIG_PATH) -> bool:
    """True iff [local_auth] enabled = true -- see auth.py's
    _authenticate_local for what that actually checks credentials
    against (PAM on Linux, local Windows accounts on Windows)."""
    parser = load_config(config_path)
    if not parser.has_section('local_auth'):
        return False
    return parser['local_auth'].getboolean('enabled', fallback=False)


def validate_auth_config(config_path: Path = DEFAULT_CONFIG_PATH) -> None:
    """Raises ValueError if config_path configures neither LDAP nor
    local-account auth -- meant to be called once at app startup (see
    app.py's create_app) so a deployment with no way for anyone to log
    in fails loudly at process start, not silently on every user's
    first login attempt."""
    ldap_cfg = load_ldap_config(config_path)  # may itself raise ValueError
    if ldap_cfg is None and not local_auth_enabled(config_path):
        raise ValueError(
            f"No authentication method configured in {config_path} -- set [ldap] "
            "server/bind_pattern and/or [local_auth] enabled = true."
        )


def load_web_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """{'secret_key': ...} from the [web] section -- falls back to a
    random key generated fresh each call if unset, which is fine for a
    single dev process but means signed sessions won't survive a
    restart; set secret_key explicitly in vra-config.ini for anything
    longer-lived than local development."""
    parser = load_config(config_path)
    secret_key = ''
    if parser.has_section('web'):
        secret_key = parser['web'].get('secret_key', '').strip()
    return {'secret_key': secret_key or secrets.token_hex(32)}
