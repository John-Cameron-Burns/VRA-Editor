"""Tests for vra_editor.core.archive_signature -- pure filesystem
logic, no Qt/Flask needed."""

from vra_editor.core import archive_signature


def test_read_signature_returns_none_when_file_absent(tmp_path):
    assert archive_signature.read_signature(tmp_path) is None


def test_write_then_read_round_trips(tmp_path):
    archive_signature.write_signature(tmp_path, 'abc123')
    assert archive_signature.read_signature(tmp_path) == 'abc123'


def test_signature_file_is_hidden_and_has_a_comment_header(tmp_path):
    archive_signature.write_signature(tmp_path, 'abc123')
    sig_path = tmp_path / archive_signature.SIGNATURE_FILENAME
    assert sig_path.name.startswith('.')
    text = sig_path.read_text()
    assert text.count('#') >= 1
    assert 'abc123' in text


def test_write_signature_overwrites_previous_value(tmp_path):
    archive_signature.write_signature(tmp_path, 'first')
    archive_signature.write_signature(tmp_path, 'second')
    assert archive_signature.read_signature(tmp_path) == 'second'


def test_read_signature_ignores_comment_lines(tmp_path):
    (tmp_path / archive_signature.SIGNATURE_FILENAME).write_text(
        "# a comment\n# another comment\nreal-id-here\n"
    )
    assert archive_signature.read_signature(tmp_path) == 'real-id-here'


def test_read_signature_returns_none_for_directory_with_no_such_file(tmp_path):
    (tmp_path / 'unrelated.txt').write_text('nothing to do with this')
    assert archive_signature.read_signature(tmp_path) is None


def test_write_signature_is_best_effort_on_unwritable_folder(tmp_path):
    missing = tmp_path / 'does-not-exist' / 'nested'
    archive_signature.write_signature(missing, 'x')  # should not raise
    assert archive_signature.read_signature(missing) is None


def test_new_archive_id_is_unique_each_call():
    a = archive_signature.new_archive_id()
    b = archive_signature.new_archive_id()
    assert a != b
    assert len(a) == 32  # uuid4().hex
