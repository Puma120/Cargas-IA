"""Servicio de OCR para extracción de texto de PDFs.

Usa PaddleOCR para reconocer texto en imágenes/PDFs
y LangChain text splitters para generar chunks semánticos.
"""
import logging
from pathlib import Path
from typing import Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)

# Motor de OCR con inicialización lazy (evita fallos al importar)
_ocr_engine = None
_ocr_init_error: Optional[str] = None


def _get_ocr_engine():
    """Inicializa PaddleOCR de forma lazy en el primer uso."""
    global _ocr_engine, _ocr_init_error

    if _ocr_engine is not None:
        return _ocr_engine

    if _ocr_init_error is not None:
        raise RuntimeError(f"PaddleOCR no pudo inicializarse: {_ocr_init_error}")

    try:
        from paddleocr import PaddleOCR
        # NOTA: PaddleOCR >= 2.9 / PaddlePaddle >= 3.0 ya no aceptan `use_gpu`.
        # El runtime detecta automáticamente si hay GPU disponible; en CPU-only
        # simplemente se omite el parámetro.
        _ocr_engine = PaddleOCR(
            use_textline_orientation=True,
            lang='es',
            enable_mkldnn=False
        )
        logger.info("PaddleOCR inicializado correctamente (CPU mode).")
        return _ocr_engine
    except Exception as e:
        _ocr_init_error = str(e)
        logger.error(f"Error inicializando PaddleOCR: {e}")
        raise RuntimeError(f"PaddleOCR no pudo inicializarse: {e}")


class OCRService:
    def __init__(self):
        # Configuramos el text splitter de LangChain para el RAG
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            is_separator_regex=False,
        )

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        Extrae texto de un archivo PDF usando PaddleOCR visualmente de manera estricta.
        """
        engine = _get_ocr_engine()

        if not Path(pdf_path).exists():
            raise FileNotFoundError(f"El archivo {pdf_path} no existe.")

        logger.info(f"Iniciando extracción OCR estricta (visual) para: {pdf_path}")

        try:
            result = engine.ocr(pdf_path)

            full_text = []
            if result:
                for idx, page in enumerate(result):
                    if page:
                        # Soporte para PaddleOCR v3 / PaddleX
                        if isinstance(page, dict) and "rec_texts" in page:
                            texts = page["rec_texts"]
                            if texts:
                                # Filtrar posibles Nones
                                full_text.extend([t for t in texts if t])
                        # Soporte para PaddleOCR v2
                        elif isinstance(page, list):
                            for line in page:
                                if isinstance(line, (list, tuple)) and len(line) >= 2:
                                    text_tuple = line[1]
                                    if isinstance(text_tuple, (list, tuple)) and len(text_tuple) > 0:
                                        text = text_tuple[0]
                                        if text:
                                            full_text.append(text)

            final_text = "\n".join(full_text)
            logger.info(f"Extracción OCR completada. {len(full_text)} líneas extraídas.")
            return final_text

        except Exception as e:
            logger.error(f"Error durante OCR de {pdf_path}: {e}")
            raise

    def get_document_chunks(self, text: str) -> list[str]:
        """
        Divide el texto crudo en fragmentos semánticos usando LangChain.
        """
        if not text.strip():
            return []

        chunks = self.text_splitter.split_text(text)
        return chunks


ocr_service = OCRService()
