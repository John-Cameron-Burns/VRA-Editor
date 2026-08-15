from conftest import JSMITH, requires_ldap, write_sample_record


def _open(client, key, rel_path):
    r = client.get(f'/api/records/{key}/{rel_path}')
    assert r.status_code == 200, r.get_json()
    return r.get_json()['record']


@requires_ldap
def test_add_child_creates_missing_section(app, test_archive):
    """A freshly created record has no titleSet at all -- adding one
    at the record root is the "+ Add {section}" flow."""
    from vra_editor.core.xml_parser import VraXmlParser
    from lxml import etree

    _config_path, locations = test_archive
    parser = VraXmlParser()
    parser.new_document('work', 'bare-001', lang='en')
    record_path = locations['edit'] / 'bare-001.xml'
    record_path.write_bytes(etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'))

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'bare-001.xml')
    assert tree['children'] == []  # nothing yet

    r = client.post('/api/records/edit/bare-001.xml/children', json={'parent_path': [], 'tag': 'titleSet'})
    assert r.status_code == 200, r.get_json()
    tree = r.get_json()['record']
    assert len(tree['children']) == 1
    assert tree['children'][0]['data']['tag'] == 'titleSet'
    assert tree['children'][0]['children'] == []  # empty titleSet, no title inside yet -- allowed


@requires_ldap
def test_add_child_beyond_record_level_max_occurs_is_422(app, test_archive):
    """Every top-level Set is max_occurs=1 at the record root -- a
    second titleSet must be rejected."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Has A Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'titleSet'})
    assert r.status_code == 422, r.get_json()


@requires_ldap
def test_add_repeatable_leaf_within_titleset(app, test_archive):
    """title within titleSet is unbounded -- a second one is fine."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'First Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'rec1.xml')
    title_set_path = tree['children'][0]['path']

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': title_set_path, 'tag': 'title'})
    assert r.status_code == 200, r.get_json()
    title_set = r.get_json()['record']['children'][0]
    assert len(title_set['children']) == 2


@requires_ldap
def test_add_child_invalid_tag_is_400(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Some Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'not-a-real-tag'})
    assert r.status_code == 400, r.get_json()


@requires_ldap
def test_add_child_requires_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'dateSet'})
    assert r.status_code == 409


@requires_ldap
def test_add_beyond_max_occurs_within_a_container(app, test_archive):
    """date's earliestDate/latestDate are each max_occurs=1 -- a
    second earliestDate under the same date must be rejected."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Date Test')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'rec1.xml')

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'dateSet'})
    tree = r.get_json()['record']
    date_set_path = next(c for c in tree['children'] if c['data']['tag'] == 'dateSet')['path']

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': date_set_path, 'tag': 'date'})
    tree = r.get_json()['record']
    date_set = next(c for c in tree['children'] if c['data']['tag'] == 'dateSet')
    date_path = date_set['children'][0]['path']

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': date_path, 'tag': 'earliestDate'})
    assert r.status_code == 200, r.get_json()

    r = client.post('/api/records/edit/rec1.xml/children', json={'parent_path': date_path, 'tag': 'earliestDate'})
    assert r.status_code == 422, r.get_json()


@requires_ldap
def test_remove_element(app, test_archive):
    _config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Removable Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'rec1.xml')
    title_set_path = tree['children'][0]['path']

    r = client.post('/api/records/edit/rec1.xml/remove-element', json={'path': title_set_path})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['record']['children'] == []
    assert 'Removable Title' not in record_path.read_text()


@requires_ldap
def test_remove_creating_a_temporarily_invalid_document_is_allowed(app, test_archive):
    """Matches desktop parity: structural mutations don't validate --
    only Save/Submit do. Removing titleSet's only <title> leaves the
    (still-present, empty) titleSet violating its own min_occurs=1 on
    title, but that's allowed to be written -- the same way the
    desktop's in-memory document can be briefly invalid mid-edit."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Only Title')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'rec1.xml')
    title_leaf_path = tree['children'][0]['children'][0]['path']

    r = client.post('/api/records/edit/rec1.xml/remove-element', json={'path': title_leaf_path})
    assert r.status_code == 200, r.get_json()
    title_set = r.get_json()['record']['children'][0]
    assert title_set['children'] == []

    # ...but Save (which does validate) should now refuse it, exactly
    # as it would refuse any other schema-invalid state.
    r = client.put('/api/records/edit/rec1.xml', json={'edits': []})
    assert r.status_code == 422, r.get_json()


@requires_ldap
def test_remove_element_requires_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened Remove')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/remove-element', json={'path': [0]})
    assert r.status_code == 409


@requires_ldap
def test_remove_element_invalid_path_is_400(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Bad Path')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    r = client.post('/api/records/edit/rec1.xml/remove-element', json={'path': [99, 99]})
    assert r.status_code == 400


@requires_ldap
def test_remove_record_itself_is_rejected(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Root')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    r = client.post('/api/records/edit/rec1.xml/remove-element', json={'path': []})
    assert r.status_code == 400


@requires_ldap
def test_set_display_translations_creates_and_updates(app, test_archive):
    """display is a valid child of titleSet itself (a Set-level
    container), not of the title leaf -- confirmed against the real
    schema-derived child_specs before writing this test."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Displayable')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    tree = _open(client, 'edit', 'rec1.xml')
    title_set_node = tree['children'][0]
    assert any(s['tag'] == 'display' for s in title_set_node['child_specs'])
    title_set_path = title_set_node['path']

    r = client.post('/api/records/edit/rec1.xml/display', json={
        'path': title_set_path, 'translations': {'en': 'Displayable', 'fr': 'Affichable'},
    })
    assert r.status_code == 200, r.get_json()
    title_set = r.get_json()['record']['children'][0]
    display_node = next(c for c in title_set['children'] if c['node_type'] == 'display')
    assert display_node['data']['translations'] == {'en': 'Displayable', 'fr': 'Affichable'}

    # Editing again via the display node's own path (not the
    # titleSet's) should update the same underlying element.
    r = client.post('/api/records/edit/rec1.xml/display', json={
        'path': display_node['path'], 'translations': {'en': 'Updated'},
    })
    assert r.status_code == 200, r.get_json()
    title_set = r.get_json()['record']['children'][0]
    display_node = next(c for c in title_set['children'] if c['node_type'] == 'display')
    assert display_node['data']['translations'] == {'en': 'Updated'}


@requires_ldap
def test_set_display_requires_lock(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened Display')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/display', json={'path': [0], 'translations': {'en': 'x'}})
    assert r.status_code == 409


@requires_ldap
def test_structural_mutations_auto_commit(app, test_archive):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Commit Test')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'dateSet'})

    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Add dateSet' in latest.message
    finally:
        repo.close()
