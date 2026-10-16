"""Small Windows integrations used by the desktop tools."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import os
import threading

from PySide6.QtCore import QAbstractNativeEventFilter, QTimer, Qt, QObject, Signal
from PySide6.QtGui import QKeySequence

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


def foreground():
    return user32.GetForegroundWindow()


def point_in_window(hwnd,x,y):
    rect=wintypes.RECT()
    return bool(user32.GetWindowRect(hwnd,ctypes.byref(rect))) and rect.left <= x < rect.right and rect.top <= y < rect.bottom


def activate(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    if user32.SetForegroundWindow(hwnd):
        return True
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    threads = {user32.GetWindowThreadProcessId(foreground(), None),
               user32.GetWindowThreadProcessId(hwnd, None)} - {current, 0}
    attached = [thread for thread in threads if user32.AttachThreadInput(current, thread, True)]
    try:
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        for thread in attached:
            user32.AttachThreadInput(current, thread, False)


def source_name():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground(), ctypes.byref(pid))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return '剪贴板'
    try:
        buf, size = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        return Path(buf.value).stem if kernel.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)) else '剪贴板'
    finally:
        kernel.CloseHandle(handle)


def window_rect_at(x, y):
    hwnd = user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x, y)), 2)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    rect = wintypes.RECT()
    if pid.value == os.getpid() or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top


def visible_windows():
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def collect(hwnd, _):
        pid, rect = wintypes.DWORD(), wintypes.RECT()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value != os.getpid() and user32.IsWindowVisible(hwnd) and user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            if rect.right - rect.left > 30 and rect.bottom - rect.top > 30:
                windows.append((rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top))
        return True
    callback = callback_type(collect)
    user32.EnumWindows(callback, 0)
    return windows


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class INPUTUNION(ctypes.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ('data',)
    _fields_ = [('type', wintypes.DWORD), ('data', INPUTUNION)]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]


def paste_to(hwnd, finished, attempts=0):
    if not hwnd or not user32.IsWindow(hwnd):
        finished(False)
        return
    if any(user32.GetAsyncKeyState(k) & 0x8000 for k in (0x10, 0x11, 0x12)):
        if attempts < 30:
            QTimer.singleShot(40, lambda: paste_to(hwnd, finished, attempts + 1))
        else:
            finished(False)
        return
    activate(hwnd)

    def send():
        if foreground() != hwnd:
            finished(False)
            return
        keys = (INPUT(1, INPUTUNION(ki=KEYBDINPUT(0x11, 0, 0, 0, 0))),
                INPUT(1, INPUTUNION(ki=KEYBDINPUT(0x56, 0, 0, 0, 0))),
                INPUT(1, INPUTUNION(ki=KEYBDINPUT(0x56, 0, 2, 0, 0))),
                INPUT(1, INPUTUNION(ki=KEYBDINPUT(0x11, 0, 2, 0, 0))))
        data = (INPUT * 4)(*keys)
        finished(user32.SendInput(4, data, ctypes.sizeof(INPUT)) == 4)
    QTimer.singleShot(100, send)


def glass(widget):
    class ACCENT(ctypes.Structure):
        _fields_ = [('state', ctypes.c_int), ('flags', ctypes.c_int),
                    ('color', ctypes.c_uint), ('animation', ctypes.c_int)]

    class DATA(ctypes.Structure):
        _fields_ = [('attribute', ctypes.c_int), ('data', ctypes.c_void_p), ('size', ctypes.c_size_t)]
    accent = ACCENT(4, 2, 0x60EFF3EF, 0)
    data = DATA(19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent))
    fn = user32.SetWindowCompositionAttribute
    fn.argtypes = [wintypes.HWND, ctypes.POINTER(DATA)]
    fn(int(widget.winId()), ctypes.byref(data))


def hotkey_code(text):
    sequence=QKeySequence(text)
    if sequence.count()!=1:
        raise ValueError('请设置一组快捷键。')
    combination=sequence[0]
    key=int(combination.key())
    flags=combination.keyboardModifiers()
    modifiers=0x4000
    for qt_flag,win_flag in [(Qt.ControlModifier,2),(Qt.AltModifier,1),(Qt.ShiftModifier,4),(Qt.MetaModifier,8)]:
        if flags & qt_flag:
            modifiers |= win_flag
    if int(Qt.Key_F1) <= key <= int(Qt.Key_F24):
        vk=0x70+key-int(Qt.Key_F1)
    else:
        if not flags & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier):
            raise ValueError('请组合 Ctrl、Alt 或 Win 使用，或选择 F1–F24。')
        special={Qt.Key_Space:32,Qt.Key_Tab:9,Qt.Key_Escape:27,Qt.Key_Return:13,
            Qt.Key_Backspace:8,Qt.Key_Delete:46,Qt.Key_Insert:45,Qt.Key_Home:36,Qt.Key_End:35,
            Qt.Key_PageUp:33,Qt.Key_PageDown:34,Qt.Key_Left:37,Qt.Key_Right:39,Qt.Key_Up:38,Qt.Key_Down:40,
            Qt.Key_Comma:0xBC,Qt.Key_Period:0xBE,Qt.Key_Slash:0xBF,Qt.Key_Minus:0xBD,Qt.Key_Equal:0xBB,
            Qt.Key_BracketLeft:0xDB,Qt.Key_BracketRight:0xDD,Qt.Key_Backslash:0xDC,Qt.Key_Semicolon:0xBA,
            Qt.Key_Apostrophe:0xDE,Qt.Key_QuoteLeft:0xC0}
        vk=key if 48 <= key <= 57 or 65 <= key <= 90 else special.get(key)
        if vk is None:
            raise ValueError('暂不支持这个按键，请换用字母、数字、方向键或功能键。')
    return modifiers,vk


class MouseClicks(QObject):
    clicked=Signal(object)

    def __init__(self,callback):
        super().__init__()
        self.clicked.connect(callback,Qt.QueuedConnection)
        self.enabled=False
        self.thread_id=None
        self.handle=None
        self.ready=threading.Event()
        self.worker=threading.Thread(target=self.listen,daemon=True)
        self.worker.start()
        self.ready.wait(1)

    def watching(self,enabled):
        self.enabled=enabled

    def listen(self):
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.thread_id=kernel.GetCurrentThreadId()
        callback_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM)
        user32.SetWindowsHookExW.argtypes=[ctypes.c_int,callback_type,wintypes.HINSTANCE,wintypes.DWORD]
        user32.SetWindowsHookExW.restype=wintypes.HHOOK
        user32.CallNextHookEx.argtypes=[wintypes.HHOOK,ctypes.c_int,wintypes.WPARAM,wintypes.LPARAM]
        user32.CallNextHookEx.restype=ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes=[wintypes.HHOOK]
        message=wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message),None,0,0,0)
        def clicked(code,kind,data):
            if self.enabled and code>=0 and kind in (0x0201,0x0204,0x0207):
                point=wintypes.POINT.from_address(data)
                self.clicked.emit((point.x,point.y))
            return user32.CallNextHookEx(None,code,kind,data)
        self.hook_callback=callback_type(clicked)
        self.handle=user32.SetWindowsHookExW(14,self.hook_callback,None,0)
        self.ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message),None,0,0)>0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            if self.handle:
                user32.UnhookWindowsHookEx(self.handle)
                self.handle=None

    def close(self):
        self.enabled=False
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id,0x0012,0,0)
            self.worker.join(timeout=1)


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks, self.registered, self.failed, self.bindings = {}, [], [], {}
        self.clipboard_id=0xF010
        self.action_ids=[]
        self.sequences=[]
        for index, (_key, label, callback) in enumerate(callbacks, 0xF010):
            modifiers,vk=hotkey_code(label)
            self.callbacks[index]=callback
            self.action_ids.append(index)
            self.sequences.append(label)
            self.bindings[index]=(modifiers,vk)
            if user32.RegisterHotKey(None, index, modifiers, vk):
                self.registered.append(index)
            else:
                self.failed.append(label)

    def replace_clipboard(self,text):
        return self.replace_all([text]+self.sequences[1:])

    def replace_all(self,sequences):
        try:
            bindings=[hotkey_code(text) for text in sequences]
        except ValueError as error:
            return False,str(error)
        if len(set(bindings))!=len(bindings):
            return False,'全局快捷键不能重复，请换一组。'
        callbacks=[self.callbacks[key] for key in self.action_ids]
        existing={self.bindings[key]:key for key in self.registered}
        ids,added=[],[]
        for binding in bindings:
            if binding in existing:
                ids.append(existing[binding])
                continue
            new=0xA100
            while new in self.registered or new in added:
                new+=1
            if not user32.RegisterHotKey(None,new,*binding):
                for key in added:
                    user32.UnregisterHotKey(None,key)
                return False,'快捷键被系统或其他程序占用，原设置仍可使用。'
            added.append(new)
            ids.append(new)
        for key in self.registered:
            if key not in ids:
                user32.UnregisterHotKey(None,key)
        self.registered=ids
        self.action_ids=ids
        self.callbacks=dict(zip(ids,callbacks))
        self.bindings=dict(zip(ids,bindings))
        self.sequences=list(sequences)
        self.clipboard_id=ids[0]
        self.failed=[]
        return True,''

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam in self.callbacks:
            QTimer.singleShot(0, self.callbacks[msg.wParam])
            return True, 0
        return False, 0

    def close(self):
        for key in self.registered:
            user32.UnregisterHotKey(None, key)
