import getpass
import os
import platform
import pwd
from typing import Optional

import regex


def strip_quotes(value: str) -> str:
    """
    Strip leading and trailing quotes  & spaces from a string. Use the Unicode character class to match ALL quotes.
    :param value:
    :return:
    """
    return regex.sub(r'^[\s\p{Quotation_Mark}]+|[\s\p{Quotation_Mark}]+$','' , value)

if platform.system() == "Windows":
    # noinspection PyUnresolvedReferences
    def get_user_name():
        import ctypes
        GetUserNameEx = ctypes.windll.secur32.GetUserNameExW
        NameDisplay = 3
        size = ctypes.pointer(ctypes.c_ulong(0))
        GetUserNameEx(NameDisplay, None, size)
        name_buffer = ctypes.create_unicode_buffer(size.contents.value)
        GetUserNameEx(NameDisplay, name_buffer, size)
        return name_buffer.value
else:
    def get_full_name():
        # Get user info by UID
        user_info = pwd.getpwuid(os.getuid())
        if hasattr(user_info, 'pw_gecos'): return user_info.pw_gecos.split(',', maxsplit=1)[0]
        if hasattr(user_info, 'gecos'): return user_info.gecos.split(',', maxsplit=1)[0]
        return None


def user_name() -> Optional[str]:
    """
    Retrieves the current user's name. The function attempts to determine the user's
    full name by evaluating  system credentials or configuration file and defaults to the
    username if a full name is not found.

    :return: The user's name, either as only the username or as a combination of
        username and full name if available.
    :rtype: str
    """
    uname = getpass.getuser()
    full_name = get_full_name()
    if full_name and full_name != uname:
        return f'{uname}({full_name})'

    from .config import load_config  # deferred: config.py imports strip_quotes from this module
    parser = load_config()
    if parser.has_section('user'):
        full_name = strip_quotes(parser['user'].get('FullName', ''))
        if full_name:
            return full_name
    return uname
