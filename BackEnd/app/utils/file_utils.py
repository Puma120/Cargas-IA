"""Utilidades para manejo de archivos subidos."""
import io
import re
from pathlib import Path

from pypdf import PdfReader


def asegurar_directorio(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitizar_nombre(nombre: str) -> str:
    """Elimina rutas y caracteres no seguros del nombre de archivo."""
    nombre = Path(nombre).name
    return re.sub(r"[^A-Za-z0-9._-]", "_", nombre)


def es_pdf_valido(contenido: bytes) -> bool:
    """Verifica que el contenido sea un PDF legible (no solo la extensión)."""
    try:
        reader = PdfReader(io.BytesIO(contenido))
        return len(reader.pages) > 0
    except Exception:
        return False


def guardar_archivo(directorio: Path, nombre: str, contenido: bytes) -> Path:
    asegurar_directorio(directorio)
    destino = directorio / sanitizar_nombre(nombre)
    destino.write_bytes(contenido)
    return destino
