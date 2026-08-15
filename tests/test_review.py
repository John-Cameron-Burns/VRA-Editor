from pathlib import Path

from conftest import JSMITH, requires_ldap, write_sample_record


@requires_ldap
def test_open_record_includes_empty_review_notes(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'No Notes Yet')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.get('/api/records/edit/rec1.xml')
    assert r.status_code == 200
    assert r.get_json()['review_notes'] == []


@requires_ldap
def test_add_update_delete_note(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Note Target')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')

    r = client.post('/api/records/edit/rec1.xml/notes', json={'text': 'Please check the date'})
    assert r.status_code == 200
    notes = r.get_json()['notes']
    assert len(notes) == 1
    assert notes[0]['text'] == 'Please check the date'
    assert notes[0]['author'] == 'jsmith'
    assert notes[0]['resolved'] is False

    r = client.put('/api/records/edit/rec1.xml/notes/0', json={'resolved': True})
    assert r.status_code == 200
    assert r.get_json()['notes'][0]['resolved'] is True

    r = client.delete('/api/records/edit/rec1.xml/notes/0')
    assert r.status_code == 200
    assert r.get_json()['notes'] == []


@requires_ldap
def test_add_note_requires_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/notes', json={'text': 'x'})
    assert r.status_code == 409


@requires_ldap
def test_note_out_of_range_is_404(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Empty Notes')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    r = client.put('/api/records/edit/rec1.xml/notes/0', json={'resolved': True})
    assert r.status_code == 404


@requires_ldap
def test_approve_moves_pending_to_reviewed_and_commits(app, test_archive):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Ready For Review', subfolder='collectionA')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/pending/collectionA/rec1.xml')

    r = client.post('/api/records/pending/collectionA/rec1.xml/approve')
    assert r.status_code == 200
    dest = Path(r.get_json()['dest_path'])
    assert dest == (locations['reviewed'] / 'collectionA' / 'rec1.xml').resolve()
    assert dest.exists()

    # Approve always commits, even with no commit_message supplied --
    # unlike Save, there's no client-side undo for a lifecycle move.
    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Approved by jsmith' in latest.message
    finally:
        repo.close()


@requires_ldap
def test_approve_requires_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Unopened Approve')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/pending/rec1.xml/approve')
    assert r.status_code == 409


@requires_ldap
def test_reject_moves_to_rejected_with_reason_note(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Needs Work')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/pending/rec1.xml')

    r = client.post('/api/records/pending/rec1.xml/reject', json={'reason': 'Missing a creator'})
    assert r.status_code == 200
    dest = Path(r.get_json()['dest_path'])
    assert dest == (locations['rejected'] / 'rec1.xml').resolve()

    # The reason should have been appended as a review note that
    # travels with the file to its new location.
    from vra_editor.core.xml_parser import VraXmlParser
    from vra_editor.core import review_notes
    parser = VraXmlParser()
    parser.load(str(dest))
    notes = review_notes.get_review_notes(parser.xml_root)
    assert len(notes) == 1
    assert notes[0]['text'] == 'Missing a creator'
    assert notes[0]['author'] == 'jsmith'


@requires_ldap
def test_reject_without_reason_adds_no_note(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['pending'], 'rec1', 'Just Reject')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/pending/rec1.xml')
    r = client.post('/api/records/pending/rec1.xml/reject')
    assert r.status_code == 200

    from vra_editor.core.xml_parser import VraXmlParser
    from vra_editor.core import review_notes
    parser = VraXmlParser()
    parser.load(str(Path(r.get_json()['dest_path'])))
    assert review_notes.get_review_notes(parser.xml_root) == []
