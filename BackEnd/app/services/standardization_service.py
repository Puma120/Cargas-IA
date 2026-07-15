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
        # Modelo cambiado a gemini-3.1-flash-lite para evitar cuotas agotadas
        self.llm = ChatGoogleGenerativeAI(model="gemini-3.1-flash-lite")
        
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
            "PROMPT DE SISTEMA — Estandarización de Excel Gubernamental a JSON Estructurado v2\n\n"
            "Principio general\n"
            "No dependas de una lista fija de nombres de campo para reconocer qué es un documento gubernamental válido. Los formatos varían (BM04 hoy, otros formatos mañana), pero los patrones estructurales se repiten: letterhead institucional, bloque de metadatos del trámite, grupos de selección tipo checkbox, tabla de registros con encabezados a uno o dos niveles, filas de subtotal. Tu trabajo es reconocer el patrón y mapear su función, no memorizar nombres de columna exactos. Si ves un esquema de destino (colecciones/campos SQL) en el contexto, úsalo como guía de mapeo preferente — pero si un documento no encaja perfectamente en ese esquema, no fuerces ni descartes: coloca el dato en extra_data con su header original intacto. El esquema es una ayuda, no una jaula.\n\n"
            "Regla de oro — Cobertura verificable\n"
            "Todo valor no vacío que exista en sheet_cells_raw debe aparecer exactamente una vez en tu salida (mapeado al esquema o en extra_data), con una excepción: cuando un mismo valor está duplicado únicamente porque ocupaba un rango de celdas combinadas (mismo valor repetido en celdas contiguas de la fila/columna fuente), cuenta como un solo dato de origen, no como N datos.\n"
            "Antes de cerrar tu respuesta, para cada fila de origen — sin importar si es _row_role_guess: 'body' o 'document_metadata' — compara:\n"
            "1. valores_origen_unicos = número de valores distintos no vacíos en esa fila (después de colapsar duplicados por merge).\n"
            "2. valores_en_salida = número de campos que produjiste para esa fila (esquema + extra_data, sin contar campos inferidos).\n"
            "Si valores_en_salida < valores_origen_unicos, no está terminado — te falta al menos un campo. Vuelve a revisar la fila cruda y agrégalo. Reporta ambos números en _confidence_notes de cada registro o elemento de metadata: 'coverage': '7/7' o, si no cuadra, 'coverage': '5/7 — revisar'.\n\n"
            "Nota para bloques de jerarquía (Letterhead):\n"
            "Cuando varias filas consecutivas de document_metadata_raw contengan un solo valor distinto cada una (ej. niveles de una institución: Secretaría -> Subsecretaría -> Dirección), cada fila es un dato de origen independiente. NO te quedes solo con el primer nivel; cada fila debe aparecer en la salida, ya sea dentro de la estructura de jerarquía o como entradas separadas en document_metadata.extra_data.\n\n"
            "Regla de selección — Solo cuenta lo que tiene evidencia\n"
            "Un ítem de un grupo tipo checkbox/opción múltiple (destino final, motivos, sí/no, etc.) solo se reporta como seleccionado si existe una celda distinta y adyacente al label que contiene un marcador afirmativo explícito ('X', 'v', celda sombreada u otro indicio de selección disponible en la metadata) — y ese marcador NO es simplemente el mismo texto del label repetido por relleno de celda combinada.\n"
            "Si el label aparece repetido en varias celdas con el mismo texto exacto y no hay una celda separada con un marcador, eso no es una selección — es ruido de formato. En ese caso:\n"
            "- No lo incluyas en la lista de seleccionados.\n"
            "- Si el grupo completo no tiene ningún marcador visible, reporta ese campo como null y anota en _confidence_notes: 'no se encontró marcador de selección en el grupo [nombre del grupo]; posible campo no diligenciado'.\n\n"
            "Campos inferidos — permitidos, pero marcados\n"
            "Si derivas un valor útil que no es una celda original — por ejemplo, extraer '6G7J3LA' como modelo desde el texto de una descripción más larga — está permitido:\n"
            "- El campo original permanece intacto en la salida.\n"
            "- El campo inferido debe marcarse 'inferred': true: {\"Model\": { \"value\": \"6G7J3LA\", \"inferred\": true, \"derived_from\": \"Name\" }}.\n"
            "- Los campos inferidos NO cuentan para la reconciliación de cobertura.\n\n"
            "extra_data sigue siendo obligatorio para todo lo no mapeado.\n\n"
            "Filas de resumen (_row_role_guess: 'summary')\n"
            "Van a summary_rows, nunca mezcladas con registros. Si hay varios bloques de subtotal, repórtalos como entradas separadas.\n\n"
            "Autochequeo final antes de responder\n"
            "1. ¿Cada fila body tiene su nota de coverage y cuadra?\n"
            "2. ¿Cada elemento en form_selections tiene un marcador real?\n"
            "3. ¿Los campos inferidos están marcados?\n"
            "4. ¿La salida es JSON puro?\n\n"
            "3. REGLAS DE MAPEO Y ESTRUCTURA\n"
            "- DEBES incluir TODOS los campos del esquema de destino, incluso si no tienen valor (asígnalos como null).\n"
            "- SIEMPRE preserva TODA la información del Excel original. Cualquier dato que no encaje en el esquema principal DEBE ir a `extra_data` dentro del registro correspondiente.\n"
            "- Si una pieza de información es global (ej. nombre de dependencia, fecha del formato), ponla en `document_metadata.extra_data`.\n"
            "- Si una pieza de información pertenece a un activo/registro específico, ponla en `records[].data.extra_data`.\n"
            "- NUNCA descartes columnas, subtotales secundarios, o notas al pie solo porque no parecen importantes; si están en el documento, DEBEN estar en el JSON.\n"
            "- DE-DUPLICACIÓN: Verifica antes de agregar cualquier dato. Si un valor ya fue capturado en un campo del esquema o en extra_data de un nivel superior (metadata), no lo dupliques en registros individuales a menos que sea una relación explícita.\n"
            "- Sé flexible: si el nombre de una columna varía ligeramente, infiere su propósito basándote en su contenido y posición, y asígnala al campo correspondiente del esquema, moviendo el nombre original a `extra_data`.\n\n"
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
            print(f"[AI AGENT] Llamando a gemini-3.1-flash-lite para analizar la hoja...")
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
