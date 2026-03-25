import mss
import base64
from PIL import Image
import io


class MSSCaptureAdapter:
    """Captures the primary screen using mss. No permissions dialog. Windows/Mac/Linux."""

    def capture_primary_screen(self) -> str:
        """Capture primary monitor, return base64-encoded JPEG string."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor (index 0 is "all monitors")
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            img.thumbnail((1920, 1080))  # Cap resolution
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return base64.b64encode(buf.getvalue()).decode()
