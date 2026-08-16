"""Web-backend-specific configuration -- the [ldap] and [web] sections
of the same vra-config.ini format vra_editor/config.py already reads
(see that module's own load_config). Kept separate from
vra_editor/config.py itself rather than added to it, since these
sections only mean anything to the web backend, not the desktop app.
"""

import secrets
from pathlib import Path

from vra_editor.config import DEFAULT_CONFIG_PATH, load_config


def load_ldap_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict:
    """{'server': ..., 'use_ssl': bool, 'bind_pattern': ...} from the
    [ldap] section. bind_pattern is a template with {username}
    substituted from the login form -- e.g.
    'cn={username},ou=people,dc=vra,dc=local' for a generic/test
    server, or '{username}@example.org' / 'EXAMPLE\\{username}' for
    Active Directory's UPN/NetBIOS simple-bind forms. Same code path
    either way; only this config differs between dev and prod targets.

    Raises ValueError if the section or a required key is missing --
    there's no sensible default for "which LDAP server", unlike
    vra_editor.config's location keys.
    """
    parser = load_config(config_path)
    if not parser.has_section('ldap'):
        raise ValueError(f"No [ldap] section configured in {config_path}.")
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
