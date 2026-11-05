"""The liquid-glass effect: real backdrop blur where the OS supports it.

- Windows 11: DWM system backdrop (Acrylic) + rounded corners + dark mode.
- Windows 10: the undocumented Acrylic blur-behind (SetWindowCompositionAttribute).
- KDE Plasma (X11): the _KDE_NET_WM_BLUR_BEHIND_REGION hint (so BOBOS OS blurs too).
- Everything else: a translucent frosted panel painted by the window itself.

If any native call fails we silently fall back to the painted glass, so the app
always runs – it just looks a little less blurry.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import byref, c_int, sizeof

# Palette for the painted-glass fallback and the UI tint.
TINT = (18, 20, 28)          # base glass colour (near-black navy)
TINT_ALPHA = 150             # 0..255; lower = more see-through
ACCENT = (120, 170, 255)     # cool blue accent
ACCENT2 = (170, 130, 255)    # violet, for gradients
BORDER_ALPHA = 46            # subtle white rim-light


def _enable_windows_blur(hwnd: int) -> bool:
    """Acrylic blur behind a frameless window (Windows 10 and 11).

    The documented Win11 system backdrop (DWMWA_SYSTEMBACKDROP_TYPE) needs a window
    frame, which Luma doesn't have, so the acrylic accent (which works for frameless
    windows on both 10 and 11) is the primary path; the backdrop is a fallback.
    """
    try:
        dwm = ctypes.windll.dwmapi
    except (AttributeError, OSError):
        return False

    class MARGINS(ctypes.Structure):
        _fields_ = [("left", c_int), ("right", c_int), ("top", c_int), ("bottom", c_int)]

    try:
        # let DWM draw into the whole client area
        dwm.DwmExtendFrameIntoClientArea(hwnd, byref(MARGINS(-1, -1, -1, -1)))
        # DWMWA_USE_IMMERSIVE_DARK_MODE = 20, DWMWA_WINDOW_CORNER_PREFERENCE = 33 (2 = round)
        dwm.DwmSetWindowAttribute(hwnd, 20, byref(c_int(1)), sizeof(c_int))
        dwm.DwmSetWindowAttribute(hwnd, 33, byref(c_int(2)), sizeof(c_int))
    except Exception:  # noqa: BLE001
        pass

    if _accent_acrylic(hwnd):
        return True
    try:
        # Win11 22H2+: DWMWA_SYSTEMBACKDROP_TYPE = 38, 4 = Acrylic
        return dwm.DwmSetWindowAttribute(hwnd, 38, byref(c_int(4)), sizeof(c_int)) == 0
    except Exception:  # noqa: BLE001
        return False


def _accent_acrylic(hwnd: int) -> bool:
    """SetWindowCompositionAttribute with ACCENT_ENABLE_ACRYLICBLURBEHIND (= 4)."""
    try:
        user32 = ctypes.windll.user32

        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [("AccentState", c_int), ("AccentFlags", c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", c_int)]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [("Attribute", c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]

        # GradientColor is ABGR: 0x66 alpha, dark navy tint laid over the blur
        accent = ACCENTPOLICY(4, 0, 0x66201812, 0)
        data = WINCOMPATTRDATA(19, ctypes.cast(byref(accent), ctypes.c_void_p), sizeof(accent))
        return user32.SetWindowCompositionAttribute(hwnd, byref(data)) != 0
    except Exception:  # noqa: BLE001
        return False


def _enable_kde_blur(widget) -> bool:
    """Ask KWin to blur behind the whole window (KDE Plasma / X11)."""
    try:
        from PySide6.QtGui import QGuiApplication
        native = QGuiApplication.platformName()
        if "xcb" not in native:
            return False
        from ctypes import cdll, util
        xlib_name = util.find_library("X11")
        if not xlib_name:
            return False
        xlib = cdll.LoadLibrary(xlib_name)
        # Declare the signatures: Display* is a 64-bit pointer and must not be truncated.
        xlib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        xlib.XOpenDisplay.restype = ctypes.c_void_p
        xlib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, c_int]
        xlib.XInternAtom.restype = ctypes.c_ulong
        xlib.XChangeProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
                                         c_int, c_int, ctypes.c_void_p, c_int]
        xlib.XFlush.argtypes = [ctypes.c_void_p]
        xlib.XCloseDisplay.argtypes = [ctypes.c_void_p]

        display = xlib.XOpenDisplay(None)
        if not display:
            return False
        try:
            atom = xlib.XInternAtom(display, b"_KDE_NET_WM_BLUR_BEHIND_REGION", 0)
            # an empty region (0 elements) tells KWin to blur behind the whole window
            # XA_CARDINAL = 6, format 32, PropModeReplace = 0
            xlib.XChangeProperty(display, int(widget.winId()), atom, 6, 32, 0, None, 0)
            xlib.XFlush(display)
        finally:
            xlib.XCloseDisplay(display)
        return True
    except Exception:  # noqa: BLE001
        return False


def apply_blur(widget) -> str:
    """Enable native backdrop blur for a frameless, translucent widget.

    Returns the backend that was used: 'windows', 'kde' or 'paint' (fallback).
    Call this once the widget has a native window (after show()).
    """
    if sys.platform.startswith("win"):
        if _enable_windows_blur(int(widget.winId())):
            return "windows"
        return "paint"
    if sys.platform == "darwin":
        # Qt can't host an NSVisualEffectView without extra native code; the painted
        # frosted panel already looks glassy over the desktop.
        return "paint"
    if _enable_kde_blur(widget):
        return "kde"
    return "paint"
