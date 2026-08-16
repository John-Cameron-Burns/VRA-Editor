"""Generates a self-contained script that deploys the web companion
app (webapp/ + frontend/) as a service behind a reverse proxy, for the
user to review and run themselves (with sudo on Linux, elevated on
Windows) -- rather than making any of these changes from inside this
(unprivileged) desktop app directly. Writing systemd units/NSSM
services, reverse-proxy configs, and installing OS packages all need
root/admin, and this codebase has never shelled out to do anything
privileged itself (see commit_to_git.py's use of dulwich instead of a
git subprocess, for the same reasoning applied elsewhere).

Two platforms, two generator functions sharing one bundle:
  - generate_install_script (Linux): bash + systemd + Nginx/Apache/none.
  - generate_windows_install_script (Windows): PowerShell + NSSM (a
    vendored service-wrapper binary, see nssm_path()) + IIS/none.

Both are self-extracting: bundle_dir()'s contents (webapp/, the subset
of vra_editor/ it imports, frontend/dist/, and requirements-web.txt --
see packaging/VRA_Editor.spec for how they get there) are archived and
base64-embedded directly in the generated script (tar.gz for Linux,
since it always has `tar`; zip for Windows, since PowerShell's
Expand-Archive is built in but there's no universal tar). That makes
the one generated file independently deployable to any target of that
OS, including one that never had this desktop app installed -- e.g.
an archive's admin running VRA Editor just to generate the script,
then copying it to a separate server.
"""

import base64
import io
import shlex
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

_ARCHIVE_MARKER = '__WEBAPP_BUNDLE_BELOW__'

# Shared verbatim by both generate_install_script and
# generate_windows_install_script -- pure stdlib (configparser/socket/
# pathlib/urllib), so it runs identically under either platform's
# python with no changes. Deliberately reads the CONFIG FILE ON DISK
# after the config-merge step, not the dialog's own field values --
# that's the only way to also catch problems in whatever this install
# preserved from an existing config.ini (see the config-merge step's
# own "blank field leaves the existing value alone" behavior), not
# just what this particular run's operator typed in.
#
# Everything here is a warning, never a hard failure: the service
# still gets installed and started either way, since e.g. an
# unreachable LDAP server might be a temporary/firewall-not-open-yet
# state, and local auth (if enabled) might be the operator's real,
# intended path regardless of whatever LDAP's own state is.
#
# Known limitation, not solved here: the [locations] writability probe
# is a plain blocking filesystem call with no timeout of its own --
# for a UNC path on a genuinely offline server, SMB's own client-side
# timeout (often 20-30+ seconds) applies per entry, so a handful of
# locations all pointing at the same down server can make this step
# feel stalled for a while rather than failing fast.
_CONFIG_SANITY_CHECK_SCRIPT = """import configparser
import socket
import sys
from pathlib import Path
from urllib.parse import urlparse

config_path = Path(sys.argv[1])
parser = configparser.ConfigParser()
if config_path.exists():
    parser.read(config_path)

warnings = []

if parser.has_section('ldap'):
    bind_pattern = parser['ldap'].get('bind_pattern', '')
    try:
        bind_pattern.format(username='test')
    except (KeyError, IndexError) as e:
        warnings.append(
            "[ldap] bind_pattern %r does not substitute correctly (%s: %s) -- every LDAP "
            "login will fail. Expected a {username} placeholder, e.g. "
            "'cn={username},ou=people,dc=example,dc=org'."
            % (bind_pattern, type(e).__name__, e)
        )

    server = parser['ldap'].get('server', '').strip()
    if server:
        parsed = urlparse(server)
        host = parsed.hostname
        port = parsed.port or (636 if parsed.scheme == 'ldaps' else 389)
        if host:
            try:
                with socket.create_connection((host, port), timeout=5):
                    pass
            except OSError as e:
                warnings.append(
                    "[ldap] server %r is not reachable right now (%s) -- LDAP logins will "
                    "fail until this is fixed." % (server, e)
                )
        else:
            warnings.append("[ldap] server %r doesn't look like a valid LDAP URL." % server)

if parser.has_section('locations'):
    for key, value in parser['locations'].items():
        value = value.strip()
        if not value:
            continue
        path = Path(value)
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / '.vra-editor-write-test'
            probe.write_text('x')
            probe.unlink()
        except OSError as e:
            warnings.append(
                "[locations] %s = %r is not writable by this service account (%s)."
                % (key, value, e)
            )

if warnings:
    print("")
    print("=== Configuration warnings (service installed and started anyway) ===")
    for w in warnings:
        print("  - " + w)
    print("Fix these, then restart the service once resolved.")
else:
    print("Configuration check: [ldap]/[locations] entries all checked out OK.")
"""


def bundle_dir() -> Path:
    """Where the packaged webapp bundle lives -- same resolution
    pattern core/schema_validator.py's RESOURCES_DIR uses (a path
    relative to this source file's own location), which keeps working
    unmodified in a frozen PyInstaller build because the bundle's
    datas destination is chosen to mirror this same relative layout."""
    return Path(__file__).resolve().parent.parent / "resources" / "webapp_bundle"


def nssm_path() -> Path:
    """The vendored NSSM binary (nssm.cc) -- Windows-only, kept as its
    own resource rather than inside bundle_dir() so Linux's own
    archive never carries a Windows binary it has no use for (see
    generate_windows_install_script, the only caller)."""
    return Path(__file__).resolve().parent.parent / "resources" / "nssm.exe"


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
    local_auth_enabled: bool = False
    # [locations] -- all optional. Blank ones are left alone rather than
    # written as empty, so pointing config_path at an existing, already-
    # configured config.ini and leaving these blank doesn't wipe it out;
    # see the config-merge step. location_app_data is the "clutter"
    # folder -- sharing it with a desktop install's own is what unifies
    # the git-backed revision history behind Audits across both.
    location_edit: str = ''
    location_ingest: str = ''
    location_pending: str = ''
    location_rejected: str = ''
    location_reviewed: str = ''
    location_released: str = ''
    location_app_data: str = ''


@dataclass(frozen=True)
class WindowsInstallOptions:
    install_dir: str = r'C:\VRA-Editor-Web'
    port: int = 8000
    config_path: str = r'C:\ProgramData\VRA-Editor\config.ini'
    reverse_proxy: str = 'iis'  # 'iis' | 'none'
    server_name: str = ''
    site_name: str = 'VRA-Editor-Web'
    ldap_server: str = ''
    ldap_bind_pattern: str = ''
    ldap_use_ssl: bool = False
    local_auth_enabled: bool = False
    # No service_user: the NSSM service runs as LocalSystem, deliberately --
    # see this module's own module docstring reasoning replicated in
    # generate_windows_install_script's docstring below (no credential
    # prompts, no password ever embedded in the generated script).
    # [locations] -- see InstallOptions's own comment; same semantics.
    # LocalSystem has no mapped network drives of its own (those are a
    # per-interactive-session thing), so a network-shared archive needs
    # a UNC path here (\\server\share\edit), never a drive letter.
    location_edit: str = ''
    location_ingest: str = ''
    location_pending: str = ''
    location_rejected: str = ''
    location_reviewed: str = ''
    location_released: str = ''
    location_app_data: str = ''


class BundleMissingError(Exception):
    """bundle_dir() doesn't exist or is empty -- this build wasn't
    packaged with the web app bundle (e.g. running from a dev
    checkout without the packaging step that populates it)."""


class NssmMissingError(Exception):
    """nssm_path() doesn't exist -- this build wasn't packaged with
    the vendored NSSM binary (Windows only; see packaging/VRA_Editor.spec)."""


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


def _zip_bundle_base64(source_dir: Path, extra_files: Sequence[Path] = ()) -> str:
    """Windows counterpart to _tar_bundle_base64 -- a zip (not tar.gz),
    since PowerShell's Expand-Archive handles zip natively with no
    external tooling, unlike tar which isn't guaranteed present.
    extra_files are added at the archive root alongside source_dir's
    own contents -- used to fold nssm.exe in next to the web app
    payload, so the generated script only has one archive to extract."""
    if not source_dir.is_dir() or not any(source_dir.iterdir()):
        raise BundleMissingError(
            f"{source_dir} doesn't exist or is empty -- this build wasn't packaged with the "
            "web app bundle (see packaging/VRA_Editor.spec)."
        )
    for extra in extra_files:
        if not extra.is_file():
            raise NssmMissingError(
                f"{extra} doesn't exist -- this build wasn't packaged with the vendored NSSM "
                "binary (see packaging/VRA_Editor.spec)."
            )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
        for entry in sorted(source_dir.rglob('*')):
            if entry.is_file():
                zf.write(entry, arcname=str(entry.relative_to(source_dir)))
        for extra in extra_files:
            zf.write(extra, arcname=extra.name)
    return base64.encodebytes(buffer.getvalue()).decode('ascii')


def _ps_quote(value: str) -> str:
    """Safely embeds value as a single-quoted PowerShell string
    literal -- single-quoted PS strings treat everything literally
    except a doubled '' for one literal quote, the PowerShell
    equivalent of shlex.quote() for bash."""
    return "'" + value.replace("'", "''") + "'"


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
    local_auth_enabled = 'true' if options.local_auth_enabled else 'false'
    loc_edit = shlex.quote(options.location_edit)
    loc_ingest = shlex.quote(options.location_ingest)
    loc_pending = shlex.quote(options.location_pending)
    loc_rejected = shlex.quote(options.location_rejected)
    loc_reviewed = shlex.quote(options.location_reviewed)
    loc_released = shlex.quote(options.location_released)
    loc_app_data = shlex.quote(options.location_app_data)

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
LOCAL_AUTH_ENABLED={local_auth_enabled}
LOC_EDIT={loc_edit}
LOC_INGEST={loc_ingest}
LOC_PENDING={loc_pending}
LOC_REJECTED={loc_rejected}
LOC_REVIEWED={loc_reviewed}
LOC_RELEASED={loc_released}
LOC_APP_DATA={loc_app_data}

if [ "$EUID" -ne 0 ]; then
  echo "This script needs root -- run it with: sudo bash $0" >&2
  exit 1
fi

warn_if_local_auth_needs_root() {{
  if [ "$LOCAL_AUTH_ENABLED" = "true" ] && [ "$SERVICE_USER" != "root" ]; then
    echo "WARNING: Local-account login is enabled, but the service will run as" >&2
    echo "         '$SERVICE_USER', not root. Checking another user's password via PAM" >&2
    echo "         normally requires root (or membership in the 'shadow' group,"  >&2
    echo "         depending on distro/PAM config) to read /etc/shadow. Local-account" >&2
    echo "         logins will likely fail until this is fixed -- either run the" >&2
    echo "         service as root, or add '$SERVICE_USER' to the 'shadow' group." >&2
  fi
}}
warn_if_local_auth_needs_root

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
python3 - "$CONFIG_PATH" "$SECRET_KEY" "$LDAP_SERVER" "$LDAP_BIND_PATTERN" "$LDAP_USE_SSL" "$LOCAL_AUTH_ENABLED" \
    "$LOC_EDIT" "$LOC_INGEST" "$LOC_PENDING" "$LOC_REJECTED" "$LOC_REVIEWED" "$LOC_RELEASED" "$LOC_APP_DATA" <<'PYEOF'
import configparser
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
secret_key, ldap_server, ldap_bind_pattern, ldap_use_ssl, local_auth_enabled = sys.argv[2:7]
loc_edit, loc_ingest, loc_pending, loc_rejected, loc_reviewed, loc_released, loc_app_data = sys.argv[7:14]

parser = configparser.ConfigParser()
if config_path.exists():
    parser.read(config_path)

if ldap_server.strip():
    parser['ldap'] = {{
        'server': ldap_server,
        'bind_pattern': ldap_bind_pattern,
        'use_ssl': ldap_use_ssl,
    }}
elif parser.has_section('ldap'):
    # Re-running the installer with LDAP now unticked -- remove the
    # stale section instead of leaving a half-configured one behind.
    parser.remove_section('ldap')

parser['local_auth'] = {{'enabled': local_auth_enabled}}

# [locations] -- a blank field here means "leave whatever's already in
# the config alone" (not "clear it"), so pointing this install at an
# existing, already-configured config.ini and leaving these blank
# doesn't wipe out its locations; only a field the operator actually
# filled in overwrites the corresponding key.
location_values = {{
    'edit': loc_edit, 'ingest': loc_ingest, 'pending': loc_pending,
    'rejected': loc_rejected, 'reviewed': loc_reviewed, 'released': loc_released,
    'app_data': loc_app_data,
}}
if not parser.has_section('locations'):
    parser['locations'] = {{}}
for key, value in location_values.items():
    if value.strip():
        parser['locations'][key] = value

if not parser.has_section('web'):
    parser['web'] = {{}}
if not parser['web'].get('secret_key', '').strip():
    parser['web']['secret_key'] = secret_key

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, 'w') as f:
    parser.write(f)
print(f"Wrote {{config_path}}")
PYEOF

echo "=== Checking configuration ==="
python3 - "$CONFIG_PATH" <<'SANITYEOF'
{_CONFIG_SANITY_CHECK_SCRIPT}
SANITYEOF

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
warn_if_local_auth_needs_root

exit 0
{_ARCHIVE_MARKER}
{encoded_bundle}
"""
    return script.encode('utf-8')


# ----------------------------------------------------------------------
# Windows (PowerShell + NSSM + IIS)
#
# Built from plain (non-f) string templates with %%TOKEN%% placeholders,
# substituted via .replace(), rather than Python f-strings -- PowerShell
# leans on { } for every block (if/else, functions, hashtables...), and
# an f-string would need doubled {{ }} at every one of those, which is
# both easy to get wrong and hard to review. Plain strings sidestep that
# entirely: no character in real PowerShell source collides with %%.
# ----------------------------------------------------------------------

_WINDOWS_CONFIG_MERGE_SCRIPT = """import configparser
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
secret_key, ldap_server, ldap_bind_pattern, ldap_use_ssl, local_auth_enabled = sys.argv[2:7]
loc_edit, loc_ingest, loc_pending, loc_rejected, loc_reviewed, loc_released, loc_app_data = sys.argv[7:14]

parser = configparser.ConfigParser()
if config_path.exists():
    parser.read(config_path)

if ldap_server.strip():
    parser['ldap'] = {
        'server': ldap_server,
        'bind_pattern': ldap_bind_pattern,
        'use_ssl': ldap_use_ssl,
    }
elif parser.has_section('ldap'):
    # Re-running the installer with LDAP now unticked -- remove the
    # stale section instead of leaving a half-configured one behind.
    parser.remove_section('ldap')

parser['local_auth'] = {'enabled': local_auth_enabled}

# [locations] -- a blank field here means "leave whatever's already in
# the config alone" (not "clear it"), so pointing this install at an
# existing, already-configured config.ini and leaving these blank
# doesn't wipe out its locations; only a field the operator actually
# filled in overwrites the corresponding key.
location_values = {
    'edit': loc_edit, 'ingest': loc_ingest, 'pending': loc_pending,
    'rejected': loc_rejected, 'reviewed': loc_reviewed, 'released': loc_released,
    'app_data': loc_app_data,
}
if not parser.has_section('locations'):
    parser['locations'] = {}
for key, value in location_values.items():
    if value.strip():
        parser['locations'][key] = value

if not parser.has_section('web'):
    parser['web'] = {}
if not parser['web'].get('secret_key', '').strip():
    parser['web']['secret_key'] = secret_key

config_path.parent.mkdir(parents=True, exist_ok=True)
with open(config_path, 'w') as f:
    parser.write(f)
print(f"Wrote {config_path}")
"""

_WINDOWS_INSTALL_SCRIPT_TEMPLATE = r"""# Generated by VRA Editor's "Install web companion" dialog.
#
# Deploys the VRA Editor web companion app as a Windows service (via
# NSSM -- see nssm_path()'s own docstring in web_installer.py for why)
# on this machine, optionally behind IIS as a reverse proxy. Review
# this script before running it -- it makes real changes: it writes
# files under %%INSTALL_DIR%% and the chosen config path, installs a
# Windows service, and (if IIS was chosen) a new IIS site alongside
# whatever else this machine already serves.
#
# TLS/certificates are NOT configured by this script -- that's your
# reverse proxy's own job, deliberately out of scope here.

#Requires -RunAsAdministrator

$ErrorActionPreference = 'Stop'

function Install-VraEditorWeb {
    param([string]$BundleBase64)

    $InstallDir = %%INSTALL_DIR%%
    $ConfigPath = %%CONFIG_PATH%%
    $Port = %%PORT%%
    $ServerName = %%SERVER_NAME%%
    $SiteName = %%SITE_NAME%%
    $LdapServer = %%LDAP_SERVER%%
    $LdapBindPattern = %%LDAP_BIND_PATTERN%%
    $LdapUseSsl = %%LDAP_USE_SSL%%
    $LocalAuthEnabled = %%LOCAL_AUTH_ENABLED%%
    $LocEdit = %%LOC_EDIT%%
    $LocIngest = %%LOC_INGEST%%
    $LocPending = %%LOC_PENDING%%
    $LocRejected = %%LOC_REJECTED%%
    $LocReviewed = %%LOC_REVIEWED%%
    $LocReleased = %%LOC_RELEASED%%
    $LocAppData = %%LOC_APP_DATA%%
    $ProxySummary = %%PROXY_SUMMARY%%

    $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)) {
        Write-Error "This script needs to be run as Administrator."
        exit 1
    }

    # Re-running this script against an existing install is a real,
    # expected case (picking up a new build, changing a setting) -- but
    # NSSM keeps its own nssm.exe open for as long as the service is
    # running, and Windows won't let Expand-Archive overwrite a file
    # that's still in use. Stop and remove any prior VraEditorWeb
    # service first so extraction below can't hit that. sc.exe (not
    # the bundled nssm.exe) does the removal, since an old install
    # might be at a different $InstallDir than this run's -- the
    # service name is the only thing guaranteed constant between runs.
    $existingService = Get-Service -Name 'VraEditorWeb' -ErrorAction SilentlyContinue
    if ($existingService) {
        Write-Host "=== Found an existing VraEditorWeb service -- stopping and removing it first ==="
        Stop-Service -Name 'VraEditorWeb' -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        sc.exe delete VraEditorWeb | Out-Null
        Start-Sleep -Seconds 1
    }

    Write-Host "=== Checking dependencies ==="
    $missing = @()
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        $missing += 'Python 3 (https://www.python.org/downloads/windows/) -- add it to PATH during install'
    }
%%PROXY_DEPENDENCY_CHECK%%
    if ($missing.Count -gt 0) {
        Write-Host "Missing:"
        foreach ($item in $missing) { Write-Host "  - $item" }
        Write-Host "Install these, then re-run this script."
        exit 1
    }

    Write-Host "=== Extracting web app to $InstallDir ==="
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $zipBytes = [Convert]::FromBase64String($BundleBase64)
    $tempZip = [System.IO.Path]::GetTempFileName() + '.zip'
    [System.IO.File]::WriteAllBytes($tempZip, $zipBytes)
    Expand-Archive -Path $tempZip -DestinationPath $InstallDir -Force
    Remove-Item $tempZip

    Write-Host "=== Setting up Python virtual environment ==="
    python -m venv "$InstallDir\venv"
    & "$InstallDir\venv\Scripts\pip.exe" install --upgrade pip -q
    & "$InstallDir\venv\Scripts\pip.exe" install -r "$InstallDir\requirements-web.txt" -q

    Write-Host "=== Configuring $ConfigPath ==="
    $secretKey = & "$InstallDir\venv\Scripts\python.exe" -c "import secrets; print(secrets.token_hex(32))"
    $mergeScript = @'
%%MERGE_SCRIPT%%
'@
    $mergeScriptPath = [System.IO.Path]::GetTempFileName() + '.py'
    [System.IO.File]::WriteAllText($mergeScriptPath, $mergeScript, (New-Object System.Text.UTF8Encoding $false))
    $ldapUseSslArg = if ($LdapUseSsl) { 'true' } else { 'false' }
    $localAuthEnabledArg = if ($LocalAuthEnabled) { 'true' } else { 'false' }
    & "$InstallDir\venv\Scripts\python.exe" $mergeScriptPath $ConfigPath $secretKey $LdapServer $LdapBindPattern $ldapUseSslArg $localAuthEnabledArg `
        $LocEdit $LocIngest $LocPending $LocRejected $LocReviewed $LocReleased $LocAppData
    Remove-Item $mergeScriptPath

    Write-Host "=== Checking configuration ==="
    $sanityScript = @'
%%SANITY_CHECK_SCRIPT%%
'@
    $sanityScriptPath = [System.IO.Path]::GetTempFileName() + '.py'
    [System.IO.File]::WriteAllText($sanityScriptPath, $sanityScript, (New-Object System.Text.UTF8Encoding $false))
    & "$InstallDir\venv\Scripts\python.exe" $sanityScriptPath $ConfigPath
    Remove-Item $sanityScriptPath

    # Local-account login (if enabled) uses win32security.LogonUser, which
    # LocalSystem can call for any local account without extra privilege
    # grants -- unlike PAM on Linux, no service-account warning is needed here.
    Write-Host "=== Installing Windows service (NSSM) ==="
    $nssmExe = Join-Path $InstallDir 'nssm.exe'
    $pythonExe = Join-Path $InstallDir 'venv\Scripts\python.exe'
    $serviceArgs = "-m waitress --host=127.0.0.1 --port=$Port --call webapp.wsgi:create_app_from_env"
    & $nssmExe install VraEditorWeb $pythonExe $serviceArgs
    & $nssmExe set VraEditorWeb AppDirectory $InstallDir
    & $nssmExe set VraEditorWeb AppEnvironmentExtra "VRA_CONFIG_PATH=$ConfigPath"
    & $nssmExe set VraEditorWeb AppStdout (Join-Path $InstallDir 'service.log')
    & $nssmExe set VraEditorWeb AppStderr (Join-Path $InstallDir 'service.log')
    & $nssmExe start VraEditorWeb

%%PROXY_SETUP%%
    Write-Host ""
    Write-Host "=== Done ==="
    Write-Host $ProxySummary
    Write-Host "Service status: Get-Service VraEditorWeb"
    Write-Host "Logs:           $InstallDir\service.log"
    Write-Host "Config file:    $ConfigPath"
    Write-Host ""
    Write-Host "Note: TLS/certificates were not configured. Set those up on your reverse proxy separately."
}

$bundleBase64 = @'
%%BUNDLE_BASE64%%
'@
Install-VraEditorWeb -BundleBase64 $bundleBase64
"""


def _iis_web_config(options: WindowsInstallOptions) -> str:
    """The new IIS site's whole web.config -- an ARR reverse-proxy
    rewrite rule forwarding everything to the local waitress process.
    {R:1} is IIS URL Rewrite's own back-reference syntax (capture
    group 1 from the match pattern), not a Python format field -- this
    is a plain string, not an f-string, specifically so a literal
    {R:1} doesn't need escaping."""
    template = """<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="ReverseProxyToVraEditorWeb" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://127.0.0.1:%%PORT%%/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
"""
    return template.replace('%%PORT%%', str(options.port))


def _windows_proxy_steps(options: WindowsInstallOptions) -> tuple[str, str, str]:
    """(dependency_check_snippet, setup_snippet, summary_line) for the
    chosen reverse_proxy -- empty snippets if 'none' (NSSM service
    only, reachable at 127.0.0.1:{port} until the operator sets up
    their own proxy in front of it).

    IIS itself, URL Rewrite, and Application Request Routing are
    checked and reported (with direct download links) rather than
    auto-installed -- unlike Linux's apt-get offer, there's no
    universal Windows package manager to lean on, and enabling IIS
    itself is enough of a system change (sometimes needing a reboot on
    client SKUs) that "tell the operator exactly what to get" is the
    safer default, not a choice that needs asking. ARR's own
    reverse-proxy feature is off by default even once the module is
    installed -- the setup snippet turns it on explicitly rather than
    assuming module presence implies it's active."""
    if options.reverse_proxy != 'iis':
        summary = f'No reverse proxy configured -- reachable at http://127.0.0.1:{options.port} only.'
        return '', '', summary

    check = """    if (-not (Get-Service -Name 'W3SVC' -ErrorAction SilentlyContinue)) {
        $missing += 'IIS (enable the Web Server (IIS) role/feature, then re-run this script)'
    } else {
        Import-Module WebAdministration -ErrorAction SilentlyContinue
        if (-not (Get-WebGlobalModule -Name 'RewriteModule' -ErrorAction SilentlyContinue)) {
            $missing += 'IIS URL Rewrite module (https://www.iis.net/downloads/microsoft/url-rewrite)'
        }
        if (-not (Get-WebGlobalModule -Name 'ApplicationRequestRouting' -ErrorAction SilentlyContinue)) {
            $missing += 'IIS Application Request Routing (https://www.iis.net/downloads/microsoft/application-request-routing)'
        }
    }
"""

    web_config_xml = _iis_web_config(options)
    physical_path = 'C:\\inetpub\\' + options.site_name

    setup_template = """    Write-Host "=== Configuring IIS ==="
    Import-Module WebAdministration
    $sitePath = %%PHYSICAL_PATH%%
    New-Item -ItemType Directory -Force -Path $sitePath | Out-Null
    $webConfigXml = @'
%%WEB_CONFIG_XML%%
'@
    [System.IO.File]::WriteAllText((Join-Path $sitePath 'web.config'), $webConfigXml, (New-Object System.Text.UTF8Encoding $false))

    Set-WebConfigurationProperty -pspath 'MACHINE/WEBROOT/APPHOST' -filter "system.webServer/proxy" -name "enabled" -value "True"

    if (Get-Website -Name %%SITE_NAME%% -ErrorAction SilentlyContinue) {
        Remove-Website -Name %%SITE_NAME%%
    }
    New-Website -Name %%SITE_NAME%% -PhysicalPath $sitePath -Port 80 -HostHeader %%SERVER_NAME%%
"""
    setup = (setup_template
             .replace('%%PHYSICAL_PATH%%', _ps_quote(physical_path))
             .replace('%%WEB_CONFIG_XML%%', web_config_xml)
             .replace('%%SITE_NAME%%', _ps_quote(options.site_name))
             .replace('%%SERVER_NAME%%', _ps_quote(options.server_name)))

    summary = f'Reverse proxy: IIS, listening on :80 for {options.server_name} (site "{options.site_name}")'
    return check, setup, summary


def generate_windows_install_script(options: WindowsInstallOptions, source_dir: Optional[Path] = None) -> bytes:
    """The full self-extracting PowerShell install script, as bytes
    ready to write to disk (save with a .ps1 extension). source_dir
    overrides bundle_dir() -- tests use this to point at a small
    fixture bundle instead of the real one. Also needs nssm_path() to
    exist (raises NssmMissingError otherwise, via _zip_bundle_base64).

    The service runs as LocalSystem (NSSM's own default) rather than a
    named account -- deliberately, so this never needs to ask for or
    embed a service-account password anywhere; the config path
    defaults to a machine-wide ProgramData location rather than
    reusing a specific user's profile for the same reason (see
    WindowsInstallOptions's own docstring)."""
    if options.reverse_proxy not in ('iis', 'none'):
        raise ValueError(f"Unknown reverse_proxy: {options.reverse_proxy!r}")

    encoded_bundle = _zip_bundle_base64(source_dir or bundle_dir(), extra_files=(nssm_path(),))
    proxy_check, proxy_setup, proxy_summary = _windows_proxy_steps(options)
    ldap_use_ssl_literal = '$true' if options.ldap_use_ssl else '$false'

    substitutions = {
        '%%INSTALL_DIR%%': _ps_quote(options.install_dir),
        '%%CONFIG_PATH%%': _ps_quote(options.config_path),
        '%%PORT%%': str(options.port),
        '%%SERVER_NAME%%': _ps_quote(options.server_name),
        '%%SITE_NAME%%': _ps_quote(options.site_name),
        '%%LDAP_SERVER%%': _ps_quote(options.ldap_server),
        '%%LDAP_BIND_PATTERN%%': _ps_quote(options.ldap_bind_pattern),
        '%%LDAP_USE_SSL%%': ldap_use_ssl_literal,
        '%%LOCAL_AUTH_ENABLED%%': '$true' if options.local_auth_enabled else '$false',
        '%%LOC_EDIT%%': _ps_quote(options.location_edit),
        '%%LOC_INGEST%%': _ps_quote(options.location_ingest),
        '%%LOC_PENDING%%': _ps_quote(options.location_pending),
        '%%LOC_REJECTED%%': _ps_quote(options.location_rejected),
        '%%LOC_REVIEWED%%': _ps_quote(options.location_reviewed),
        '%%LOC_RELEASED%%': _ps_quote(options.location_released),
        '%%LOC_APP_DATA%%': _ps_quote(options.location_app_data),
        '%%PROXY_DEPENDENCY_CHECK%%': proxy_check,
        '%%PROXY_SETUP%%': proxy_setup,
        # _ps_quote, not raw text -- this becomes $ProxySummary = ...,
        # then Write-Host $ProxySummary (a plain variable reference)
        # rather than being spliced straight into a Write-Host "..."
        # line, which would break if server_name/site_name ever
        # contained a literal double-quote (see
        # test_no_unescaped_nested_double_quotes_in_write_host_lines).
        '%%PROXY_SUMMARY%%': _ps_quote(proxy_summary),
        '%%MERGE_SCRIPT%%': _WINDOWS_CONFIG_MERGE_SCRIPT,
        '%%SANITY_CHECK_SCRIPT%%': _CONFIG_SANITY_CHECK_SCRIPT,
        '%%BUNDLE_BASE64%%': encoded_bundle,
    }

    script = _WINDOWS_INSTALL_SCRIPT_TEMPLATE
    for token, value in substitutions.items():
        script = script.replace(token, value)

    return script.encode('utf-8')
