"""Platform backend selector.

`get_backend()` returns a module exposing the interface documented in
`base.py`. The rest of the app never imports platform code directly.

(Named hv_platform, not platform, to avoid shadowing the stdlib module.)
"""
import sys


def get_backend():
    if sys.platform == "darwin":
        from hv_platform import darwin
        return darwin
    if sys.platform == "win32":
        from hv_platform import win32
        return win32
    raise RuntimeError(f"unsupported platform: {sys.platform} "
                       "(HoyoVoice supports macOS and Windows)")
