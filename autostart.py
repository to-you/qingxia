"""Current-user Windows sign-in startup; changed only from the settings panel."""
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY=r'Software\Microsoft\Windows\CurrentVersion\Run'
VALUE_NAME='QingXia'


def command():
    executable=Path(sys.executable)
    if getattr(sys,'frozen',False):
        args=[str(executable),'--background']
    else:
        pythonw=executable.with_name('pythonw.exe')
        args=[str(pythonw if pythonw.exists() else executable),str(Path(__file__).with_name('main.py').resolve()),'--background']
    return subprocess.list2cmdline(args)


def enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY) as key:
            value,_=winreg.QueryValueEx(key,VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def migrate_legacy():
    """Preserve this application's existing startup choice after a project rename."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
            try:
                old,_=winreg.QueryValueEx(key,'FloTools')
            except FileNotFoundError:
                return
            parent=Path(__file__).resolve().parent.parent
            known=[str(parent/'flo-tools'/'main.py'),str(Path(__file__).with_name('main.py').resolve())]
            if not any(path.casefold() in old.casefold() for path in known):
                return
            try:
                winreg.QueryValueEx(key,VALUE_NAME)
            except FileNotFoundError:
                winreg.SetValueEx(key,VALUE_NAME,0,winreg.REG_SZ,command())
            winreg.DeleteValue(key,'FloTools')
    except FileNotFoundError:
        pass


def set_enabled(value):
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,RUN_KEY,0,winreg.KEY_SET_VALUE) as key:
        if value:
            winreg.SetValueEx(key,VALUE_NAME,0,winreg.REG_SZ,command())
        else:
            try:
                winreg.DeleteValue(key,VALUE_NAME)
            except FileNotFoundError:
                pass
