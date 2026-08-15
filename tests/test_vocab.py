"""Covers vocab_routes.py's own logic: auth gating, input validation,
and the vocabularies listing. Deliberately doesn't exercise a real
/api/vocab/search hit against VIAF/Getty/LOC/GNS here -- those are
live external services with no local test double in this codebase,
and hitting them from the automated suite would make it flaky and
rate-limit-prone. That path is covered by manual/browser verification
instead (see the Phase 4 rollout notes)."""

from conftest import JSMITH, requires_ldap


@requires_ldap
def test_list_vocabularies(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/vocab/vocabularies')
    assert r.status_code == 200, r.get_json()
    keys = {v['key'] for v in r.get_json()['vocabularies']}
    assert keys == {'VIAF', 'AAT', 'TGN', 'ULAN', 'GNS', 'LCSH', 'LCNAF', 'LCGFT', 'LCTGM'}


def test_list_vocabularies_requires_auth(client):
    r = client.get('/api/vocab/vocabularies')
    assert r.status_code == 401


def test_search_requires_auth(client):
    r = client.get('/api/vocab/search?vocab=AAT&q=bronze')
    assert r.status_code == 401


@requires_ldap
def test_search_rejects_unknown_vocab(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/vocab/search?vocab=NOT_REAL&q=bronze')
    assert r.status_code == 400


@requires_ldap
def test_search_rejects_missing_vocab(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/vocab/search?q=bronze')
    assert r.status_code == 400


@requires_ldap
def test_search_rejects_empty_query(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/vocab/search?vocab=AAT&q=')
    assert r.status_code == 400
