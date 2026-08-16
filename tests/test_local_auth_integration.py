"""Opt-in, real-account verification for webapp/auth.py's local-OS-
account backends -- deliberately NOT part of routine CI (see
ARCHITECTURE.md and tests/conftest.py's own LDAP-vs-local-auth testing
philosophy note). Standing up a real local OS account needs root/admin
and permanently modifies the host running these tests, unlike the
throwaway `lldap` Docker container the LDAP suite uses -- there's no
`docker-compose down` equivalent for a real useradd.

To run these against a real pre-provisioned account:

    Linux (run as root, so the process can read /etc/shadow):
        sudo useradd -M vra-test-local
        sudo passwd vra-test-local          # set a known password
        sudo VRA_TEST_LOCAL_USER=vra-test-local \\
             VRA_TEST_LOCAL_PASSWORD='<the password you set>' \\
             pytest tests/test_local_auth_integration.py

    Windows (run from an elevated PowerShell prompt):
        net user vra-test-local Password123! /add
        $env:VRA_TEST_LOCAL_USER = 'vra-test-local'
        $env:VRA_TEST_LOCAL_PASSWORD = 'Password123!'
        pytest tests/test_local_auth_integration.py

Skipped by default (no env vars set) everywhere else.
"""

import os

import pytest

from webapp.auth import _authenticate_local

TEST_LOCAL_USER = os.environ.get('VRA_TEST_LOCAL_USER')
TEST_LOCAL_PASSWORD = os.environ.get('VRA_TEST_LOCAL_PASSWORD')

requires_local_account = pytest.mark.skipif(
    not (TEST_LOCAL_USER and TEST_LOCAL_PASSWORD),
    reason="VRA_TEST_LOCAL_USER/VRA_TEST_LOCAL_PASSWORD not set -- opt-in manual verification "
           "against a real pre-provisioned local OS account (see this module's own docstring "
           "for provisioning steps). Skipped by default.",
)


@requires_local_account
def test_real_local_account_login_succeeds():
    assert _authenticate_local(TEST_LOCAL_USER, TEST_LOCAL_PASSWORD) is True


@requires_local_account
def test_real_local_account_wrong_password_fails():
    assert _authenticate_local(TEST_LOCAL_USER, 'definitely-wrong-password') is False


@requires_local_account
def test_real_local_account_unknown_user_fails():
    assert _authenticate_local('definitely-not-a-real-account', TEST_LOCAL_PASSWORD) is False
