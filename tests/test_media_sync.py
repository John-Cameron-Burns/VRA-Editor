import io
import json

import pytest

from conftest import JSMITH, requires_ldap, write_sample_record

pyexiv2 = pytest.importorskip('pyexiv2', reason='pyexiv2 not installed -- IPTC-backed media-sync tests need it')
PIL_Image = pytest.importorskip('PIL.Image', reason='Pillow not installed')


def _make_test_image_with_iptc(tmp_path, filename='test.jpg', **iptc_overrides):
    """A real JPEG on disk with known dimensions/DPI and embedded IPTC
    fields -- pyexiv2 needs an actual file, not an in-memory buffer, to
    write into, so this is built once per test and read back as bytes
    for upload."""
    path = tmp_path / filename
    PIL_Image.open  # noqa: B018 -- just to force the importorskip'd name to resolve
    from PIL import Image
    Image.new('RGB', (200, 100), color='blue').save(str(path), dpi=(300, 300))

    fields = {
        'Iptc.Application2.ObjectName': 'File Title',
        'Iptc.Application2.Caption': 'File description',
        'Iptc.Application2.Copyright': 'File rights statement',
        'Iptc.Application2.Byline': ['File Photographer'],
        'Iptc.Application2.Keywords': ['keyword-one', 'keyword-two'],
    }
    fields.update(iptc_overrides)
    img = pyexiv2.Image(str(path))
    try:
        img.modify_iptc(fields)
    finally:
        img.close()
    return path


@requires_ldap
def test_compare_media_reports_fill_record_for_empty_fields(app, test_archive, tmp_path):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Existing Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)

    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/compare',
            data={'file': (f, 'test.jpg')},
            content_type='multipart/form-data',
        )
    assert r.status_code == 200, r.get_json()
    data = r.get_json()
    assert data['iptc_available'] is True
    assert data['measurements']['width'] == 200
    assert data['measurements']['height'] == 100
    assert data['measurements']['resolution'] == 300

    # Title already has a value on the record (from write_sample_record)
    # and the file has a *different* value -- conflict.
    assert data['fields']['title']['status'] == 'conflict'
    assert data['fields']['title']['file'] == 'File Title'
    # Description/rights/agent/subject are empty on the record -- fill_record.
    assert data['fields']['description']['status'] == 'fill_record'
    assert data['fields']['rights']['status'] == 'fill_record'
    assert data['fields']['agent']['status'] == 'fill_record'
    assert data['fields']['subject']['status'] == 'fill_record'
    # No date/location EXIF on this test image.
    assert data['fields']['date']['status'] == 'empty'
    assert data['fields']['location']['status'] == 'empty'


@requires_ldap
def test_compare_media_does_not_require_lock(app, test_archive, tmp_path):
    """Read-only -- should work without ever opening the record."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Unopened')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/compare',
            data={'file': (f, 'test.jpg')},
            content_type='multipart/form-data',
        )
    assert r.status_code == 200, r.get_json()


@requires_ldap
def test_compare_media_requires_file(app, test_archive):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'No File')

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    r = client.post('/api/records/edit/rec1.xml/media-sync/compare', data={}, content_type='multipart/form-data')
    assert r.status_code == 400


@requires_ldap
def test_compare_media_missing_record_is_404(app, test_archive, tmp_path):
    _config_path, locations = test_archive
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/does-not-exist.xml/media-sync/compare',
            data={'file': (f, 'test.jpg')},
            content_type='multipart/form-data',
        )
    assert r.status_code == 404


def test_compare_media_requires_auth(client, test_archive):
    r = client.post('/api/records/edit/rec1.xml/media-sync/compare', data={}, content_type='multipart/form-data')
    assert r.status_code == 401


@requires_ldap
def test_apply_media_fills_record_and_writes_measurements(app, test_archive, tmp_path):
    from dulwich.repo import Repo
    from vra_editor.app_data import get_git_dir

    config_path, locations = test_archive
    record_path = write_sample_record(locations['edit'], 'rec1', 'Original Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')  # acquire the lock

    selections = json.dumps({'description': 'record', 'rights': 'record', 'agent': 'record', 'subject': 'record'})
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/apply',
            data={'file': (f, 'test.jpg'), 'selections': selections},
            content_type='multipart/form-data',
        )
    assert r.status_code == 200, r.get_json()

    xml = record_path.read_text()
    assert 'Original Title' in xml  # title wasn't in selections -- untouched
    assert 'File description' in xml
    assert 'File rights statement' in xml
    assert 'File Photographer' in xml
    assert 'keyword-one' in xml
    # Measurements are always written, selected or not.
    assert 'type="width"' in xml and '>200<' in xml
    assert 'type="height"' in xml and '>100<' in xml

    repo = Repo(str(get_git_dir(config_path)))
    try:
        latest = next(iter(repo.get_walker())).commit
        assert b'jsmith' in latest.author
        assert b'Fill record from media file' in latest.message
    finally:
        repo.close()


@requires_ldap
def test_apply_media_rejects_file_direction(app, test_archive, tmp_path):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')

    selections = json.dumps({'title': 'file'})
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/apply',
            data={'file': (f, 'test.jpg'), 'selections': selections},
            content_type='multipart/form-data',
        )
    assert r.status_code == 400, r.get_json()


@requires_ldap
def test_apply_media_rejects_unknown_field(app, test_archive, tmp_path):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')

    selections = json.dumps({'not_a_real_field': 'record'})
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/apply',
            data={'file': (f, 'test.jpg'), 'selections': selections},
            content_type='multipart/form-data',
        )
    assert r.status_code == 400


@requires_ldap
def test_apply_media_requires_lock(app, test_archive, tmp_path):
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    # Deliberately not opened -- no lock held.

    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/apply',
            data={'file': (f, 'test.jpg'), 'selections': '{}'},
            content_type='multipart/form-data',
        )
    assert r.status_code == 409


@requires_ldap
def test_apply_media_rejects_schema_invalid_document(app, test_archive, tmp_path):
    """If the document is already schema-invalid for reasons unrelated
    to media sync (e.g. an empty dateSet left over from a structural
    add), apply should refuse rather than silently writing on top of
    it -- matching Save's own validation gate."""
    _config_path, locations = test_archive
    write_sample_record(locations['edit'], 'rec1', 'Title')
    image_path = _make_test_image_with_iptc(tmp_path)

    client = app.test_client()
    client.post('/api/auth/login', json=JSMITH)
    client.get('/api/records/edit/rec1.xml')
    # Leaves the document schema-invalid: dateSet requires >=1 date.
    client.post('/api/records/edit/rec1.xml/children', json={'parent_path': [], 'tag': 'dateSet'})

    selections = json.dumps({'description': 'record'})
    with open(image_path, 'rb') as f:
        r = client.post(
            '/api/records/edit/rec1.xml/media-sync/apply',
            data={'file': (f, 'test.jpg'), 'selections': selections},
            content_type='multipart/form-data',
        )
    assert r.status_code == 422, r.get_json()


def test_apply_media_requires_auth(client, test_archive):
    r = client.post('/api/records/edit/rec1.xml/media-sync/apply', data={}, content_type='multipart/form-data')
    assert r.status_code == 401
