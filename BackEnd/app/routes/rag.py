"""Endpoints RAG — Procesamiento de documentos y Chat con IA."""
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.rag import AiDocument
from app.services.rag_processing_service import process_document_background
from app.services.ai_service import ai_service

router = APIRouter(tags=["RAG"])


class ProcessDocumentRequest(BaseModel):
    document_id: int
    entity_type: str
    file_path: str


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    document_id: str
    query: str
    chat_history: Optional[List[ChatMessage]] = []

from fastapi import UploadFile, File
import os
import uuid
from app.core.config import UPLOAD_DIR

import hashlib

@router.post("/rag/upload")
async def upload_file(file: UploadFile = File(...), db: Session = Depends(get_db)):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    content = await file.read()
    file_hash = hashlib.md5(content).hexdigest()
    file_id = file_hash[:10]
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    record = db.query(AiDocument).filter(AiDocument.FileUrl == file_path).first()
    if record:
        return {"document_id": record.EntityId, "entity_type": record.EntityType, "file_path": file_path, "duplicate": True}
        
    with open(file_path, "wb") as f:
        f.write(content)
    return {"document_id": int(file_hash[:8], 16) % 100000, "entity_type": "PDF", "file_path": file_path, "duplicate": False}



@router.post("/rag/process", status_code=202)
def process_document(
    request: ProcessDocumentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Encola un documento PDF para ser procesado por la IA (OCR + Embeddings).
    """
    # Verificamos si ya está procesado o en progreso
    record = db.query(AiDocument).filter_by(
        EntityId=request.document_id, EntityType=request.entity_type
    ).first()

    if record and record.Status in ["COMPLETED", "PROCESSING"]:
        return {"message": f"Documento ya se encuentra en estado: {record.Status}"}

    background_tasks.add_task(
        process_document_background,
        request.document_id,
        request.entity_type,
        request.file_path,
    )

    return {"message": "Documento encolado para procesamiento RAG."}


class SaveAndLearnRequest(BaseModel):
    document_id: str
    original_extraction: dict
    corrected_data: list
    document_text: Optional[str] = None
    data_type: str = "activos"

@router.post("/rag/save-and-learn")
def save_and_learn(request: SaveAndLearnRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Guarda la experiencia en la Base Vectorial."""
    from app.services.vector_db_service import get_vector_store
    
    # Recuperar el texto original del documento
    doc_text = request.document_text
    if not doc_text:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        vstore = get_vector_store()
        q_filter = Filter(must=[FieldCondition(key="metadata.document_id", match=MatchValue(value=request.document_id))])
        results = vstore.similarity_search(" ", k=1000, filter=q_filter)
        doc_text = "\n\n".join([d.page_content for d in results])
        
    # 3. Guardar en SQLite local
    if request.data_type == "activos":
        from app.models.rag import Activos_BD
        for act in request.corrected_data:
            if "db_id" in act and act["db_id"]:
                db_act = db.query(Activos_BD).filter_by(Id=act["db_id"]).first()
                if db_act:
                    db_act.ClaveVieja = act.get("clave_vieja", db_act.ClaveVieja)
                    db_act.NombreActivo = act.get("nombre_activo", db_act.NombreActivo)
                    db_act.NumeroSerie = act.get("numero_serie", db_act.NumeroSerie)
                    db_act.Custodio = act.get("custodio", db_act.Custodio)
    elif request.data_type == "comprobantes":
        from app.models.rag import Comprobantes_BD
        for comp in request.corrected_data:
            if "db_id" in comp and comp["db_id"]:
                db_comp = db.query(Comprobantes_BD).filter_by(Id=comp["db_id"]).first()
                if db_comp:
                    db_comp.TipoServicio = comp.get("tipo_servicio", db_comp.TipoServicio)
                    db_comp.PeriodoFacturacion = comp.get("periodo_facturacion", db_comp.PeriodoFacturacion)
                    db_comp.MontoAPagar = comp.get("monto_a_pagar", db_comp.MontoAPagar)
                    db_comp.Nombre = comp.get("nombre", db_comp.Nombre)
                    db_comp.Domicilio = comp.get("domicilio", db_comp.Domicilio)
                    db_comp.Folio = comp.get("folio", db_comp.Folio)
    db.commit()

    # 4. Guardar en Knowledge Base (Background)
    background_tasks.add_task(
        ai_service.save_knowledge_experience,
        document_text=doc_text,
        original_extraction=request.original_extraction,
        corrected_extraction={"activos": request.corrected_data}
    )
    
    return {"message": "Experiencia registrada en la base de datos de IA.", "inserted": len(request.corrected_data)}

@router.get("/rag/status/{entity_type}/{entity_id}")
def get_document_status(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
):
    """
    Consulta el estado de procesamiento RAG de un documento.
    """
    record = db.query(AiDocument).filter_by(
        EntityId=entity_id, EntityType=entity_type
    ).first()

    if not record:
        return {"status": "NOT_FOUND", "message": "Documento no ha sido procesado."}

    extracted_data = None
    if record.Status == "COMPLETED":
        from app.models.rag import Activos_BD, Comprobantes_BD, CFDI_BD, Identificacion_BD, ActaConstitutiva_BD

        document_type = None
        if record.ExtractedData:
            import json
            try:
                document_type = json.loads(record.ExtractedData).get("entity_type")
            except (json.JSONDecodeError, AttributeError):
                pass

        activos = db.query(Activos_BD).filter_by(AiDocumentId=record.DocumentId).all()
        activos_list = []
        for a in activos:
            activos_list.append({
                "universal_code": a.CodigoUniversal,
                "progressive_number": a.NumeroProgresivo,
                "clave_vieja": a.ClaveVieja,
                "dependency_number": a.NumeroDependencia,
                "responsible_unit": a.UnidadResponsable,
                "responsible_sub_unit": a.SubUnidadResponsable,
                "nombre_activo": a.NombreActivo,
                "marca": a.Marca,
                "color": a.Color,
                "material": a.Material,
                "numero_serie": a.NumeroSerie,
                "estado_fisico": a.EstadoFisico,
                "categoria": a.Categorizacion,
                "donation_invoice": a.NumeroFactura,
                "donor_name": a.NombreDonante,
                "donation_cost_iva": a.CostoIva,
                "contract_number": a.NumeroActaContrato,
                "custodio_original": a.Custodio,
                "custodio": a.Custodio,
                "is_duplicate": a.IsDuplicate,
                "db_id": a.Id
            })
            
        comprobantes = db.query(Comprobantes_BD).filter_by(AiDocumentId=record.DocumentId).all()
        comprobantes_list = []
        for c in comprobantes:
            comprobantes_list.append({
                "tipo_servicio": c.TipoServicio,
                "periodo_facturacion": c.PeriodoFacturacion,
                "monto_a_pagar": c.MontoAPagar,
                "fecha_expedicion": c.FechaExpedicion,
                "fecha_pago": c.FechaPago,
                "nombre": c.Nombre,
                "domicilio": c.Domicilio,
                "folio": c.Folio,
                "is_duplicate": c.IsDuplicate,
                "db_id": c.Id
            })

        cfdis = db.query(CFDI_BD).filter_by(AiDocumentId=record.DocumentId).all()
        cfdis_list = []
        for cf in cfdis:
            cfdis_list.append({
                "uuid": cf.UUID,
                "rfc_emisor": cf.RfcEmisor,
                "rfc_receptor": cf.RfcReceptor,
                "fecha": cf.Fecha,
                "subtotal": cf.Subtotal,
                "iva": cf.Iva,
                "total": cf.Total,
                "metodo_pago": cf.MetodoPago,
                "forma_pago": cf.FormaPago,
                "moneda": cf.Moneda,
                "is_duplicate": cf.IsDuplicate,
                "db_id": cf.Id
            })

        identificaciones = db.query(Identificacion_BD).filter_by(AiDocumentId=record.DocumentId).all()
        ident_list = []
        for ident in identificaciones:
            ident_list.append({
                "tipo_identificacion": ident.TipoIdentificacion,
                "nombre": ident.Nombre,
                "curp": ident.CURP,
                "clave_elector": ident.ClaveElector,
                "numero_identificacion": ident.NumeroIdentificacion,
                "ocr": ident.OCR,
                "vigencia": ident.Vigencia,
                "domicilio": ident.Domicilio,
                "sexo": ident.Sexo,
                "seccion": ident.Seccion,
                "fecha_nacimiento": ident.FechaNacimiento,
                "is_duplicate": ident.IsDuplicate,
                "db_id": ident.Id
            })

        actas = db.query(ActaConstitutiva_BD).filter_by(AiDocumentId=record.DocumentId).all()
        actas_list = []
        for ac in actas:
            actas_list.append({
                "razon_social": ac.RazonSocial,
                "rfc": ac.RFC,
                "fecha_constitucion": ac.FechaConstitucion,
                "objeto_social": ac.ObjetoSocial,
                "representante_legal": ac.RepresentanteLegal,
                "notaria": ac.Notaria,
                "ciudad": ac.Ciudad,
                "notario": ac.Notario,
                "numero_escritura": ac.NumeroEscritura,
                "is_duplicate": ac.IsDuplicate,
                "db_id": ac.Id
            })
            
        extracted_data = {
            "entity_type": record.EntityType,
            "document_type": document_type,
            "activos": activos_list,
            "comprobantes": comprobantes_list,
            "cfdis": cfdis_list,
            "identificaciones": ident_list,
            "actas_constitutivas": actas_list,
        }

    return {
        "status": record.Status,
        "error_message": record.ErrorMessage,
        "extracted_data": extracted_data,
        "created_at": record.CreatedAt.isoformat() if record.CreatedAt else None,
    }

