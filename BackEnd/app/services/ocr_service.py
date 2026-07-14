"""Servicio de OCR para extracción de texto de PDFs.

Usa Tesseract (via pytesseract) + PyMuPDF para reconocer texto en PDFs
y LangChain text splitters para generar chunks semánticos.

Flujo: PDF → PyMuPDF (rasteriza página a imagen) → Tesseract OCR → texto.
"""
import logging
from pathlib import Path
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# DPI de renderizado de páginas. 500 es calidad ultra alta para escaneos difíciles.
# Garantiza que el OCR pueda leer la letra más diminuta de identificaciones oficiales.
_RENDER_DPI = 500


def _pdf_to_text_tesseract(pdf_path: str) -> str:
    """
    Convierte cada página del PDF a imagen con PyMuPDF y aplica Tesseract OCR.
    Retorna el texto completo concatenado de todas las páginas.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF no está instalado. Agrega 'pymupdf' a requirements.txt.") from e

    try:
        import pytesseract
        from PIL import Image, ImageOps
        import io
    except ImportError as e:
        raise RuntimeError(
            "pytesseract o Pillow no están instalados. "
            "Agrega 'pytesseract' y 'Pillow' a requirements.txt."
        ) from e

    doc = fitz.open(pdf_path)
    pages_text: list[str] = []

    zoom = _RENDER_DPI / 72  # 72 DPI es la resolución base de PDF
    mat = fitz.Matrix(zoom, zoom)

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

        # Convertir el pixmap a imagen PIL directamente desde bytes (sin disco)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Escala de grises + autocontraste: mejora drásticamente la lectura en
        # escaneos con fondos de seguridad/hologramas (ej. credenciales oficiales).
        img = ImageOps.grayscale(img)
        img = ImageOps.autocontrast(img, cutoff=2)

        # Tesseract: español como idioma principal, ingles como fallback.
        # psm 6 (bloque uniforme de texto) capta mejor los layouts densos en
        # columnas de identificaciones oficiales que psm 3 (segmentación automática).
        text = pytesseract.image_to_string(img, lang="spa+eng", config="--psm 6")
        pages_text.append(text)
        logger.debug(f"Página {page_num + 1}/{len(doc)} procesada con Tesseract.")

    doc.close()
    return "\n\n".join(pages_text)


class OCRService:
    def __init__(self):
        # Text splitter de LangChain para el RAG
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            is_separator_regex=False,
        )

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extrae texto de un archivo PDF usando Tesseract OCR.
        Soporta PDFs digitales y escaneados (imagen).
        """
        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"El archivo {pdf_path} no existe.")

        logger.info(f"Iniciando extracción OCR (Tesseract) para: {pdf_path}")

        text = _pdf_to_text_tesseract(pdf_path)

        line_count = len([l for l in text.splitlines() if l.strip()])
        logger.info(f"Extracción OCR completada. {line_count} líneas con contenido extraídas.")
        return text

    def get_document_chunks(self, text: str) -> list[str]:
        """
        Divide el texto crudo en fragmentos semánticos usando LangChain.
        """
        if not text.strip():
            return []

        chunks = self.text_splitter.split_text(text)
        return chunks


ocr_service = OCRService()
