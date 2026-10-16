"""Read stable Windows clipboard snapshots without Qt's MIME cache."""
import ctypes
from ctypes import wintypes
import json
import struct

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImage

from store import png_bytes, text_payload

user = ctypes.WinDLL('user32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
shell = ctypes.WinDLL('shell32', use_last_error=True)
user.OpenClipboard.argtypes = [wintypes.HWND]
user.GetClipboardData.argtypes = [wintypes.UINT]
user.GetClipboardData.restype = wintypes.HANDLE
user.GetClipboardSequenceNumber.restype = wintypes.DWORD
user.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
kernel.GlobalLock.argtypes = [wintypes.HANDLE]
kernel.GlobalLock.restype = ctypes.c_void_p
kernel.GlobalSize.argtypes = [wintypes.HANDLE]
kernel.GlobalSize.restype = ctypes.c_size_t
kernel.GlobalUnlock.argtypes = [wintypes.HANDLE]
shell.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
shell.DragQueryFileW.restype = wintypes.UINT
PNG_FORMAT = user.RegisterClipboardFormatW('PNG')


def read_handle(handle):
    pointer = kernel.GlobalLock(handle) if handle else None
    if not pointer:
        return None
    try:
        return ctypes.string_at(pointer, kernel.GlobalSize(handle))
    finally:
        kernel.GlobalUnlock(handle)


def read_snapshot():
    if not user.OpenClipboard(None):
        return None
    try:
        payload = None
        files = user.GetClipboardData(15) if user.IsClipboardFormatAvailable(15) else None
        if files:
            paths = []
            for index in range(shell.DragQueryFileW(files, 0xffffffff, None, 0)):
                size = shell.DragQueryFileW(files, index, None, 0)
                buf = ctypes.create_unicode_buffer(size+1)
                shell.DragQueryFileW(files, index, buf, size+1)
                paths.append(QUrl.fromLocalFile(buf.value).toString())
            if paths:
                payload = ('file', json.dumps(paths, ensure_ascii=False), b'')
        if payload is None:
            for fmt in (PNG_FORMAT, 17, 8):
                if not user.IsClipboardFormatAvailable(fmt):
                    continue
                data = read_handle(user.GetClipboardData(fmt))
                if not data:
                    continue
                if fmt != PNG_FORMAT:
                    if len(data) < 40:
                        continue
                    header = struct.unpack_from('<I', data)[0]
                    bits = struct.unpack_from('<H', data, 14)[0]
                    compression, colors = struct.unpack_from('<I', data, 16)[0], struct.unpack_from('<I', data, 32)[0]
                    palette = colors*4 if colors else (4*(1 << bits) if bits <= 8 else 0)
                    masks = (12 if compression == 3 else 16 if compression == 6 else 0) if header == 40 else 0
                    offset = 14+header+palette+masks
                    data = struct.pack('<2sIHHI', b'BM', len(data)+14, 0, 0, offset)+data
                image = QImage.fromData(data)
                if not image.isNull():
                    payload = ('image', f'{image.width()} × {image.height()}', png_bytes(image))
                    break
        if payload is None and user.IsClipboardFormatAvailable(13):
            data = read_handle(user.GetClipboardData(13))
            if data:
                text = data.decode('utf-16-le', errors='replace').split('\0',1)[0]
                if text.strip():
                    payload = text_payload(text)
        # Delayed rendering may itself change the clipboard sequence.
        return user.GetClipboardSequenceNumber(), payload
    finally:
        user.CloseClipboard()
