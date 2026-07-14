import json
import logging
import ast
from typing import List, Dict, Any, Tuple
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from app.utils.json_utils import safe_json_dumps
import os

logger = logging.getLogger(__name__)

class StandardizationService:
    def __init__(self):
        # Modelo exacto solicitado
        self.llm = ChatGoogleGenerativeAI(model="gemma-4-31b-it")
        
        # Define the target schema based on ScirptSGA.sql
        self.schema_context = {
            "assets": [
                "AssetCode", "Name", "SerialNumber", "Model", "LocationId", 
                "AssetStatusId", "CustodianPersonId", "OwnershipType", 
                "AcquisitionDate", "PurchaseCost", "Manufacturer", "Year", 
                "Dimensions", "InvoiceNumber", "Supplier", "TotalCost"
            ],
            "tramites": [
                "WoNumber", "AssetId", "WoType", "PriorityId", "WoStatusId", 
                "ReportedDate", "DueDate", "Notes"
            ],
            "custodios": [
                "AssetId", "AssignedToId", "AssignedDate", "UnassignedDate", "Notes"
            ],
            "audit_log": [
                "Timestamp", "UserId", "Action", "Table", "OldValue", "NewValue"
            ]
        }

    async def standardize_sheet(self, sheet_name: str, sheet_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes a full sheet using the specialized governmental ETL prompt.
        """
        print(f"\n--- [AI AGENT] Analizando hoja: {sheet_name} ---")
        
        system_prompt = (
            "PROMPT DE SISTEMA — Estandarización de Excel Gubernamental a JSON Estructurado\n\n"
            "1. ROL\n"
            "Eres un agente de ETL especializado en normalizar datos extraídos de archivos Excel gubernamentales/administrativos con formato variable (activos, trámites, inventarios) hacia un esquema NoSQL predefinido. Tu única salida válida es JSON. No generas explicaciones, texto libre, ni comentarios fuera de la estructura solicitada.\n\n"
            "2. CONTEXTO DE ENTRADA\n"
            "Vas a recibir un JSON crudo producido por la Fase 1 de extracción, que ya viene pre-segmentado en zonas:\n"
            "- document_metadata_raw: bloque de letterhead institucional, domicilio, dependencia.\n"
            "- form_selections_raw: campos tipo checkbox/opción múltiple.\n"
            "- table_rows_raw: los registros tabulares reales, con headers ya reconstruidos.\n"
            "- summary_rows_raw: filas de tipo SUBTOTAL/TOTAL/GRAN TOTAL.\n\n"
            f"3. ESQUEMA DE DESTINO\n{safe_json_dumps(self.schema_context, indent=2)}\n"
            "Primero identifica y clasifica el archivo procesando en la categoria de activos, custodios, tramites o audit log despues iguala o relaciona la informacion posible del documento al esquema correspondiente.\n\n"
            "5. REGLAS DURAS (no negociables)\n"
            "R1 — Un valor de celda = un campo, siempre. NUNCA combines, resumas ni concatenes dos o más valores originales distintos en un solo campo de salida. Un campo = un valor original.\n"
            "R2 — extra_data es una colección de campos individuales, no un texto libre. Formato obligatorio: "
            "{\"campo_normalizado\": {\"value\": \"...\", \"original_header\": \"...\"}}.\n"
            "R3 — No inventes datos. Si un campo del esquema no tiene equivalente claro, omítelo.\n"
            "R4 — Normaliza headers, no valores. Headers en snake_case sin acentos. Valores se preservan tal cual.\n"
            "R5 — Filas de resumen nunca se mezclan con registros. Van a summary_rows.\n"
            "R6 — Checkboxes/selección múltiple se resuelven identificando el marcador ('X', 'v') y devolviendo solo la etiqueta seleccionada.\n"
            "R7 — Consistencia de tipos. Numéricos como number, IDs con ceros a la izquierda como string.\n\n"
            "6. FORMATO DE SALIDA OBLIGATORIO\n"
            "Responde ÚNICAMENTE con este JSON, sin texto antes ni después:\n"
            "{\n"
            "  'document_metadata': { 'institucion': { }, 'dependencia': { }, 'form_selections': { }, 'extra_data': { } },\n"
            "  'records': [ { 'collection': '...', 'data': { 'campo_sql': '...', 'extra_data': { } }, '_confidence_notes': [] } ],\n"
            "  'summary_rows': [ { 'type': 'subtotal', 'source_row_index': 0, 'data': { } } ],\n"
            "  '_batch_meta': { 'records_in_batch': 0, 'fields_sent_to_extra_data': [] }\n"
            "}"
        )
        
        user_prompt = f"Sheet Name: {sheet_name}\nData:\n{safe_json_dumps(sheet_data, indent=2)}"
        
        try:
            print(f"[AI AGENT] Llamando a gemma-4-31b-it para analizar la hoja...")
            response = await self.llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            # Handle structured responses (thinking + text blocks)
            content_raw = response.content
            final_text = ""

            if isinstance(content_raw, list):
                # Find the block that contains the actual text response
                for block in content_raw:
                    if isinstance(block, dict) and block.get('type') == 'text':
                        final_text = block.get('text', '')
                        break
                # Fallback if no 'text' type found
                if not final_text:
                    final_text = "".join([str(b) for b in content_raw])
            else:
                final_text = str(content_raw)

            # Clean markdown formatting
            content = final_text.replace("```json", "").replace("```", "").strip()
            
            print(f"\n[AI AGENT] <<< RESPUESTA IA:")
            print(content)
            
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                print("[AI AGENT] JSON standard failed, trying ast.literal_eval for single-quote format...")
                try:
                    return ast.literal_eval(content)
                except Exception as e:
                    print(f"[AI AGENT] Critical parsing error: {e}")
                    raise e
            
        except Exception as e:
            print(f"[AI AGENT] ERROR analizando hoja {sheet_name}: {e}")
            return {
                "metadata": { "title": "Error", "date": "N/A", "collection": "generic_migration" },
                "records": []
            }
