from conftest import JSMITH, requires_ldap, write_sample_record


@requires_ldap
def test_list_audits_reflects_prior_commits(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'audit-001'})

    r = client.get('/api/audits')
    assert r.status_code == 200, r.get_json()
    revisions = r.get_json()['revisions']
    assert len(revisions) == 1
    assert revisions[0]['filename'] == 'edit/audit-001.xml'
    assert revisions[0]['author'] == 'jsmith'
    assert revisions[0]['message'] == 'Create work audit-001'
    assert 'sha' in revisions[0] and revisions[0]['sha']
    assert 'date' in revisions[0] and revisions[0]['date']


@requires_ldap
def test_list_audits_empty_before_any_commit(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/audits')
    assert r.status_code == 200
    assert r.get_json()['revisions'] == []


def test_list_audits_requires_auth(client):
    r = client.get('/api/audits')
    assert r.status_code == 401


@requires_ldap
def test_restore_writes_a_new_file_and_commits(app, test_archive):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'orig-001'})
    original_content = (locations['edit'] / 'orig-001.xml').read_text()

    revisions = client.get('/api/audits').get_json()['revisions']
    sha = revisions[0]['sha']
    filename = revisions[0]['filename']

    r = client.post('/api/audits/restore', json={
        'sha': sha, 'filename': filename, 'dest_rel_path': 'restored-001.xml',
    })
    assert r.status_code == 201, r.get_json()
    assert r.get_json()['rel_path'] == 'restored-001.xml'

    restored_path = locations['edit'] / 'restored-001.xml'
    assert restored_path.exists()
    assert restored_path.read_text() == original_content

    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Restore' in latest.message
    finally:
        repo.close()


@requires_ldap
def test_restore_refuses_to_overwrite_existing_file(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'orig-002'})
    revisions = client.get('/api/audits').get_json()['revisions']
    sha = revisions[0]['sha']
    filename = revisions[0]['filename']

    write_sample_record(locations['edit'], 'already-there', 'Existing')
    r = client.post('/api/audits/restore', json={
        'sha': sha, 'filename': filename, 'dest_rel_path': 'already-there.xml',
    })
    assert r.status_code == 409


@requires_ldap
def test_restore_missing_fields_is_400(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/audits/restore', json={'sha': '', 'filename': '', 'dest_rel_path': ''})
    assert r.status_code == 400


@requires_ldap
def test_restore_unknown_sha_is_404(app, test_archive):
    _config_path, locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.post('/api/records/edit', json={'record_type': 'work', 'record_id': 'audit-003'})

    r = client.post('/api/audits/restore', json={
        'sha': 'a' * 40, 'filename': 'edit/audit-003.xml', 'dest_rel_path': 'nope.xml',
    })
    assert r.status_code == 404


def test_restore_requires_auth(client, test_archive):
    r = client.post('/api/audits/restore', json={
        'sha': 'a' * 40, 'filename': 'edit/x.xml', 'dest_rel_path': 'y.xml',
    })
    assert r.status_code == 401
