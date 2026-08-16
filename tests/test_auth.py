import sys
import types

import webapp.auth
from conftest import JSMITH, MDOE, requires_ldap


@requires_ldap
def test_login_success(client):
    r = client.post('/api/auth/login', json=JSMITH)
    assert r.status_code == 200
    assert r.get_json() == {'username': 'jsmith'}


@requires_ldap
def test_login_wrong_password(client):
    r = client.post('/api/auth/login', json={'username': 'jsmith', 'password': 'not-the-password'})
    assert r.status_code == 401


@requires_ldap
def test_login_unknown_user(client):
    r = client.post('/api/auth/login', json={'username': 'nobody', 'password': 'whatever'})
    assert r.status_code == 401


def test_login_missing_fields(client):
    """No LDAP round-trip should even happen for an empty username/password."""
    r = client.post('/api/auth/login', json={})
    assert r.status_code == 401


def test_whoami_requires_auth(client):
    r = client.get('/api/auth/whoami')
    assert r.status_code == 401


@requires_ldap
def test_whoami_after_login(client):
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/auth/whoami')
    assert r.status_code == 200
    assert r.get_json()['username'] == 'jsmith'


@requires_ldap
def test_logout_clears_session(client):
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/auth/logout')
    assert r.status_code == 200
    r = client.get('/api/auth/whoami')
    assert r.status_code == 401


@requires_ldap
def test_logout_releases_held_locks(app, test_archive):
    from vra_editor.core import record_locks
    from conftest import write_sample_record

    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'lock-test', 'Lock Test Record')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/lock-test.xml')
    assert r.status_code == 200
    assert record_locks.status(record_path, config_path)['holder'] == 'jsmith'

    client.post('/api/auth/logout')
    assert record_locks.status(record_path, config_path) is None


@requires_ldap
def test_two_different_users_can_each_log_in(app):
    client_a = app.test_client()
    client_b = app.test_client()
    r_a = client_a.post('/api/auth/login', json=JSMITH)
    r_b = client_b.post('/api/auth/login', json=MDOE)
    assert r_a.status_code == 200 and r_a.get_json()['username'] == 'jsmith'
    assert r_b.status_code == 200 and r_b.get_json()['username'] == 'mdoe'


# ----------------------------------------------------------------------
# authenticate() precedence -- LDAP first, local second, first success
# wins. No @requires_ldap here: these monkeypatch the backend functions
# directly, so no real LDAP server or OS account is ever touched.
# ----------------------------------------------------------------------

def test_authenticate_prefers_ldap_when_it_succeeds(monkeypatch):
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', lambda cp: {'server': 'x', 'use_ssl': False, 'bind_pattern': 'y'})
    monkeypatch.setattr(webapp.auth, '_authenticate_ldap', lambda u, p, cfg: True)
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: True)

    def _fail_if_called(u, p):
        raise AssertionError("local auth should never be tried when LDAP already succeeded")
    monkeypatch.setattr(webapp.auth, '_authenticate_local', _fail_if_called)

    assert webapp.auth.authenticate('someone', 'pw') == {'username': 'someone'}


def test_authenticate_falls_through_to_local_when_ldap_fails(monkeypatch):
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', lambda cp: {'server': 'x', 'use_ssl': False, 'bind_pattern': 'y'})
    monkeypatch.setattr(webapp.auth, '_authenticate_ldap', lambda u, p, cfg: False)
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: True)
    monkeypatch.setattr(webapp.auth, '_authenticate_local', lambda u, p: True)

    assert webapp.auth.authenticate('someone', 'pw') == {'username': 'someone'}


def test_authenticate_skips_local_when_not_enabled(monkeypatch):
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', lambda cp: {'server': 'x', 'use_ssl': False, 'bind_pattern': 'y'})
    monkeypatch.setattr(webapp.auth, '_authenticate_ldap', lambda u, p, cfg: False)
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: False)

    def _fail_if_called(u, p):
        raise AssertionError("local auth should never be tried when it isn't enabled")
    monkeypatch.setattr(webapp.auth, '_authenticate_local', _fail_if_called)

    assert webapp.auth.authenticate('someone', 'pw') is None


def test_authenticate_returns_none_when_both_backends_fail(monkeypatch):
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', lambda cp: {'server': 'x', 'use_ssl': False, 'bind_pattern': 'y'})
    monkeypatch.setattr(webapp.auth, '_authenticate_ldap', lambda u, p, cfg: False)
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: True)
    monkeypatch.setattr(webapp.auth, '_authenticate_local', lambda u, p: False)

    assert webapp.auth.authenticate('someone', 'pw') is None


def test_authenticate_returns_none_when_ldap_not_configured_and_local_disabled(monkeypatch):
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', lambda cp: None)
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: False)

    assert webapp.auth.authenticate('someone', 'pw') is None


def test_authenticate_short_circuits_on_empty_credentials_without_configured_backends(monkeypatch):
    """No LDAP/local round-trip should even happen for an empty
    username/password -- covered for authenticate() directly (see
    test_login_missing_fields for the route-level version)."""
    def _fail_if_called(cp):
        raise AssertionError("should never reach config loading for empty credentials")
    monkeypatch.setattr(webapp.auth, 'load_ldap_config', _fail_if_called)
    assert webapp.auth.authenticate('', 'pw') is None
    assert webapp.auth.authenticate('someone', '') is None


# ----------------------------------------------------------------------
# _authenticate_ldap's own bind_pattern handling -- regression coverage
# for a real production crash: a typo like "{usename}" instead of
# "{username}" used to raise an uncaught KeyError straight out to a
# 500 on every single login attempt, instead of just failing this one
# backend (the same way an unreachable LDAP server already does).
# ----------------------------------------------------------------------

def test_authenticate_ldap_returns_false_on_malformed_bind_pattern(app):
    with app.app_context():
        result = webapp.auth._authenticate_ldap(
            'jsmith', 'whatever',
            {'server': 'ldap://x', 'use_ssl': False, 'bind_pattern': 'cn={usename}'},
        )
    assert result is False


def test_authenticate_falls_through_to_local_when_bind_pattern_malformed(app, monkeypatch):
    """The whole point of not raising: a broken bind_pattern must not
    prevent local auth from getting its turn."""
    monkeypatch.setattr(
        webapp.auth, 'load_ldap_config',
        lambda cp: {'server': 'x', 'use_ssl': False, 'bind_pattern': 'cn={usename}'},
    )
    monkeypatch.setattr(webapp.auth, 'local_auth_enabled', lambda cp: True)
    monkeypatch.setattr(webapp.auth, '_authenticate_local', lambda u, p: True)
    with app.app_context():
        assert webapp.auth.authenticate('jsmith', 'whatever') == {'username': 'jsmith'}


# ----------------------------------------------------------------------
# _authenticate_local's platform dispatch
# ----------------------------------------------------------------------

def test_authenticate_local_dispatches_to_pam_on_linux(monkeypatch):
    monkeypatch.setattr(webapp.auth.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(webapp.auth, '_authenticate_pam', lambda u, p: 'pam-called')
    assert webapp.auth._authenticate_local('u', 'p') == 'pam-called'


def test_authenticate_local_dispatches_to_windows_on_windows(monkeypatch):
    monkeypatch.setattr(webapp.auth.platform, 'system', lambda: 'Windows')
    monkeypatch.setattr(webapp.auth, '_authenticate_windows_local', lambda u, p: 'windows-called')
    assert webapp.auth._authenticate_local('u', 'p') == 'windows-called'


# ----------------------------------------------------------------------
# _authenticate_pam / _authenticate_windows_local -- the real glue code,
# exercised against fake sys.modules entries rather than a real PAM
# stack or real Windows accounts (see ARCHITECTURE.md for why: standing
# up real disposable local OS accounts isn't practical in CI the way a
# throwaway LDAP docker container is). Runnable on any CI OS regardless
# of the actual platform, since the fake module is injected directly.
# ----------------------------------------------------------------------

class _FakePam:
    def authenticate(self, username, password, service='login'):
        assert service == 'login'
        if username == 'raises':
            raise RuntimeError("PAM service file not found")
        return username == 'gooduser' and password == 'goodpass'


def test_authenticate_pam_success(monkeypatch):
    fake_module = types.ModuleType('pam')
    fake_module.pam = _FakePam
    monkeypatch.setitem(sys.modules, 'pam', fake_module)
    assert webapp.auth._authenticate_pam('gooduser', 'goodpass') is True


def test_authenticate_pam_wrong_password(monkeypatch):
    fake_module = types.ModuleType('pam')
    fake_module.pam = _FakePam
    monkeypatch.setitem(sys.modules, 'pam', fake_module)
    assert webapp.auth._authenticate_pam('gooduser', 'wrongpass') is False


def test_authenticate_pam_collapses_exceptions_to_false(monkeypatch):
    fake_module = types.ModuleType('pam')
    fake_module.pam = _FakePam
    monkeypatch.setitem(sys.modules, 'pam', fake_module)
    assert webapp.auth._authenticate_pam('raises', 'x') is False


class _FakePywintypesError(Exception):
    pass


class _FakeHandle:
    def __init__(self):
        self.closed = False

    def Close(self):
        self.closed = True


def _install_fake_win32(monkeypatch, logon_user):
    fake_pywintypes = types.ModuleType('pywintypes')
    fake_pywintypes.error = _FakePywintypesError
    fake_win32security = types.ModuleType('win32security')
    fake_win32security.LOGON32_LOGON_NETWORK = 3
    fake_win32security.LOGON32_PROVIDER_DEFAULT = 0
    fake_win32security.LogonUser = logon_user
    monkeypatch.setitem(sys.modules, 'pywintypes', fake_pywintypes)
    monkeypatch.setitem(sys.modules, 'win32security', fake_win32security)


def test_authenticate_windows_local_success(monkeypatch):
    handle = _FakeHandle()

    def fake_logon_user(username, domain, password, logon_type, provider):
        assert domain is None
        assert logon_type == 3
        assert provider == 0
        if username == 'gooduser' and password == 'goodpass':
            return handle
        raise _FakePywintypesError("bad credentials")
    _install_fake_win32(monkeypatch, fake_logon_user)

    assert webapp.auth._authenticate_windows_local('gooduser', 'goodpass') is True
    assert handle.closed is True


def test_authenticate_windows_local_wrong_password(monkeypatch):
    def fake_logon_user(username, domain, password, logon_type, provider):
        raise _FakePywintypesError("bad credentials")
    _install_fake_win32(monkeypatch, fake_logon_user)

    assert webapp.auth._authenticate_windows_local('gooduser', 'wrongpass') is False
