"""
Tesseract Adapter - OCR usando Tesseract.

Implementa ScreenService usando Tesseract OCR para extraer texto
de imágenes de pantalla y detectar contextos de aplicaciones.
"""

import io
import logging
import re
from typing import Any, Dict, Optional

import pytesseract
from PIL import Image

from ...application.interfaces.screen_service import ScreenService

logger = logging.getLogger(__name__)


class TesseractAdapter(ScreenService):
    """
    Adapter para Tesseract OCR.

    Usa Tesseract para:
    - Extraer texto de imágenes de pantalla
    - Detectar contexto de aplicaciones (VS Code, browser, terminal)
    - Identificar errores visibles en pantalla
    """

    def __init__(self):
        """
        Inicializa el adapter de Tesseract.

        Auto-detecta el ejecutable de Tesseract según el sistema operativo:
        - Windows: busca en 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
        - Linux/Mac: usa el PATH del sistema (instalado via apt/brew)
        """
        import shutil
        import sys

        if sys.platform == "win32":
            # Path por defecto de Chocolatey / instalador de UB-Mannheim
            win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
            if shutil.which("tesseract") is None:
                # Tesseract no está en PATH — usar path absoluto
                pytesseract.pytesseract.tesseract_cmd = win_path
                logger.info(f"✅ TesseractAdapter: using Windows path → {win_path}")
            else:
                logger.info("✅ TesseractAdapter: Tesseract found in PATH")
        else:
            # Linux / macOS — asumimos que está en PATH vía apt/brew
            if shutil.which("tesseract") is None:
                logger.warning(
                    "⚠️  Tesseract not found in PATH. "
                    "Install with: sudo apt-get install tesseract-ocr"
                )
            else:
                logger.info("✅ TesseractAdapter initialized (Linux/macOS)")

    async def extract_text_from_image(
        self, image_data: bytes, language: str = "eng"
    ) -> str:
        """
        Extrae texto de una imagen usando OCR.

        Args:
            image_data: Datos de la imagen (PNG, JPG, etc.)
            language: Idioma para OCR ("eng", "spa", "eng+spa")

        Returns:
            Texto extraído de la imagen

        Raises:
            Exception: Si ocurre un error en la extracción
        """
        try:
            # Convertir bytes a imagen PIL
            image = Image.open(io.BytesIO(image_data))

            # Extraer texto con Tesseract
            # PSM 3 = Automatic page segmentation (default)
            # PSM 11 = Sparse text (mejor para UIs modernas)
            custom_config = r"--oem 3 --psm 11"

            text = pytesseract.image_to_string(
                image, lang=language, config=custom_config
            )

            logger.info(f"Extracted {len(text)} characters from screen")
            return text.strip()

        except Exception as e:
            logger.error(f"Error extracting text with Tesseract: {e}")
            raise

    async def detect_app_context(self, screen_text: str) -> Dict[str, Any]:
        """
        Detecta el contexto de la aplicación activa basándose en el texto.

        Args:
            screen_text: Texto extraído de la pantalla

        Returns:
            Diccionario con información del contexto
        """
        try:
            context = {"app": "unknown", "details": {}}

            text_lower = screen_text.lower()

            # Detectar VS Code
            if any(
                keyword in text_lower
                for keyword in ["visual studio code", "vscode", "typescript", "src/"]
            ):
                context["app"] = "vscode"
                context["details"] = {
                    "has_errors": "error" in text_lower or "warning" in text_lower,
                    "language": self._detect_programming_language(screen_text),
                }

            # Detectar navegador
            elif any(
                keyword in text_lower
                for keyword in [
                    "chrome",
                    "firefox",
                    "safari",
                    "http://",
                    "https://",
                    "localhost",
                ]
            ):
                context["app"] = "browser"
                context["details"] = {
                    "has_errors": "error" in text_lower
                    or "failed to load" in text_lower,
                    "url_detected": self._extract_url(screen_text),
                }

            # Detectar terminal
            elif any(
                keyword in text_lower
                for keyword in ["bash", "powershell", "cmd", "$", "~/"]
            ):
                context["app"] = "terminal"
                context["details"] = {
                    "has_errors": "error" in text_lower or "failed" in text_lower,
                    "shell_type": self._detect_shell_type(screen_text),
                }

            # Detectar IDE genérico
            elif any(
                keyword in text_lower
                for keyword in ["class", "function", "import", "def ", "const ", "let "]
            ):
                context["app"] = "code_editor"
                context["details"] = {
                    "language": self._detect_programming_language(screen_text)
                }

            logger.info(f"Detected app context: {context['app']}")
            return context

        except Exception as e:
            logger.error(f"Error detecting app context: {e}")
            return {"app": "unknown", "details": {}}

    async def detect_errors(
        self, screen_text: str, app_context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Detecta errores visibles en el texto de pantalla.

        Args:
            screen_text: Texto de la pantalla
            app_context: Contexto de la aplicación activa

        Returns:
            Diccionario con errores detectados
        """
        try:
            result = {
                "has_error": False,
                "error_type": None,
                "error_message": "",
                "line_number": None,
            }

            text_lower = screen_text.lower()

            # Patrones de error comunes
            error_patterns = [
                # JavaScript/TypeScript
                (r"error ts\d+:", "typescript_error"),
                (r"syntaxerror:", "syntax_error"),
                (r"typeerror:", "type_error"),
                (r"referenceerror:", "reference_error"),
                (r"uncaught exception:", "runtime_error"),
                # Python
                (r"traceback \(most recent call last\):", "python_error"),
                (r"nameerror:", "python_name_error"),
                (r"typeerror:", "python_type_error"),
                (r"valueerror:", "python_value_error"),
                # General
                (r"error:", "general_error"),
                (r"failed:", "failure"),
                (r"exception:", "exception"),
                (r"cannot find", "not_found_error"),
                (r"module not found", "import_error"),
                # HTTP/Network
                (r"404", "not_found"),
                (r"500", "server_error"),
                (r"cors", "cors_error"),
                (r"network error", "network_error"),
            ]

            # Buscar errores
            for pattern, error_type in error_patterns:
                match = re.search(pattern, text_lower)
                if match:
                    result["has_error"] = True
                    result["error_type"] = error_type

                    # Intentar extraer el mensaje de error (próximas 100 chars)
                    start = match.start()
                    result["error_message"] = screen_text[start : start + 200].strip()

                    # Intentar extraer número de línea
                    line_match = re.search(
                        r"line (\d+)", text_lower[max(0, start - 50) : start + 50]
                    )
                    if line_match:
                        result["line_number"] = int(line_match.group(1))

                    break

            if result["has_error"]:
                logger.warning(f"Error detected: {result['error_type']}")

            return result

        except Exception as e:
            logger.error(f"Error detecting errors in screen text: {e}")
            return {
                "has_error": False,
                "error_type": None,
                "error_message": "",
                "line_number": None,
            }

    def _detect_programming_language(self, text: str) -> Optional[str]:
        """Detecta el lenguaje de programación en el texto."""
        text_lower = text.lower()

        if "import react" in text_lower or "jsx" in text_lower or "tsx" in text_lower:
            return "typescript_react"
        elif "def " in text_lower and "import " in text_lower:
            return "python"
        elif "const " in text_lower or "let " in text_lower:
            return "javascript"
        elif "public class" in text_lower or "private void" in text_lower:
            return "java"
        elif "fn " in text_lower and "mut " in text_lower:
            return "rust"

        return None

    def _extract_url(self, text: str) -> Optional[str]:
        """Extrae URL del texto si existe."""
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        match = re.search(url_pattern, text)
        return match.group(0) if match else None

    def _detect_shell_type(self, text: str) -> Optional[str]:
        """Detecta el tipo de shell."""
        text_lower = text.lower()

        if "powershell" in text_lower or "ps>" in text_lower:
            return "powershell"
        elif "bash" in text_lower or "~/" in text:
            return "bash"
        elif "cmd" in text_lower or "c:\\" in text_lower:
            return "cmd"

        return None


# Singleton instance
_tesseract_adapter_instance: Optional[TesseractAdapter] = None


def get_tesseract_adapter() -> TesseractAdapter:
    """
    Obtiene la instancia singleton del TesseractAdapter.

    Returns:
        Instancia de TesseractAdapter
    """
    global _tesseract_adapter_instance
    if _tesseract_adapter_instance is None:
        _tesseract_adapter_instance = TesseractAdapter()
    return _tesseract_adapter_instance
