import getpass
import os, pwd , platform
from csv import excel

if platform.system() == "Windows":
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
        if hasattr(user_info, 'pw_gecos'): return  user_info.pw_gecos.split(',',maxsplit=1)[0]
        if hasattr(user_info, 'gecos'): return user_info.gecos.split(',', maxsplit=1)[0]
        return None


def user_name():
    uname  = getpass.getuser()
    full_name = get_full_name()
    if not full_name  or (full_name == uname) : return uname
    else: return f'{uname}({full_name}'
