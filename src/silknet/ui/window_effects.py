"""Native window tweaks for the frameless Alya SILKNET window.

The app paints its own rounded chrome with per-pixel alpha. No native acrylic
backdrop is requested: Windows tints the whole window rectangle (rounded
corners included) with an opaque dark layer, which hides the desktop and
cancels the intended rounded transparency. Only the DWM title-bar mode is kept
in sync so any system-drawn piece matches the current theme.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY = 19
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_DONOTROUND = 1

_GWL_STYLE = -16
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_SM_CXICON = 11
_SM_CXSMICON = 49

# Keep native icon handles alive for the lifetime of the process. Windows does
# not take ownership of HICONs returned by LoadImageW.
_TASKBAR_ICONS: list[int] = []


def _is_windows() -> bool:
    return sys.platform == "win32"


def _window_handle(window) -> int:
    try:
        return int(window.winId())
    except (AttributeError, TypeError, ValueError):
        return 0


def _set_dwm_attribute(handle: int, attribute: int, value: int) -> bool:
    try:
        dwmapi = ctypes.windll.dwmapi
        result = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(handle),
            wintypes.DWORD(attribute),
            ctypes.byref(ctypes.c_int(value)),
            wintypes.DWORD(ctypes.sizeof(ctypes.c_int)),
        )
        return result == 0
    except (AttributeError, OSError, ValueError):
        return False


def _ensure_taskbar_styles(handle: int) -> None:
    """Keep the taskbar button able to minimize and restore the window."""
    try:
        user32 = ctypes.windll.user32
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_style.restype = ctypes.c_ssize_t
        get_style.argtypes = (wintypes.HWND, ctypes.c_int)
        set_style.restype = ctypes.c_ssize_t
        set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        style = int(get_style(wintypes.HWND(handle), _GWL_STYLE))
        wanted = style | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_SYSMENU
        if wanted == style:
            return
        set_style(wintypes.HWND(handle), _GWL_STYLE, wanted)
        user32.SetWindowPos(
            wintypes.HWND(handle),
            wintypes.HWND(0),
            0,
            0,
            0,
            0,
            _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return


def configure_native_window(window, *, dark: bool) -> None:
    """Match the native frame to the theme without any native blur layer."""
    if not _is_windows():
        return
    handle = _window_handle(window)
    if not handle:
        return
    _ensure_taskbar_styles(handle)
    # Keep our own painted corner radius instead of a second DWM rounding.
    _set_dwm_attribute(handle, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_DONOTROUND)
    if not _set_dwm_attribute(handle, _DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark)):
        _set_dwm_attribute(handle, _DWMWA_USE_IMMERSIVE_DARK_MODE_LEGACY, int(dark))


def apply_taskbar_icon(window, icon_path: str | Path) -> bool:
    """Attach the bundled .ico directly to the native window.

    ``QApplication.setWindowIcon`` is not always forwarded for frameless,
    per-pixel-alpha windows: Windows can end up drawing a blank taskbar button
    even though the window icon exists in Qt. Sending ``WM_SETICON`` with both
    small and large HICONs makes the taskbar icon deterministic.

    Returns ``True`` when at least one icon slot was updated.
    """

    if not _is_windows():
        return False
    handle = _window_handle(window)
    path = Path(icon_path)
    if not handle or not path.exists():
        return False
    try:
        user32 = ctypes.windll.user32
        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.GetSystemMetrics.argtypes = (ctypes.c_int,)
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = (
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        )
        user32.SendMessageW.restype = wintypes.LPARAM
        user32.SendMessageW.argtypes = (
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        big = int(user32.GetSystemMetrics(_SM_CXICON)) or 32
        small = int(user32.GetSystemMetrics(_SM_CXSMICON)) or 16
        loaded = 0
        for size, slot in ((big, _ICON_BIG), (small, _ICON_SMALL)):
            hicon = user32.LoadImageW(
                None,
                str(path),
                _IMAGE_ICON,
                size,
                size,
                _LR_LOADFROMFILE,
            )
            if not hicon:
                continue
            _TASKBAR_ICONS.append(int(hicon))
            user32.SendMessageW(
                wintypes.HWND(handle),
                _WM_SETICON,
                wintypes.WPARAM(slot),
                wintypes.LPARAM(hicon),
            )
            loaded += 1
        if loaded:
            user32.SetWindowPos(
                wintypes.HWND(handle),
                wintypes.HWND(0),
                0,
                0,
                0,
                0,
                _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
            )
        return loaded > 0
    except (AttributeError, OSError, TypeError, ValueError):
        return False
