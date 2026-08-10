import getpass
import os
import platform
from typing import Optional

import regex


def strip_quotes(value: str) -> str:
    """
    Strip leading and trailing quotes  & spaces from a string. Use the Unicode character class to match ALL quotes.
    :param value:
    :return:
    """
    return regex.sub(r'^[\s\p{Quotation_Mark}]+|[\s\p{Quotation_Mark}]+$', '', value)


if platform.system() == "Windows":
    # noinspection PyUnresolvedReferences
    def get_full_name():
        import ctypes
        GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
        NameDisplay = 3
        size = ctypes.pointer(ctypes.c_ulong(0))
        GetUserNameEx(NameDisplay, None, size)
        if size.contents.value == 0:
            return None
        name_buffer = ctypes.create_unicode_buffer(size.contents.value)
        if not GetUserNameEx(NameDisplay, name_buffer, size):
            return None
        return name_buffer.value or None
else:
    def get_full_name():
        import pwd  # POSIX-only; deferred so importing this module doesn't fail on Windows
        # Get user info by UID
        user_info = pwd.getpwuid(os.getuid())
        if hasattr(user_info, 'pw_gecos'): return user_info.pw_gecos.split(',', maxsplit=1)[0]
        if hasattr(user_info, 'gecos'): return user_info.gecos.split(',', maxsplit=1)[0]
        return None


def user_name() -> Optional[str]:
    """
    Retrieves the current user's full name for display, checking OS
    account info first, then vra-config.ini's [user] FullName, and
    falling back to the computer login name if neither has one.

    :return: The user's full name, or their login name if no full name
        is available.
    :rtype: str
    """
    uname = getpass.getuser()
    full_name = get_full_name()
    if full_name and full_name != uname:
        return full_name

    from .config import load_config  # deferred: config.py imports strip_quotes from this module
    parser = load_config()
    if parser.has_section('user'):
        full_name = strip_quotes(parser['user'].get('FullName', ''))
        if full_name:
            return full_name
    return uname
