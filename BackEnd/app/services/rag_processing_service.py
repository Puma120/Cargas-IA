"""Servicio de procesamiento RAG en background.

Contiene la lógica de background processing para OCR + Embeddings.
Separado de las rutas para evitar dependencias circulares.
"""
import logging
from app.core.database import SessionLocal
from app.models.rag import AiDocument
from app.services.ocr_service import ocr_service
from app.services.ai_service import ai_service

logger = logging.getLogger(__name__)


def process_document_background(document_id: int, entity_type: str, file_path: str):
    """Tarea en segundo plano para extraer texto (OCR) y generar embeddings (Qdrant)."""
    db = SessionLocal()
    try:
        # Registrar o actualizar estado en SQL
        doc_record = db.query(AiDocument).filter_by(
            EntityId=document_id, EntityType=entity_type
        ).first()

        if not doc_record:
            doc_record = AiDocument(
                EntityId=document_id,
                EntityType=entity_type,
                FileUrl=file_path,
                Status="PROCESSING_OCR",
            )
            db.add(doc_record)
        else:
            doc_record.Status = "PROCESSING_OCR"
        db.commit()

        # 1. Extraer texto con PaddleOCR
        logger.info(f"Extrayendo texto de {file_path}...")
        raw_text = ocr_service.extract_text_from_pdf(file_path)

        # 2. Dividir en chunks
        chunks = ocr_service.get_document_chunks(raw_text)

        if not chunks:
            raise ValueError("No se pudo extraer texto legible del documento.")

        # 3. Vectorizar e indexar en Qdrant
        doc_record.Status = "PROCESSING_VECTOR"
        db.commit()
        str_doc_id = f"{entity_type}_{document_id}"
        ai_service.process_and_index_chunks(
            chunks, document_id=str_doc_id, entity_type=entity_type
        )
        
        # 4. Extraer estructura automáticamente
        doc_record.Status = "PROCESSING_LLM"
        db.commit()
        logger.info(f"Iniciando extracción estructurada de {str_doc_id}...")
        extracted_data = ai_service.analyze_document(str_doc_id)
        if extracted_data:
            import json
            doc_record.ExtractedData = json.dumps(extracted_data)

            # Guardar activos individualmente
            from app.models.rag import Activos_BD
            from sqlalchemy import or_
            activos_list = extracted_data.get("activos") or []
            for act in activos_list:
                clave_v = act.get("clave_vieja")
                num_ser = act.get("numero_serie")
                
                is_duplicate = False
                # Validar duplicado si existe clave_vieja o numero_serie
                if clave_v or num_ser:
                    filters = []
                    if clave_v:
                        filters.append(Activos_BD.ClaveVieja == clave_v)
                    if num_ser:
                        filters.append(Activos_BD.NumeroSerie == num_ser)
                    
                    dup_count = db.query(Activos_BD).filter(or_(*filters)).count()
                    if dup_count > 0:
                        is_duplicate = True
                
                nuevo_activo = Activos_BD(
                    AiDocumentId=doc_record.DocumentId,
                    CodigoUniversal=act.get("universal_code"),
                    NumeroProgresivo=act.get("progressive_number"),
                    ClaveVieja=clave_v,
                    NumeroDependencia=act.get("dependency_number"),
                    UnidadResponsable=act.get("responsible_unit"),
                    SubUnidadResponsable=act.get("responsible_sub_unit"),
                    NombreActivo=act.get("nombre_activo"),
                    Marca=act.get("marca"),
                    Color=act.get("color"),
                    Material=act.get("material"),
                    NumeroSerie=num_ser,
                    EstadoFisico=act.get("estado_fisico"),
                    Categorizacion=act.get("categoria"),
                    NumeroFactura=act.get("donation_invoice"),
                    NombreDonante=act.get("donor_name"),
                    CostoIva=act.get("donation_cost_iva"),
                    NumeroActaContrato=act.get("contract_number"),
                    Custodio=act.get("custodio_original"),
                    IsDuplicate=is_duplicate
                )
                db.add(nuevo_activo)

            # Guardar comprobantes individualmente
            from app.models.rag import Comprobantes_BD
            comprobantes_list = extracted_data.get("comprobantes") or []
            for comp in comprobantes_list:
                folio = comp.get("folio")
                
                is_duplicate = False
                # Validar duplicado si existe folio
                if folio:
                    dup_count = db.query(Comprobantes_BD).filter(Comprobantes_BD.Folio == folio).count()
                    if dup_count > 0:
                        is_duplicate = True
                else:
                    # Alternativa: si no hay folio, buscar por nombre y periodo o fecha
                    nombre = comp.get("nombre")
                    periodo = comp.get("periodo_facturacion")
                    if nombre and periodo:
                        dup_count = db.query(Comprobantes_BD).filter(
                            Comprobantes_BD.Nombre == nombre,
                            Comprobantes_BD.PeriodoFacturacion == periodo
                        ).count()
                        if dup_count > 0:
                            is_duplicate = True

                nuevo_comp = Comprobantes_BD(
                    AiDocumentId=doc_record.DocumentId,
                    TipoServicio=comp.get("tipo_servicio"),
                    PeriodoFacturacion=comp.get("periodo_facturacion"),
                    MontoAPagar=comp.get("monto_a_pagar"),
                    FechaExpedicion=comp.get("fecha_expedicion"),
                    FechaPago=comp.get("fecha_pago"),
                    Nombre=comp.get("nombre"),
                    Domicilio=comp.get("domicilio"),
                    Folio=folio,
                    IsDuplicate=is_duplicate
                )
                db.add(nuevo_comp)

        # 5. Actualizar estado final
        doc_record.Status = "COMPLETED"
        db.commit()
        logger.info(f"Documento {str_doc_id} procesado exitosamente ({len(chunks)} chunks).")

    except Exception as e:
        logger.error(f"Error procesando documento {entity_type}_{document_id}: {e}")
        db.rollback()
        doc_record = db.query(AiDocument).filter_by(
            EntityId=document_id, EntityType=entity_type
        ).first()
        if doc_record:
            doc_record.Status = "ERROR"
            doc_record.ErrorMessage = str(e)[:1000]
            db.commit()
    finally:
        db.close()
