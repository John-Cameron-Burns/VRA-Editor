"""Unit tests for webapp/config.py's auth-config helpers -- pure
configparser + tmp_path, no Flask/LDAP fixtures needed since these
functions only ever read a config.ini off disk."""

import pytest

from webapp.config import load_ldap_config, local_auth_enabled, validate_auth_config


def _write_config(path, text):
    path.write_text(text)
    return path


def test_load_ldap_config_returns_none_when_section_absent(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[web]\nsecret_key = x\n")
    assert load_ldap_config(config_path) is None


def test_load_ldap_config_returns_none_when_file_missing(tmp_path):
    assert load_ldap_config(tmp_path / 'does-not-exist.ini') is None


def test_load_ldap_config_raises_when_server_missing(tmp_path):
    config_path = _write_config(
        tmp_path / 'config.ini', "[ldap]\nbind_pattern = cn={username}\n",
    )
    with pytest.raises(ValueError):
        load_ldap_config(config_path)


def test_load_ldap_config_raises_when_bind_pattern_missing(tmp_path):
    config_path = _write_config(
        tmp_path / 'config.ini', "[ldap]\nserver = ldap://x:389\n",
    )
    with pytest.raises(ValueError):
        load_ldap_config(config_path)


def test_load_ldap_config_returns_dict_when_complete(tmp_path):
    config_path = _write_config(
        tmp_path / 'config.ini',
        "[ldap]\nserver = ldap://x:389\nbind_pattern = cn={username}\nuse_ssl = true\n",
    )
    cfg = load_ldap_config(config_path)
    assert cfg == {'server': 'ldap://x:389', 'use_ssl': True, 'bind_pattern': 'cn={username}'}


def test_local_auth_enabled_false_when_section_absent(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[web]\nsecret_key = x\n")
    assert local_auth_enabled(config_path) is False


def test_local_auth_enabled_false_when_enabled_key_absent(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[local_auth]\n")
    assert local_auth_enabled(config_path) is False


def test_local_auth_enabled_true_when_configured(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[local_auth]\nenabled = true\n")
    assert local_auth_enabled(config_path) is True


def test_local_auth_enabled_false_when_explicitly_false(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[local_auth]\nenabled = false\n")
    assert local_auth_enabled(config_path) is False


def test_validate_auth_config_raises_when_neither_configured(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[web]\nsecret_key = x\n")
    with pytest.raises(ValueError):
        validate_auth_config(config_path)


def test_validate_auth_config_passes_ldap_only(tmp_path):
    config_path = _write_config(
        tmp_path / 'config.ini', "[ldap]\nserver = ldap://x:389\nbind_pattern = cn={username}\n",
    )
    validate_auth_config(config_path)  # should not raise


def test_validate_auth_config_passes_local_only(tmp_path):
    config_path = _write_config(tmp_path / 'config.ini', "[local_auth]\nenabled = true\n")
    validate_auth_config(config_path)  # should not raise


def test_validate_auth_config_passes_both(tmp_path):
    config_path = _write_config(
        tmp_path / 'config.ini',
        "[ldap]\nserver = ldap://x:389\nbind_pattern = cn={username}\n\n"
        "[local_auth]\nenabled = true\n",
    )
    validate_auth_config(config_path)  # should not raise


def test_validate_auth_config_still_raises_on_incomplete_ldap_even_if_local_enabled(tmp_path):
    """An [ldap] section that's present but broken is a real
    misconfiguration, regardless of local auth being enabled -- it
    shouldn't be silently treated as 'LDAP is off'."""
    config_path = _write_config(
        tmp_path / 'config.ini',
        "[ldap]\nserver = ldap://x:389\n\n[local_auth]\nenabled = true\n",
    )
    with pytest.raises(ValueError):
        validate_auth_config(config_path)
