"""Tests for vra_editor.core.web_installer -- Qt-free, so plain pytest
with no LDAP/Flask fixtures needed (unlike the rest of tests/, which
covers webapp/).

Linux: runs bash -n (and, for the main case, the actual extraction
commands) to verify the generated script isn't just Python-side
correct but genuinely valid/working bash.

Windows: no `pwsh` is available in this environment, so there's no
equivalent syntax check for the generated PowerShell here -- that gap
is real, not silently skipped (see the class docstring below). These
tests instead lean harder on content assertions and a real zip
round-trip, plus a regression test for a nested-double-quote bug a
manual review caught before these tests existed (see
test_no_unescaped_nested_double_quotes_in_write_host_lines).
"""

import base64
import re
import shutil
import subprocess
import tarfile
import zipfile

import pytest

from vra_editor.core.web_installer import (
    BundleMissingError,
    InstallOptions,
    NssmMissingError,
    WindowsInstallOptions,
    generate_install_script,
    generate_windows_install_script,
)

requires_bash = pytest.mark.skipif(shutil.which('bash') is None, reason='bash not available')


@pytest.fixture
def fixture_bundle(tmp_path):
    """A minimal stand-in for the real webapp_bundle/ -- just enough
    to prove the archive/extraction round-trip works."""
    bundle = tmp_path / 'webapp_bundle'
    (bundle / 'webapp').mkdir(parents=True)
    (bundle / 'webapp' / 'wsgi.py').write_text("print('hello from wsgi')\n")
    (bundle / 'requirements-web.txt').write_text('flask>=3.0\nwaitress>=3.0\n')
    return bundle


def _default_options(**overrides) -> InstallOptions:
    base = dict(
        install_dir='/opt/vra-editor-web',
        port=8000,
        service_user='jsmith',
        config_path='/home/jsmith/.vra-editor/config.ini',
        reverse_proxy='nginx',
        server_name='vra.example.org',
        ldap_server='ldap://ldap.example.org:389',
        ldap_bind_pattern='cn={username},ou=people,dc=example,dc=org',
        ldap_use_ssl=False,
    )
    base.update(overrides)
    return InstallOptions(**base)


def test_missing_bundle_raises(tmp_path):
    empty_dir = tmp_path / 'nonexistent'
    with pytest.raises(BundleMissingError):
        generate_install_script(_default_options(), source_dir=empty_dir)


def test_unknown_reverse_proxy_raises(fixture_bundle):
    with pytest.raises(ValueError):
        generate_install_script(_default_options(reverse_proxy='caddy'), source_dir=fixture_bundle)


def test_script_contains_correct_systemd_fields(fixture_bundle):
    script = generate_install_script(_default_options(), source_dir=fixture_bundle).decode('utf-8')
    assert 'User=$SERVICE_USER' in script
    assert 'WorkingDirectory=$INSTALL_DIR' in script
    assert 'Environment=VRA_CONFIG_PATH=$CONFIG_PATH' in script
    assert 'ExecStart=$INSTALL_DIR/venv/bin/waitress-serve --host=127.0.0.1 --port=$PORT --call webapp.wsgi:create_app_from_env' in script
    assert 'SERVICE_USER=jsmith' in script
    assert 'CONFIG_PATH=/home/jsmith/.vra-editor/config.ini' in script
    assert 'PORT=8000' in script


@pytest.mark.parametrize('proxy,expect_present,expect_absent', [
    ('nginx', ['server {', 'listen 80;', '/etc/nginx/sites-available', 'proxy_pass http://127.0.0.1:8000'],
     ['VirtualHost', '/etc/apache2']),
    ('apache', ['<VirtualHost *:80>', 'ProxyPass / http://127.0.0.1:8000/', '/etc/apache2/sites-available'],
     ['server {', '/etc/nginx']),
    ('none', [], ['server {', 'VirtualHost', '/etc/nginx', '/etc/apache2']),
])
def test_reverse_proxy_template_selection(fixture_bundle, proxy, expect_present, expect_absent):
    script = generate_install_script(_default_options(reverse_proxy=proxy), source_dir=fixture_bundle).decode('utf-8')
    for needle in expect_present:
        assert needle in script
    for needle in expect_absent:
        assert needle not in script


def test_ldap_options_reach_the_config_merge_step(fixture_bundle):
    script = generate_install_script(_default_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "LDAP_SERVER=ldap://ldap.example.org:389" in script
    assert "LDAP_BIND_PATTERN='cn={username},ou=people,dc=example,dc=org'" in script
    assert 'LDAP_USE_SSL=false' in script
    assert "parser['ldap'] = {" in script


def test_local_auth_disabled_by_default(fixture_bundle):
    script = generate_install_script(_default_options(), source_dir=fixture_bundle).decode('utf-8')
    assert 'LOCAL_AUTH_ENABLED=false' in script


def test_local_auth_enabled_reaches_config_merge_step(fixture_bundle):
    script = generate_install_script(
        _default_options(local_auth_enabled=True), source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'LOCAL_AUTH_ENABLED=true' in script
    assert "parser['local_auth'] = {'enabled': local_auth_enabled}" in script


def test_ldap_omitted_from_config_merge_when_ldap_server_blank(fixture_bundle):
    script = generate_install_script(
        _default_options(ldap_server='', ldap_bind_pattern='', local_auth_enabled=True),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    assert "LDAP_SERVER=''" in script
    assert "parser.remove_section('ldap')" in script


def test_locations_reach_the_config_merge_step(fixture_bundle):
    script = generate_install_script(
        _default_options(
            location_edit='/mnt/archive/edit', location_ingest='/mnt/archive/ingest',
            location_app_data='/mnt/archive/clutter',
        ),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'LOC_EDIT=/mnt/archive/edit' in script
    assert 'LOC_INGEST=/mnt/archive/ingest' in script
    assert 'LOC_APP_DATA=/mnt/archive/clutter' in script
    assert "location_values = {" in script
    assert "'edit': loc_edit" in script
    assert "'app_data': loc_app_data" in script


def test_locations_blank_by_default(fixture_bundle):
    script = generate_install_script(_default_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "LOC_EDIT=''" in script
    assert "LOC_APP_DATA=''" in script


@requires_bash
def test_locations_real_merge_preserves_existing_and_overwrites_filled(tmp_path, fixture_bundle):
    """Runs the ACTUAL embedded config-merge Python script against a
    real subprocess (not a static text check) to prove the "blank
    field leaves the existing value alone, a filled one overwrites it"
    semantics genuinely hold -- the whole point of not just always
    writing every key, since an operator pointing this at an existing,
    already-configured config.ini and leaving most fields blank must
    not have that config's locations wiped out."""
    config_path = tmp_path / 'config.ini'
    config_path.write_text(
        "[locations]\n"
        "edit = /old/edit\n"
        "ingest = /old/ingest\n"
        "pending = /old/pending\n"
    )

    script = generate_install_script(
        _default_options(
            config_path=str(config_path),
            location_edit='/new/edit',  # overwrite this one
            # ingest/pending left blank -- must survive untouched
            location_reviewed='/new/reviewed',  # a brand new key
        ),
        source_dir=fixture_bundle,
    )
    script_path = tmp_path / 'install.sh'
    script_path.write_bytes(script)

    # Extract just the config-merge step (between the "Configuring"
    # echo and the matching PYEOF) and run it directly, skipping
    # everything before it (root check, dependency check, extraction)
    # that isn't relevant to this and would need a real root/target dir.
    text = script.decode('utf-8')
    start = text.index('echo "=== Configuring')
    end = text.index('PYEOF\n', start) + len('PYEOF\n')
    snippet = text[start:end]
    merge_script_path = tmp_path / 'merge_check.sh'
    merge_script_path.write_text(
        f'#!/bin/bash\nCONFIG_PATH={config_path}\n'
        f'SECRET_KEY=x\nLDAP_SERVER=\'\'\nLDAP_BIND_PATTERN=\'\'\nLDAP_USE_SSL=false\n'
        f'LOCAL_AUTH_ENABLED=false\n'
        f"LOC_EDIT='/new/edit'\nLOC_INGEST=''\nLOC_PENDING=''\nLOC_REJECTED=''\n"
        f"LOC_REVIEWED='/new/reviewed'\nLOC_RELEASED=''\nLOC_APP_DATA=''\n"
        + snippet
    )
    result = subprocess.run(['bash', str(merge_script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    written = config_path.read_text()
    assert 'edit = /new/edit' in written        # overwritten
    assert 'ingest = /old/ingest' in written     # preserved (left blank)
    assert 'pending = /old/pending' in written   # preserved (left blank)
    assert 'reviewed = /new/reviewed' in written  # newly added


def test_linux_warns_when_local_auth_enabled_and_service_user_not_root(fixture_bundle):
    script = generate_install_script(
        _default_options(local_auth_enabled=True, service_user='jsmith'), source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'WARNING: Local-account login is enabled' in script
    # Printed once right after the dependency check, and again in the
    # final summary -- the function is defined once, called twice.
    assert script.count('warn_if_local_auth_needs_root') == 3


@requires_bash
@pytest.mark.parametrize('local_auth_enabled,service_user,expect_warning', [
    (True, 'jsmith', True),
    (True, 'root', False),
    (False, 'jsmith', False),
])
def test_local_auth_warning_actually_fires_at_runtime(
    tmp_path, fixture_bundle, local_auth_enabled, service_user, expect_warning,
):
    """Runs the real generated script's warn_if_local_auth_needs_root
    function against a real bash subprocess (not a static text check),
    to prove the runtime condition genuinely fires (or doesn't) as
    intended -- past the point where "$EUID" -ne 0 would normally exit,
    since this test isn't running as root."""
    script = generate_install_script(
        _default_options(local_auth_enabled=local_auth_enabled, service_user=service_user),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    # Extract just the SERVICE_USER/LOCAL_AUTH_ENABLED assignments and
    # the warn_if_local_auth_needs_root function definition -- everything
    # up to (not including) the root-EUID check, which would otherwise
    # exit this test subprocess immediately since it isn't running as root.
    func_start = script.index('warn_if_local_auth_needs_root() {')
    func_end = script.index('\n}\n', func_start) + len('\n}\n')
    preamble = script[script.index('SERVICE_USER='):script.index('if [ "$EUID"')]
    snippet = preamble + script[func_start:func_end] + 'warn_if_local_auth_needs_root\n'
    script_path = tmp_path / 'warn_check.sh'
    script_path.write_text('#!/bin/bash\n' + snippet)
    result = subprocess.run(['bash', str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    if expect_warning:
        assert 'WARNING: Local-account login is enabled' in result.stderr
    else:
        assert result.stderr == ''


def test_linux_no_warning_when_local_auth_disabled(fixture_bundle):
    script = generate_install_script(
        _default_options(local_auth_enabled=False, service_user='jsmith'), source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'LOCAL_AUTH_ENABLED=false' in script


def test_tls_is_never_configured(fixture_bundle):
    """The whole point of scoping certs out -- assert no cert/TLS
    directives sneak into either proxy template."""
    for proxy in ('nginx', 'apache'):
        script = generate_install_script(_default_options(reverse_proxy=proxy), source_dir=fixture_bundle).decode('utf-8')
        assert 'ssl_certificate' not in script
        assert 'SSLCertificate' not in script
        assert 'listen 443' not in script
        assert ':443' not in script
    for proxy in ('nginx', 'apache', 'none'):
        script = generate_install_script(_default_options(reverse_proxy=proxy), source_dir=fixture_bundle).decode('utf-8')
        assert 'TLS/certificates were not configured' in script


def test_embedded_archive_decodes_to_the_original_bundle(fixture_bundle):
    """Pure-Python round-trip: pull the base64 blob out of the
    generated script text and confirm it tars back to the exact
    fixture bundle contents."""
    script = generate_install_script(_default_options(), source_dir=fixture_bundle).decode('utf-8')
    _before, _marker, after = script.partition('__WEBAPP_BUNDLE_BELOW__\n')
    assert _marker, 'archive marker not found in generated script'

    raw = base64.b64decode(after)
    import io
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as tar:
        names = set(tar.getnames())
        assert 'webapp' in names or any(n.startswith('webapp/') for n in names)
        wsgi_member = tar.extractfile('webapp/wsgi.py')
        assert wsgi_member.read().decode() == "print('hello from wsgi')\n"
        req_member = tar.extractfile('requirements-web.txt')
        assert 'flask' in req_member.read().decode()


@requires_bash
@pytest.mark.parametrize('proxy', ['nginx', 'apache', 'none'])
def test_generated_script_is_valid_bash(tmp_path, fixture_bundle, proxy):
    script = generate_install_script(_default_options(reverse_proxy=proxy), source_dir=fixture_bundle)
    script_path = tmp_path / 'install.sh'
    script_path.write_bytes(script)
    result = subprocess.run(['bash', '-n', str(script_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@requires_bash
def test_real_extraction_commands_recover_the_bundle(tmp_path, fixture_bundle):
    """Runs the ACTUAL grep/tail/base64/tar pipeline the generated
    script itself uses (not a Python re-implementation of it), against
    a real subprocess shell, to prove the runtime extraction mechanism
    genuinely works end to end."""
    if shutil.which('tar') is None or shutil.which('base64') is None:
        pytest.skip('tar/base64 not available')

    script = generate_install_script(_default_options(), source_dir=fixture_bundle)
    script_path = tmp_path / 'install.sh'
    script_path.write_bytes(script)
    dest = tmp_path / 'extracted'
    dest.mkdir()

    pipeline = (
        f'ARCHIVE_LINE=$(grep -an "^__WEBAPP_BUNDLE_BELOW__$" "{script_path}" | head -1 | cut -d: -f1); '
        f'tail -n +$((ARCHIVE_LINE + 1)) "{script_path}" | base64 -d | tar xz -C "{dest}"'
    )
    result = subprocess.run(['bash', '-c', pipeline], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (dest / 'webapp' / 'wsgi.py').read_text() == "print('hello from wsgi')\n"
    assert 'flask' in (dest / 'requirements-web.txt').read_text()


# ----------------------------------------------------------------------
# Windows (PowerShell + NSSM + IIS)
# ----------------------------------------------------------------------

requires_pwsh = pytest.mark.skipif(
    shutil.which('pwsh') is None,
    reason='pwsh not available -- no PowerShell syntax check possible in this environment',
)


@pytest.fixture
def fake_nssm(tmp_path, monkeypatch):
    """Stands in for the vendored nssm.exe (not committed to the repo
    -- see nssm_path()'s own docstring) so tests can exercise the
    Windows generator without it."""
    nssm_file = tmp_path / 'fake_nssm.exe'
    nssm_file.write_bytes(b'FAKE NSSM BINARY CONTENT')
    monkeypatch.setattr('vra_editor.core.web_installer.nssm_path', lambda: nssm_file)
    return nssm_file


def _default_windows_options(**overrides) -> WindowsInstallOptions:
    base = dict(
        install_dir=r'C:\VRA-Editor-Web',
        port=8000,
        config_path=r'C:\ProgramData\VRA-Editor\config.ini',
        reverse_proxy='iis',
        server_name='vra.example.org',
        site_name='VRA-Editor-Web',
        ldap_server='ldap://ldap.example.org:389',
        ldap_bind_pattern='cn={username},ou=people,dc=example,dc=org',
        ldap_use_ssl=False,
    )
    base.update(overrides)
    return WindowsInstallOptions(**base)


def test_windows_missing_bundle_raises(tmp_path, fake_nssm):
    empty_dir = tmp_path / 'nonexistent'
    with pytest.raises(BundleMissingError):
        generate_windows_install_script(_default_windows_options(), source_dir=empty_dir)


def test_windows_missing_nssm_raises(fixture_bundle):
    # Deliberately no fake_nssm fixture here -- nssm_path() resolves
    # to its real (in this dev checkout, nonexistent) location.
    with pytest.raises(NssmMissingError):
        generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle)


def test_windows_unknown_reverse_proxy_raises(fixture_bundle, fake_nssm):
    with pytest.raises(ValueError):
        generate_windows_install_script(_default_windows_options(reverse_proxy='caddy'), source_dir=fixture_bundle)


def test_windows_script_contains_correct_nssm_and_service_fields(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "& $nssmExe install VraEditorWeb $pythonExe $serviceArgs" in script
    assert '$serviceArgs = "-m waitress --host=127.0.0.1 --port=$Port --call webapp.wsgi:create_app_from_env"' in script
    assert '& $nssmExe set VraEditorWeb AppEnvironmentExtra "VRA_CONFIG_PATH=$ConfigPath"' in script
    assert "$InstallDir = 'C:\\VRA-Editor-Web'" in script
    assert "$ConfigPath = 'C:\\ProgramData\\VRA-Editor\\config.ini'" in script
    assert '$Port = 8000' in script
    # LocalSystem by design -- no service-account field or password anywhere.
    assert 'ObjectName' not in script
    assert 'password' not in script.lower()


def test_windows_elevation_check_present(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert '#Requires -RunAsAdministrator' in script
    assert 'WindowsBuiltinRole]::Administrator' in script


def test_windows_stops_existing_service_before_extracting(fixture_bundle, fake_nssm):
    """Regression test: re-running the installer against an existing
    deployment used to fail with 'Access to the path ... nssm.exe is
    denied' because Expand-Archive can't overwrite a file NSSM still
    has open while the service is running. The script must stop/remove
    any prior VraEditorWeb service before extraction, using sc.exe
    (not the newly-extracted nssm.exe) since an earlier install may
    have lived at a different directory than this run's."""
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "Get-Service -Name 'VraEditorWeb'" in script
    assert 'Stop-Service' in script
    assert 'sc.exe delete VraEditorWeb' in script
    assert script.index('VraEditorWeb service') < script.index('Extracting web app to')


@pytest.mark.parametrize('proxy,expect_present,expect_absent', [
    ('iis', ['New-Website', 'HostHeader', 'ApplicationRequestRouting', 'RewriteModule', 'web.config',
             'action type="Rewrite" url="http://127.0.0.1:8000/{R:1}"'],
     []),
    ('none', [], ['New-Website', 'ApplicationRequestRouting', 'RewriteModule', 'Configuring IIS']),
])
def test_windows_reverse_proxy_template_selection(fixture_bundle, fake_nssm, proxy, expect_present, expect_absent):
    script = generate_windows_install_script(
        _default_windows_options(reverse_proxy=proxy), source_dir=fixture_bundle,
    ).decode('utf-8')
    for needle in expect_present:
        assert needle in script
    for needle in expect_absent:
        assert needle not in script


def test_windows_ldap_options_reach_the_config_merge_step(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "$LdapServer = 'ldap://ldap.example.org:389'" in script
    assert "$LdapBindPattern = 'cn={username},ou=people,dc=example,dc=org'" in script
    assert '$LdapUseSsl = $false' in script
    assert "parser['ldap'] = {" in script


def test_windows_local_auth_disabled_by_default(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert '$LocalAuthEnabled = $false' in script


def test_windows_local_auth_enabled_reaches_config_merge_step(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(
        _default_windows_options(local_auth_enabled=True), source_dir=fixture_bundle,
    ).decode('utf-8')
    assert '$LocalAuthEnabled = $true' in script
    assert 'localAuthEnabledArg' in script
    assert "parser['local_auth'] = {'enabled': local_auth_enabled}" in script


def test_windows_ldap_omitted_from_config_merge_when_ldap_server_blank(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(
        _default_windows_options(ldap_server='', ldap_bind_pattern='', local_auth_enabled=True),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    assert "$LdapServer = ''" in script
    assert "parser.remove_section('ldap')" in script


def test_windows_locations_reach_the_config_merge_step(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(
        _default_windows_options(
            location_edit=r'\\fileserver\archive\edit',
            location_app_data=r'\\fileserver\archive\clutter',
        ),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    assert '$LocEdit' in script
    assert 'fileserver' in script
    assert "location_values = {" in script
    assert "'app_data': loc_app_data" in script


def test_windows_locations_blank_by_default(fixture_bundle, fake_nssm):
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')
    assert "$LocEdit = ''" in script
    assert "$LocAppData = ''" in script


def test_windows_no_service_user_warning_anywhere(fixture_bundle, fake_nssm):
    """Unlike Linux, Windows has no service_user field and no privilege
    gap for LogonUser -- confirm no such warning text was accidentally
    carried over."""
    script = generate_windows_install_script(
        _default_windows_options(local_auth_enabled=True), source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'shadow' not in script.lower()
    assert 'LocalSystem can call' in script  # the explanatory comment, present instead


def test_windows_tls_is_never_configured(fixture_bundle, fake_nssm):
    """'certificate' legitimately appears once, in the note saying TLS
    isn't configured -- checked for explicitly rather than banned
    outright, alongside the actual TLS-directive checks."""
    for proxy in ('iis', 'none'):
        script = generate_windows_install_script(
            _default_windows_options(reverse_proxy=proxy), source_dir=fixture_bundle,
        ).decode('utf-8')
        assert 'sslFlags' not in script
        assert 'New-SelfSignedCertificate' not in script
        assert 'New-WebBinding' not in script  # only used to add a :443 binding, never called here
        assert ':443' not in script
        assert 'TLS/certificates were not configured' in script


def test_no_unescaped_nested_double_quotes_in_write_host_lines(fixture_bundle, fake_nssm):
    """Regression test: an earlier draft embedded the IIS summary
    (built from user-supplied server_name/site_name) directly inside
    an already-double-quoted Write-Host line, so a value containing a
    literal " would have closed that string early -- a real
    PowerShell syntax error. Every Write-Host "..." line's own content
    must not itself contain an unescaped double quote; user-supplied
    text must flow through a $Variable (see $ProxySummary) instead."""
    for proxy in ('iis', 'none'):
        script = generate_windows_install_script(
            _default_windows_options(reverse_proxy=proxy, site_name='Some "Weird" Name'),
            source_dir=fixture_bundle,
        ).decode('utf-8')
        for line in script.splitlines():
            match = re.match(r'^\s*Write-Host "([^"]*)"\s*$', line)
            if match:
                continue  # exactly one matched pair of quotes -- fine
            match = re.match(r'^\s*Write-Host "(.*)"\s*$', line)
            if match:
                # Matched greedily -- if the non-greedy version above
                # didn't already match, there's more than one quoted
                # segment on this line, meaning an embedded unescaped ".
                pytest.fail(f"Write-Host line has an embedded unescaped double-quote: {line!r}")


def test_proxy_summary_survives_quote_characters_in_site_name(fixture_bundle, fake_nssm):
    """The actual value under test for the regression above: a
    site_name containing both a literal " and a literal ' must still
    produce a syntactically sound $ProxySummary assignment (single
    quotes doubled per _ps_quote, double quotes need no escaping
    inside a PowerShell single-quoted string) and must be referenced
    via the plain $ProxySummary variable, not re-embedded as text."""
    script = generate_windows_install_script(
        _default_windows_options(site_name="Weird \"Quoted\" O'Brien Name"),
        source_dir=fixture_bundle,
    ).decode('utf-8')
    assert 'Write-Host $ProxySummary' in script
    assignment_lines = [line for line in script.splitlines() if line.strip().startswith('$ProxySummary =')]
    assert len(assignment_lines) == 1
    assignment = assignment_lines[0]
    # _ps_quote doubles each literal ' -- confirm that happened, and
    # that the whole thing is still one syntactically closed '...' string.
    assert "O''Brien" in assignment
    assert assignment.strip().startswith("$ProxySummary = '")
    assert assignment.strip().endswith("'")


def test_windows_embedded_archive_decodes_to_the_original_bundle_and_nssm(fixture_bundle, fake_nssm):
    """Pure-Python round-trip: pull the base64 blob out of the
    generated script text and confirm it unzips back to the exact
    fixture bundle contents, plus nssm.exe folded in alongside it."""
    script = generate_windows_install_script(_default_windows_options(), source_dir=fixture_bundle).decode('utf-8')

    before, marker, after = script.partition("$bundleBase64 = @'\n")
    assert marker, "here-string opening for $bundleBase64 not found"
    blob, _sep, _rest = after.partition("\n'@\n")

    raw = base64.b64decode(blob)
    import io
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        names = set(zf.namelist())
        assert 'webapp/wsgi.py' in names
        assert 'requirements-web.txt' in names
        assert 'fake_nssm.exe' in names
        assert zf.read('webapp/wsgi.py').decode() == "print('hello from wsgi')\n"
        assert 'flask' in zf.read('requirements-web.txt').decode()
        assert zf.read('fake_nssm.exe') == b'FAKE NSSM BINARY CONTENT'


@requires_pwsh
@pytest.mark.parametrize('proxy', ['iis', 'none'])
def test_generated_windows_script_is_valid_powershell(tmp_path, fixture_bundle, fake_nssm, proxy):
    script = generate_windows_install_script(
        _default_windows_options(reverse_proxy=proxy), source_dir=fixture_bundle,
    )
    script_path = tmp_path / 'install.ps1'
    script_path.write_bytes(script)
    result = subprocess.run(
        ['pwsh', '-NoProfile', '-Command',
         f"$errors = $null; [System.Management.Automation.Language.Parser]::ParseFile("
         f"'{script_path}', [ref]$null, [ref]$errors) | Out-Null; "
         f"if ($errors.Count -gt 0) {{ $errors | ForEach-Object {{ Write-Error $_ }}; exit 1 }}"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
