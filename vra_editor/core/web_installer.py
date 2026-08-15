"""Generates a self-contained shell script that deploys the web
companion app (webapp/ + frontend/) as a systemd service behind a
reverse proxy (Nginx, Apache, or none), on Linux.

Deliberately generates a script for the user to review and run
themselves with sudo, rather than making any of these changes from
inside this (unprivileged) desktop app directly -- writing systemd
units, reverse-proxy configs, and installing OS packages all need
root, and this codebase has never shelled out to do anything
privileged (see commit_to_git.py's use of dulwich instead of a git
subprocess, for the same reasoning applied elsewhere).

The script is self-extracting: bundle_dir()'s contents (webapp/, the
subset of vra_editor/ it imports, frontend/dist/, and
requirements-web.txt -- see packaging/VRA_Editor.spec for how they get
there) are tarred and base64-embedded directly in the generated
script, after a marker line. That makes the one generated .sh file
independently deployable to any Linux target, including one that
never had this desktop app installed -- e.g. an archive's admin
running VRA Editor just to generate this script, then copying it to a
separate server.
"""

import base64
import io
import shlex
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_ARCHIVE_MARKER = '__WEBAPP_BUNDLE_BELOW__'


def bundle_dir() -> Path:
    """Where the packaged webapp bundle lives -- same resolution
    pattern core/schema_validator.py's RESOURCES_DIR uses (a path
    relative to this source file's own location), which keeps working
    unmodified in a frozen PyInstaller build because the bundle's
    datas destination is chosen to mirror this same relative layout."""
    return Path(__file__).resolve().parent.parent / "resources" / "webapp_bundle"


@dataclass(frozen=True)
class InstallOptions:
    install_dir: str = '/opt/vra-editor-web'
    port: int = 8000
    service_user: str = 'root'
    config_path: str = '/root/.vra-editor/config.ini'
    reverse_proxy: str = 'nginx'  # 'nginx' | 'apache' | 'none'
    server_name: str = ''
    ldap_server: str = ''
    ldap_bind_pattern: str = ''
    ldap_use_ssl: bool = False


class BundleMissingError(Exception):
    """bundle_dir() doesn't exist or is empty -- this build wasn't
    packaged with the web app bundle (e.g. running from a dev
    checkout without the packaging step that populates it)."""


def _tar_bundle_base64(source_dir: Path) -> str:
    if not source_dir.is_dir() or not any(source_dir.iterdir()):
        raise BundleMissingError(
            f"{source_dir} doesn't exist or is empty -- this build wasn't packaged with the "
            "web app bundle (see packaging/VRA_Editor.spec)."
        )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as tar:
        for entry in sorted(source_dir.iterdir()):
            tar.add(entry, arcname=entry.name)
    # encodebytes (not b64encode) -- wraps at 76 chars like the `base64`
    # CLI tool's own default output, so the generated script doesn't
    # contain one multi-megabyte line. `base64 -d` ignores the embedded
    # newlines when decoding either way.
    return base64.encodebytes(buffer.getvalue()).decode('ascii')


def _nginx_config(options: InstallOptions) -> str:
    return f"""server {{
    listen 80;
    server_name {options.server_name};

    location / {{
        proxy_pass http://127.0.0.1:{options.port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


def _apache_config(options: InstallOptions) -> str:
    return f"""<VirtualHost *:80>
    ServerName {options.server_name}
    ProxyPreserveHost On
    ProxyPass / http://127.0.0.1:{options.port}/
    ProxyPassReverse / http://127.0.0.1:{options.port}/
</VirtualHost>
"""


def _proxy_setup_steps(options: InstallOptions) -> tuple[str, str]:
    """(dependency_check_snippet, setup_snippet) for the chosen
    reverse_proxy -- empty strings if 'none' (systemd service only,
    reachable at 127.0.0.1:{port} until the operator sets up their own
    proxy in front of it)."""
    if options.reverse_proxy == 'nginx':
        check = 'command -v nginx >/dev/null 2>&1 || MISSING="$MISSING nginx"'
        config = _nginx_config(options)
        setup = f"""echo "=== Configuring Nginx ==="
cat > /etc/nginx/sites-available/vra-editor.conf <<'NGINXEOF'
{config}NGINXEOF
ln -sf /etc/nginx/sites-available/vra-editor.conf /etc/nginx/sites-enabled/vra-editor.conf
nginx -t
systemctl reload nginx
"""
        return check, setup
    if options.reverse_proxy == 'apache':
        check = 'command -v apache2 >/dev/null 2>&1 || MISSING="$MISSING apache2"'
        config = _apache_config(options)
        setup = f"""echo "=== Configuring Apache ==="
a2enmod proxy proxy_http
cat > /etc/apache2/sites-available/vra-editor.conf <<'APACHEEOF'
{config}APACHEEOF
a2ensite vra-editor.conf
apache2ctl configtest
systemctl reload apache2
"""
        return check, setup
    return '', ''


def generate_install_script(options: InstallOptions, source_dir: Optional[Path] = None) -> bytes:
    """The full self-extracting install script, as bytes ready to
    write to disk. source_dir overrides bundle_dir() -- tests use this
    to point at a small fixture bundle instead of the real one."""
    if options.reverse_proxy not in ('nginx', 'apache', 'none'):
        raise ValueError(f"Unknown reverse_proxy: {options.reverse_proxy!r}")

    encoded_bundle = _tar_bundle_base64(source_dir or bundle_dir())
    proxy_check, proxy_setup = _proxy_setup_steps(options)

    install_dir = shlex.quote(options.install_dir)
    service_user = shlex.quote(options.service_user)
    config_path = shlex.quote(options.config_path)
    server_name = shlex.quote(options.server_name)
    ldap_server = shlex.quote(options.ldap_server)
    ldap_bind_pattern = shlex.quote(options.ldap_bind_pattern)
    ldap_use_ssl = 'true' if options.ldap_use_ssl else 'false'

    proxy_summary = {
        'nginx': f'Reverse proxy: Nginx, listening on :80 for {options.server_name}',
        'apache': f'Reverse proxy: Apache, listening on :80 for {options.server_name}',
        'none': f'No reverse proxy configured -- reachable at http://127.0.0.1:{options.port} only.',
    }[options.reverse_proxy]

    script = f"""#!/bin/bash
# Generated by VRA Editor's "Install web companion" dialog.
#
# Deploys the VRA Editor web companion app as a systemd service on
# this machine. Review this script before running it -- it makes real
# changes: it may install OS packages (with your confirmation), writes
# a systemd unit, writes files under {options.install_dir} and
# /etc/systemd/system/, and (if a reverse proxy was chosen) a site
# config for it.
#
# TLS/certificates are NOT configured by this script -- that's your
# reverse proxy's own job, deliberately out of scope here.
set -euo pipefail

INSTALL_DIR={install_dir}
SERVICE_USER={service_user}
CONFIG_PATH={config_path}
PORT={options.port}
SERVER_NAME={server_name}
LDAP_SERVER={ldap_server}
LDAP_BIND_PATTERN={ldap_bind_pattern}
LDAP_USE_SSL={ldap_use_ssl}

if [ "$EUID" -ne 0 ]; then
  echo "This script needs root -- run it with: sudo bash $0" >&2
  exit 1
fi

echo "=== Checking dependencies ==="
MISSING=""
command -v python3 >/dev/null 2>&1 || MISSING="$MISSING python3"
python3 -c "import venv" >/dev/null 2>&1 || MISSING="$MISSING python3-venv"
{proxy_check}

if [ -n "$MISSING" ]; then
  echo "Missing packages:$MISSING"
  read -r -p "Install them now with apt? [y/N] " REPLY
  if [[ "$REPLY" =~ ^[Yy]$ ]]; then
    apt-get update
    apt-get install -y $MISSING
  else
    echo "Install these yourself, then re-run this script: apt-get install -y$MISSING" >&2
    exit 1
  fi
fi

echo "=== Extracting web app to $INSTALL_DIR ==="
mkdir -p "$INSTALL_DIR"
ARCHIVE_LINE=$(grep -an "^{_ARCHIVE_MARKER}$" "$0" | head -1 | cut -d: -f1)
tail -n +$((ARCHIVE_LINE + 1)) "$0" | base64 -d | tar xz -C "$INSTALL_DIR"

echo "=== Setting up Python virtual environment ==="
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements-web.txt" -q

echo "=== Configuring $CONFIG_PATH ==="
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
python3 - "$CONFIG_PATH" "$SECRET_KEY" "$LDAP_SERVER" "$LDAP_BIND_PATTERN" "$LDAP_USE_SSL" <<'PYEOF'
import configparser
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
secret_key, ldap_server, ldap_bind_pattern, ldap_use_ssl = sys.argv[2:6]

parser = configparser.ConfigParser()
if config_path.exists():
    parser.read(config_path)

parser['ldap'] = {{
    'server': ldap_server,
    'bind_pattern': ldap_bind_pattern,
    'use_ssl': ldap_use_ssl,
}}
if not parser.has_section('web'):
    parser['web'] = {{}}
if not parser['web'].get('secret_key', '').strip():
    parser['web']['secret_key'] = secret_key

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, 'w') as f:
    parser.write(f)
print(f"Wrote {{config_path}}")
PYEOF

echo "=== Installing systemd service ==="
cat > /etc/systemd/system/vra-editor-web.service <<UNITEOF
[Unit]
Description=VRA Editor web companion
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment=VRA_CONFIG_PATH=$CONFIG_PATH
ExecStart=$INSTALL_DIR/venv/bin/waitress-serve --host=127.0.0.1 --port=$PORT --call webapp.wsgi:create_app_from_env
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNITEOF

systemctl daemon-reload
systemctl enable --now vra-editor-web

{proxy_setup}
echo
echo "=== Done ==="
echo "{proxy_summary}"
echo "Service status: systemctl status vra-editor-web"
echo "Logs:           journalctl -u vra-editor-web -f"
echo "Config file:    $CONFIG_PATH"
echo
echo "Note: TLS/certificates were not configured. Set those up on your reverse proxy separately."

exit 0
{_ARCHIVE_MARKER}
{encoded_bundle}
"""
    return script.encode('utf-8')
