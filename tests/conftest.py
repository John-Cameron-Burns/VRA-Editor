"""Pytest fixtures for webapp/'s test suite.

Needs a running LDAP test server -- see docker-compose.web-test.yml at
the repo root:

    docker compose -f docker-compose.web-test.yml up -d
    docker compose -f docker-compose.web-test.yml exec lldap-test /bootstrap/bootstrap.sh
    pytest tests/

Tests that need it are skipped with a clear message (not a confusing
connection-refused traceback) if it isn't reachable, so the rest of
the suite still runs without Docker -- see requires_ldap below.

Every fixture-built config points at temp directories under tmp_path --
these tests must never touch a developer's real ~/.vra-editor/config.ini
or archive folders. isolated_app_data patches vra_editor.app_data
before anything imports vra_editor.config, since that module's own
load_locations()/load_config() bind their config_path default once, at
first import -- patching app_data afterward wouldn't take effect (this
bit a manual test earlier in development; see commit history).
"""

import configparser
import os
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pytest

# Overridable so this suite can point at a different LDAP server
# without editing this file -- e.g. VRA_TEST_LDAP_SERVER=ldap://10.0.5.98:389
# to run against a real dev server instead of the local docker-compose
# fixture (useful wherever Docker itself isn't available).
TEST_LDAP_SERVER = os.environ.get("VRA_TEST_LDAP_SERVER", "ldap://localhost:3389")
TEST_LDAP_BIND_PATTERN = "cn={username},ou=people,dc=vra,dc=local"
_ldap_url = urlparse(TEST_LDAP_SERVER)
_LDAP_HOST = _ldap_url.hostname or "localhost"
_LDAP_PORT = _ldap_url.port or 389

JSMITH = {"username": "jsmith", "password": "TestPass123!"}
MDOE = {"username": "mdoe", "password": "TestPass456!"}


def _ldap_reachable() -> bool:
    try:
        with socket.create_connection((_LDAP_HOST, _LDAP_PORT), timeout=1):
            return True
    except OSError:
        return False


requires_ldap = pytest.mark.skipif(
    not _ldap_reachable(),
    reason=f"LDAP test server not reachable at {TEST_LDAP_SERVER} -- "
           "run `docker compose -f docker-compose.web-test.yml up -d` first "
           "(or set VRA_TEST_LDAP_SERVER to point elsewhere)",
)


@pytest.fixture
def isolated_app_data(monkeypatch):
    """Points vra_editor.app_data at a fresh temp dir for this test.
    Must happen before vra_editor.config is imported for the first
    time in this process -- conftest.py itself doesn't import it at
    module scope, for exactly that reason."""
    import vra_editor.app_data as app_data
    fake_home = Path(tempfile.mkdtemp()) / '.vra-editor'
    monkeypatch.setattr(app_data, 'BOOTSTRAP_DIR', fake_home)
    monkeypatch.setattr(app_data, 'CONFIG_PATH', fake_home / 'config.ini')
    return fake_home


@pytest.fixture
def test_archive(isolated_app_data, tmp_path):
    """A throwaway config.ini + edit/pending/rejected/reviewed folder
    tree pointed at the test LDAP server. Returns (config_path,
    locations dict)."""
    config_path = tmp_path / 'config.ini'
    locations = {
        'edit': tmp_path / 'archive' / 'edit',
        'pending': tmp_path / 'archive' / 'pending',
        'rejected': tmp_path / 'archive' / 'rejected',
        'reviewed': tmp_path / 'archive' / 'reviewed',
        'app_data': isolated_app_data,
    }
    for path in locations.values():
        path.mkdir(parents=True, exist_ok=True)

    cp = configparser.ConfigParser()
    cp['ldap'] = {
        'server': TEST_LDAP_SERVER,
        'use_ssl': 'false',
        'bind_pattern': TEST_LDAP_BIND_PATTERN,
    }
    cp['locations'] = {k: str(v) for k, v in locations.items()}
    with open(config_path, 'w') as f:
        cp.write(f)

    return config_path, locations


@pytest.fixture
def app(test_archive):
    from webapp.app import create_app
    config_path, _locations = test_archive
    return create_app(config_path=config_path)


@pytest.fixture
def client(app):
    return app.test_client()


def write_sample_record(edit_dir: Path, record_id: str, title: str, subfolder: str = '') -> Path:
    """Writes a minimal, schema-valid work record with one title, the
    same way the desktop app's Create + Save would -- for tests that
    need a real file on disk to open/edit/submit."""
    from lxml import etree
    from vra_editor.core.xml_parser import VraXmlParser

    parser = VraXmlParser()
    parser.new_document('work', record_id, lang='en')
    records = parser.build_tree()
    sibling_order = [s.tag for s in records[0].child_specs]
    parser.add_child(records[0].element, 'titleSet', sibling_order)
    records = parser.build_tree()
    title_specs = [s.tag for s in records[0].children[0].child_specs]
    title_elem = parser.add_child(records[0].children[0].element, 'title', title_specs)
    parser.set_element_data(title_elem, title, vocab='', refid='', href='', lang='', type_value='descriptive')

    dest_dir = (edit_dir / subfolder) if subfolder else edit_dir
    dest_dir.mkdir(parents=True, exist_ok=True)
    record_path = dest_dir / f'{record_id}.xml'
    record_path.write_bytes(
        etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8')
    )
    return record_path
