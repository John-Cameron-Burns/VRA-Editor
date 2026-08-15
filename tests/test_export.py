from conftest import JSMITH, requires_ldap, write_sample_record


@requires_ldap
def test_export_dublin_core(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'A Sculpture')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/rec1.xml/export/dublin-core')
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.mimetype == 'application/xml'
    assert 'attachment' in r.headers['Content-Disposition']
    assert 'rec1-dc.xml' in r.headers['Content-Disposition']
    body = r.get_data(as_text=True)
    assert 'A Sculpture' in body
    assert 'oai_dc' in body


@requires_ldap
def test_export_lido(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'A Sculpture')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/rec1.xml/export/lido')
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.mimetype == 'application/xml'
    assert 'rec1-lido.xml' in r.headers['Content-Disposition']
    body = r.get_data(as_text=True)
    assert 'A Sculpture' in body
    assert 'lido:lido' in body


@requires_ldap
def test_export_missing_record_is_404(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/does-not-exist.xml/export/dublin-core')
    assert r.status_code == 404


@requires_ldap
def test_export_does_not_require_the_lock(app, test_archive):
    """Export is read-only -- it should work even without opening the
    record first (no lock held), unlike Save/structural mutations."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened Export')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/rec1.xml/export/dublin-core')
    assert r.status_code == 200


def test_export_requires_auth(client, test_archive):
    r = client.get('/api/records/edit/rec1.xml/export/dublin-core')
    assert r.status_code == 401


@requires_ldap
def test_export_works_from_pending_folder(app, test_archive):
    """Export should also work for a record awaiting review, matching
    ALLOWED_FOLDERS covering both edit and pending."""
    _config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Pending Export')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/pending/rec1.xml/export/dublin-core')
    assert r.status_code == 200
