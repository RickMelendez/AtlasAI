"""
Entidad de dominio que representa el contexto de pantalla capturado por Atlas AI.

Almacena el texto extraído por OCR, la aplicación detectada, y los errores
identificados en el momento de la captura.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional
from uuid import uuid4


@dataclass
class ScreenContext:
    """
    Representa una captura de contexto de pantalla en un momento dado.

    Attributes:
        session_id: Session ID del WebSocket asociado
        ocr_text: Texto extraído de la pantalla mediante OCR
        app_name: Nombre de la aplicación detectada (VS Code, Chrome, etc.)
        id: Identificador único del contexto
        created_at: Timestamp de la captura
        detected_errors: Lista de errores identificados en pantalla
        language: Lenguaje de programación detectado (si aplica)
        url: URL extraída si el contexto es un navegador
        shell_type: Tipo de shell si el contexto es una terminal
        line_numbers: Números de línea referenciados en errores
        raw_analysis: Análisis de Claude sobre este contexto (opcional)
    """

    session_id: str
    ocr_text: str
    app_name: str = "unknown"
    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    detected_errors: List[str] = field(default_factory=list)
    language: Optional[str] = None
    url: Optional[str] = None
    shell_type: Optional[str] = None
    line_numbers: List[int] = field(default_factory=list)
    raw_analysis: Optional[str] = None

    def has_errors(self) -> bool:
        """Retorna True si se detectaron errores en la pantalla."""
        return len(self.detected_errors) > 0

    def is_coding_context(self) -> bool:
        """Retorna True si el contexto es de programación."""
        coding_apps = {
            "visual studio code",
            "sublime text",
            "notepad++",
            "vim",
            "neovim",
        }
        return self.app_name.lower() in coding_apps or self.language is not None

    def is_browser_context(self) -> bool:
        """Retorna True si el contexto es de un navegador."""
        browsers = {"chrome", "firefox", "edge", "safari", "opera"}
        return any(b in self.app_name.lower() for b in browsers)

    def is_terminal_context(self) -> bool:
        """Retorna True si el contexto es de una terminal."""
        return self.shell_type is not None

    def to_prompt_string(self) -> str:
        """
        Genera una representación en texto para incluir en prompts de Claude.

        Returns:
            String formateado con el contexto de pantalla
        """
        lines = [f"[Contexto de pantalla - {self.app_name}]"]

        if self.language:
            lines.append(f"Lenguaje detectado: {self.language}")

        if self.url:
            lines.append(f"URL: {self.url}")

        if self.shell_type:
            lines.append(f"Shell: {self.shell_type}")

        if self.detected_errors:
            lines.append("Errores detectados:")
            for error in self.detected_errors:
                lines.append(f"  - {error}")

        if self.ocr_text:
            lines.append(
                f"Texto en pantalla:\n{self.ocr_text[:1000]}"
            )  # Limitar a 1000 chars

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serializa la entidad a diccionario."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "ocr_text": self.ocr_text,
            "app_name": self.app_name,
            "created_at": self.created_at.isoformat(),
            "detected_errors": self.detected_errors,
            "language": self.language,
            "url": self.url,
            "shell_type": self.shell_type,
            "line_numbers": self.line_numbers,
            "raw_analysis": self.raw_analysis,
        }
