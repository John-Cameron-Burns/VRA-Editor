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
