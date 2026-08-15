"""Tests for vra_editor.core.web_installer -- Qt-free, so plain pytest
with no LDAP/Flask fixtures needed (unlike the rest of tests/, which
covers webapp/). Runs bash -n (and, for the main case, the actual
extraction commands) to verify the generated script isn't just
Python-side correct but genuinely valid/working bash.
"""

import base64
import shutil
import subprocess
import tarfile

import pytest

from vra_editor.core.web_installer import BundleMissingError, InstallOptions, generate_install_script

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
