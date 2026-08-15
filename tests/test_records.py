from pathlib import Path

from conftest import JSMITH, MDOE, requires_ldap, write_sample_record


@requires_ldap
def test_folder_list_shows_records_with_titles(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'First Record')
    write_sample_record(locations['edit'], 'rec2', 'Second Record', subfolder='collectionA')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/folders/edit')
    assert r.status_code == 200
    records = {rec['rel_path']: rec for rec in r.get_json()['records']}
    assert records['rec1.xml']['title'] == 'First Record'
    assert records['rec1.xml']['locked_by'] is None
    assert records['collectionA/rec2.xml']['title'] == 'Second Record'


def test_folder_list_requires_auth(client):
    r = client.get('/api/folders/edit')
    assert r.status_code == 401


@requires_ldap
def test_folder_list_unknown_key_is_404(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    # 'reviewed'/'rejected'/'released' are reachable only via the
    # transitions into them (Approve/Reject/Submit), never browsed or
    # opened directly -- see records_common.ALLOWED_FOLDERS.
    r = client.get('/api/folders/reviewed')
    assert r.status_code == 404


@requires_ldap
def test_folder_list_pending_is_allowed(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Awaiting Review')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/folders/pending')
    assert r.status_code == 200
    assert r.get_json()['records'][0]['title'] == 'Awaiting Review'


@requires_ldap
def test_open_record_acquires_lock_and_returns_tree(app, test_archive):
    from vra_editor.core import record_locks

    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Open Me')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/rec1.xml')
    assert r.status_code == 200

    body = r.get_json()
    assert body['record']['data']['tag'] == 'work'
    title_node = body['record']['children'][0]['children'][0]
    assert title_node['data']['text'] == 'Open Me'
    assert title_node['path'] == [0, 0]
    assert 'heartbeat_interval' in body

    lock = record_locks.status(record_path, config_path)
    assert lock == {'holder': 'jsmith', 'expired': False}


@requires_ldap
def test_open_record_not_found(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/does-not-exist.xml')
    assert r.status_code == 404


@requires_ldap
def test_open_record_blocked_by_another_users_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Contested Record')

    client_a, client_b = app.test_client(), app.test_client()
    client_a.post('/api/auth/login', json=JSMITH)
    client_b.post('/api/auth/login', json=MDOE)

    assert client_a.get('/api/records/edit/rec1.xml').status_code == 200
    r = client_b.get('/api/records/edit/rec1.xml')
    assert r.status_code == 409
    assert 'jsmith' in r.get_json()['error']


@requires_ldap
def test_heartbeat_and_release(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Heartbeat Record')

    client_a, client_b = app.test_client(), app.test_client()
    client_a.post('/api/auth/login', json=JSMITH)
    client_b.post('/api/auth/login', json=MDOE)
    client_a.get('/api/records/edit/rec1.xml')

    assert client_a.post('/api/records/edit/rec1.xml/heartbeat').status_code == 200
    assert client_b.post('/api/records/edit/rec1.xml/heartbeat').status_code == 409

    assert client_a.post('/api/records/edit/rec1.xml/release').status_code == 200
    assert client_b.get('/api/records/edit/rec1.xml').status_code == 200


@requires_ldap
def test_path_traversal_is_rejected(app):
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/../../../../etc/passwd')
    assert r.status_code == 404


@requires_ldap
def test_save_requires_holding_the_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened Record')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.put('/api/records/edit/rec1.xml', json={'edits': []})
    assert r.status_code == 409


@requires_ldap
def test_save_persists_edit_and_commits_with_correct_author(app, test_archive):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Before Edit')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = client.get('/api/records/edit/rec1.xml').get_json()['record']
    title_path = tree['children'][0]['children'][0]['path']

    r = client.put('/api/records/edit/rec1.xml', json={
        'edits': [{'path': title_path, 'text': 'After Edit', 'type': 'descriptive'}],
        'commit_message': 'Edit via test',
    })
    assert r.status_code == 200

    saved = record_path.read_text()
    assert 'After Edit' in saved
    assert 'Before Edit' not in saved

    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Edit via test' in latest.message
    finally:
        repo.close()


@requires_ldap
def test_save_without_commit_message_skips_commit(app, test_archive):
    """Matches the desktop's own optional commit-comment prompt: a
    blank/omitted message means the save happens but nothing is
    committed to git history."""
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'No Commit')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    r = client.put('/api/records/edit/rec1.xml', json={'edits': []})
    assert r.status_code == 200
    assert not (get_git_dir(config_path) / 'HEAD').exists()


@requires_ldap
def test_save_rejects_invalid_edit_path(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Bad Path Record')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    r = client.put('/api/records/edit/rec1.xml', json={'edits': [{'path': [99, 99], 'text': 'x'}]})
    assert r.status_code == 400


@requires_ldap
def test_save_rejects_schema_invalid_value(app, test_archive):
    """title's type attribute is a controlled vocabulary -- 'not-a-real-type'
    isn't in it, so schema validation should reject the save (422),
    and the file on disk must be untouched."""
    _config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Still Valid')
    original = record_path.read_text()

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = client.get('/api/records/edit/rec1.xml').get_json()['record']
    title_path = tree['children'][0]['children'][0]['path']

    r = client.put('/api/records/edit/rec1.xml', json={
        'edits': [{'path': title_path, 'text': 'Still Valid', 'type': 'not-a-real-type'}],
    })
    assert r.status_code == 422
    assert record_path.read_text() == original


@requires_ldap
def test_submit_moves_to_pending_preserving_subfolder(app, test_archive):
    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Submit Me', subfolder='collectionA')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/collectionA/rec1.xml')

    r = client.post('/api/records/edit/collectionA/rec1.xml/submit')
    assert r.status_code == 200

    dest = Path(r.get_json()['dest_path'])
    assert dest == (locations['pending'] / 'collectionA' / 'rec1.xml').resolve()
    assert dest.exists()
    assert not record_path.exists()


@requires_ldap
def test_submit_requires_holding_the_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened Submit')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/submit')
    assert r.status_code == 409


@requires_ldap
def test_submit_releases_lock(app, test_archive):
    from vra_editor.core import record_locks

    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Lock Then Submit')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    client.post('/api/records/edit/rec1.xml/submit')

    assert record_locks.status(record_path, config_path) is None
