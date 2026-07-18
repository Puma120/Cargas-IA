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

# DPI de renderizado de páginas. 300 es el estándar óptimo para Tesseract.
# Valores más altos (como 500) resaltan el ruido, los hologramas y los patrones de seguridad del fondo.
_RENDER_DPI = 900


import base64
from app.core.config import settings
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage

def _pdf_to_text_tesseract(pdf_path: str) -> str:
    """
    Convierte cada página del PDF a imagen con PyMuPDF y usa Gemini Multimodal 
    para extraer el texto de forma perfecta. Reemplaza a Tesseract para documentos 
    complejos como pasaportes e INEs que tienen hologramas y ruido.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("PyMuPDF no está instalado.") from e

    doc = fitz.open(pdf_path)
    
    zoom = 2.0  # ~144 DPI es excelente para Gemini Vision
    mat = fitz.Matrix(zoom, zoom)
    
    images_b64 = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img_bytes = pix.tobytes("jpeg")
        images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))
    
    doc.close()

    if not images_b64:
        return ""

    llm = ChatGoogleGenerativeAI(
        model="gemma-4-31b-it",
        google_api_key=settings.gemini_api_key,
        temperature=0.0
    )

    content = [
        {
            "type": "text", 
            "text": "Transcribe TODO el texto visible en estas imágenes con extrema precisión. "
                    "Asegúrate de extraer nombres, fechas, números de pasaporte o credencial, domicilios, "
                    "códigos MRZ, sexo y firmas. Ignora los hologramas, rostros o marcas de agua. "
                    "Devuelve estrictamente solo el texto plano transcrito."
        }
    ]

    for b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
        })

    try:
        msg = HumanMessage(content=content)
        response = llm.invoke([msg])
        text = response.content
        if isinstance(text, list):
            text = " ".join([str(t.get("text", t)) if isinstance(t, dict) else str(t) for t in text])
        return text
    except Exception as e:
        logger.error(f"Error usando Gemini para OCR: {e}")
        return ""


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
