from conftest import JSMITH, requires_ldap, write_sample_record


@requires_ldap
def test_create_record_writes_a_skeleton_document(app, test_archive):
    _config_path, locations = test_archive

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'new-work-001'})
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['rel_path'] == 'new-work-001.xml'

    record_path = locations['edit'] / 'new-work-001.xml'
    assert record_path.exists()
    xml = record_path.read_text()
    assert 'id="new-work-001"' in xml
    assert '<vra:work' in xml


@requires_ldap
def test_create_record_supports_image_and_collection(app, test_archive):
    _config_path, locations = test_archive

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    r = client.post('/api/records/edit', json={'record_type': 'image', 'record_id': 'img-001'})
    assert r.status_code == 201, r.get_json()
    assert '<vra:image' in (locations['edit'] / 'img-001.xml').read_text()

    r = client.post('/api/records/edit', json={'record_type': 'collection', 'record_id': 'coll-001'})
    assert r.status_code == 201, r.get_json()
    assert '<vra:collection' in (locations['edit'] / 'coll-001.xml').read_text()


@requires_ldap
def test_create_record_rejects_invalid_record_type(app, test_archive):
    _config_path, locations = test_archive

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'not-a-real-type', 'record_id': 'x'})
    assert r.status_code == 400
    assert not (locations['edit'] / 'x.xml').exists()


@requires_ldap
def test_create_record_rejects_empty_id(app, test_archive):
    _config_path, locations = test_archive

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': '   '})
    assert r.status_code == 400


@requires_ldap
def test_create_record_rejects_path_separators_in_id(app, test_archive):
    _config_path, locations = test_archive

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': '../escape'})
    assert r.status_code == 400
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'sub\\dir'})
    assert r.status_code == 400


@requires_ldap
def test_create_record_conflicts_with_existing_file(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'already-exists', 'Existing Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'already-exists'})
    assert r.status_code == 409


def test_create_record_requires_auth(client, test_archive):
    _config_path, locations = test_archive
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'nope'})
    assert r.status_code == 401
    assert not (locations['edit'] / 'nope.xml').exists()


@requires_ldap
def test_create_record_auto_commits(app, test_archive):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, _locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'committed-001'})
    assert r.status_code == 201, r.get_json()

    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Create work committed-001' in latest.message
    finally:
        repo.close()


@requires_ldap
def test_newly_created_record_can_be_opened_and_edited(app, test_archive):
    """The created record should behave exactly like any other record
    once it exists -- opening it acquires the lock and returns a tree
    with the record's own child_specs (e.g. titleSet is addable)."""
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'editable-001'})

    r = client.get('/api/records/edit/editable-001.xml')
    assert r.status_code == 200, r.get_json()
    tree = r.get_json()['record']
    assert tree['children'] == []
    assert any(s['tag'] == 'titleSet' for s in tree['child_specs'])
