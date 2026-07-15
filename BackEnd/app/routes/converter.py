import json
import os
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.file_converter import FileConverterService
from app.services.standardization_service import StandardizationService
from app.services.nosql_service import NoSQLService
from app.utils.json_utils import safe_json_dumps
from typing import List, Dict, Any

router = APIRouter(
    prefix="/converter",
    tags=["converter"]
)

# Initialize services
converter_service = FileConverterService()
standardizer = StandardizationService()
nosql_service = NoSQLService()

# Directorio de logs dentro del contenedor (mapeado a BackEnd/data/migration_logs)
LOGS_BASE_DIR = "/app/data/migration_logs"

@router.get("/collections")
async def get_collections():
    """List all available collections in the NoSQL database."""
    return {"collections": nosql_service.list_collections()}

@router.post("/save")
async def save_excel_data(payload: Dict[str, Any]):
    """Save corrected Excel data to the selected collection."""
    sheet_name = payload.get("sheet_name")
    collection = payload.get("collection")
    data = payload.get("data")
    
    result_id, actual_collection = nosql_service.save_document(collection, data)
    return {"status": "success", "id": result_id, "collection": actual_collection}

@router.post("/upload", response_model=List[Dict[str, Any]])
async def upload_file_to_nosql(file: UploadFile = File(...)):
    """
    Upload a CSV or Excel file, standardize it via AI, and save it to NoSQL.
    Saves raw and final JSON to the project folder for auditing.
    """
    if not file.filename.endswith(('.csv', '.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Only .csv, .xlsx, and .xls are accepted."
        )

    try:
        # 1. Crear carpeta de sesión para este archivo específico
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_folder_name = f"{timestamp}_{file.filename}"
        session_path = os.path.join(LOGS_BASE_DIR, session_folder_name)
        os.makedirs(session_path, exist_ok=True)

        print(f"\n>>> [API] Procesando: {file.filename} -> Sesión: {session_folder_name} <<<")

        # 2. Extract raw JSON (Returns list of sheets)
        content = await file.read()
        all_sheets_data = await converter_service.convert_to_json(content, file.filename)
        
        # GUARDAR JSON CRUDO
        raw_file_path = os.path.join(session_path, "raw_extracted.json")
        with open(raw_file_path, "w", encoding="utf-8") as f:
            f.write(safe_json_dumps(all_sheets_data, indent=2, ensure_ascii=False))
        print(f"[API] Archivo crudo guardado en: {raw_file_path}")

        # 3. Process each sheet via AI
        final_results = []
        for sheet in all_sheets_data:
            sheet_name = sheet['sheet_name']

            # Standardize the entire sheet as a single document
            standardized_doc = await standardizer.standardize_sheet(sheet_name, sheet)

            # Save standardized result to file
            final_file_path = os.path.join(session_path, f"final_{sheet_name}.json")
            with open(final_file_path, "w", encoding="utf-8") as f:
                f.write(safe_json_dumps(standardized_doc, indent=2, ensure_ascii=False))

            # Guardar el documento con la estructura detectada por la IA
            final_results.append({
                "sheet": sheet_name,
                "data": standardized_doc,
                "metadata": standardized_doc.get('document_metadata', {}) if isinstance(standardized_doc, dict) else {}
            })
        print(f">>> [API] Proceso completado. Archivos disponibles en {session_path} <<<\n")
        return final_results

    except Exception as e:
        print(f"[API] CRITICAL ERROR: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during the migration process: {str(e)}"
        )
