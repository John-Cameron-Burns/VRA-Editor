def test_version_works_without_auth(client):
    r = client.get('/api/version')
    assert r.status_code == 200
    assert 'version' in r.get_json()


def test_version_falls_back_to_dev_build_from_source(client):
    """Running from a source checkout (no bundled VERSION file, as in
    this test run) -- update_check.get_app_version()'s own documented
    fallback."""
    r = client.get('/api/version')
    assert r.get_json()['version'] == 'development build'
