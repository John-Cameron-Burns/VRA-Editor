import configparser

from conftest import JSMITH


def _add_ingest_location(config_path, tmp_path):
    """test_archive's own config.ini doesn't configure an 'ingest'
    location (Import is the only feature that needs one) -- add it
    in place and return the folder path, creating it too."""
    ingest_dir = tmp_path / 'archive' / 'ingest'
    ingest_dir.mkdir(parents=True, exist_ok=True)

    cp = configparser.ConfigParser()
    cp.read(config_path)
    cp['locations']['ingest'] = str(ingest_dir)
    with open(config_path, 'w') as f:
        cp.write(f)
    return ingest_dir


def _write_ingest_record(ingest_dir, record_id, title):
    from lxml import etree
    from vra_editor.core.xml_parser import VraXmlParser

    parser = VraXmlParser()
    parser.new_document('work', record_id, lang='en')
    records = parser.build_tree()
    parser.add_child(records[0].element, 'titleSet', [s.tag for s in records[0].child_specs])
    records = parser.build_tree()
    title_set = records[0].children[0]
    parser.add_child(title_set.element, 'title', [s.tag for s in title_set.child_specs])
    records = parser.build_tree()
    title_leaf = records[0].children[0].children[0]
    parser.set_element_data(title_leaf.element, title)

    path = ingest_dir / f'{record_id}.xml'
    path.write_bytes(etree.tostring(parser.xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'))
    return path


def test_import_requires_auth(client, test_archive):
    r = client.post('/api/import/run')
    assert r.status_code == 401


def test_import_missing_ingest_location_is_400(app, test_archive):
    config_path, _locations = test_archive
    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/run')
    assert r.status_code == 400, r.get_json()


def test_import_moves_records_into_edit(app, test_archive, tmp_path):
    config_path, locations = test_archive
    ingest_dir = _add_ingest_location(config_path, tmp_path)
    _write_ingest_record(ingest_dir, 'imported-001', 'Freshly Ingested')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/run')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['orphan_media'] == []

    dest = locations['edit'] / 'imported-001.xml'
    assert dest.exists()
    assert 'Freshly Ingested' in dest.read_text()
    # source moved to ingest_dir/done/, not left in place or deleted
    assert not (ingest_dir / 'imported-001.xml').exists()
    assert (ingest_dir / 'done' / 'imported-001.xml').exists()


def test_import_reports_orphan_media(app, test_archive, tmp_path):
    config_path, locations = test_archive
    ingest_dir = _add_ingest_location(config_path, tmp_path)
    orphan = ingest_dir / 'stray.jpg'
    orphan.write_bytes(b'not a real jpeg, just needs to exist')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/run')
    assert r.status_code == 200, r.get_json()
    orphans = r.get_json()['orphan_media']
    assert orphans == [{'rel_path': 'stray.jpg'}]
    # process_vra_directory itself doesn't touch orphans -- still in place
    assert orphan.exists()


def test_stash_orphan_moves_into_done(app, test_archive, tmp_path):
    config_path, locations = test_archive
    ingest_dir = _add_ingest_location(config_path, tmp_path)
    orphan = ingest_dir / 'stray.jpg'
    orphan.write_bytes(b'orphan content')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/orphans/stash', json={'rel_path': 'stray.jpg'})
    assert r.status_code == 200, r.get_json()
    assert not orphan.exists()
    assert (ingest_dir / 'done' / 'stray.jpg').exists()


def test_ignore_orphan_then_import_no_longer_reports_it(app, test_archive, tmp_path):
    config_path, locations = test_archive
    ingest_dir = _add_ingest_location(config_path, tmp_path)
    orphan = ingest_dir / 'stray.jpg'
    orphan.write_bytes(b'orphan content')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    r = client.post('/api/import/orphans/ignore', json={'rel_path': 'stray.jpg'})
    assert r.status_code == 200, r.get_json()
    assert orphan.exists()  # ignore doesn't move the file, just remembers it

    r = client.post('/api/import/run')
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['orphan_media'] == []


def test_stash_unknown_orphan_is_404(app, test_archive, tmp_path):
    config_path, locations = test_archive
    _add_ingest_location(config_path, tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/orphans/stash', json={'rel_path': 'does-not-exist.jpg'})
    assert r.status_code == 404


def test_orphan_rel_path_cannot_escape_ingest_dir(app, test_archive, tmp_path):
    config_path, locations = test_archive
    _add_ingest_location(config_path, tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/import/orphans/stash', json={'rel_path': '../edit/rec1.xml'})
    assert r.status_code == 404
