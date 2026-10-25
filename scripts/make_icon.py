"""Build the multi-size Windows icon (``alya.ico``) from the bundled artwork.

Run with the project virtual environment::

    .venv\\Scripts\\python.exe scripts\\make_icon.py
"""

from __future__ import annotations

import struct

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication

from silknet.ui.assets import LOGO_FILE, rounded_logo

SIZES = (16, 24, 32, 40, 48, 64, 128, 256)
OUTPUT = LOGO_FILE.with_suffix(".ico")


def _png_bytes(size: int) -> bytes:
    pixmap = rounded_logo(size, 0.22, device_ratio=1.0)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def main() -> int:
    app = QGuiApplication([])
    blobs = [(size, _png_bytes(size)) for size in SIZES]
    offset = 6 + 16 * len(blobs)
    entries: list[bytes] = []
    payloads: list[bytes] = []
    for size, blob in blobs:
        entries.append(
            struct.pack(
                "<BBBBHHII",
                0 if size >= 256 else size,
                0 if size >= 256 else size,
                0,
                0,
                1,
                32,
                len(blob),
                offset,
            )
        )
        payloads.append(blob)
        offset += len(blob)
    icon_bytes = struct.pack("<HHH", 0, 1, len(blobs)) + b"".join(entries) + b"".join(payloads)
    OUTPUT.write_bytes(icon_bytes)
    print("wrote", OUTPUT, len(icon_bytes), "bytes")
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
