"""Servicio de IA para RAG con Agente y herramientas.

Usa Ollama (CPU mode) con modelos Qwen para:
- Generar embeddings de documentos
- Responder preguntas usando un agente con tool-calling
"""
import logging
from typing import List, Optional

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from typing import Any

from app.core.config import settings
from app.services.vector_db_service import get_vector_store

logger = logging.getLogger(__name__)

# ─── Tools del Agente ───────────────────────────────────────────────────────


@tool
def search_document_content(query: str, document_id: str) -> str:
    """
    Busca fragmentos relevantes de texto dentro de un documento PDF específico.
    Usa esta herramienta SIEMPRE que necesites responder preguntas sobre el contenido
    de un documento cargado en el sistema.
    """
    logger.info(f"Tool ejecutado: Buscando '{query}' en doc_id: {document_id}")
    try:
        vector_store = get_vector_store()

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Filtro estricto de Qdrant para buscar solo en los chunks que pertenecen a este documento
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.document_id",
                    match=MatchValue(value=document_id)
                )
            ]
        )

        # Aumentamos a k=15 para traer más trozos de la tabla y no perder filas
        results = vector_store.similarity_search(query, k=15, filter=qdrant_filter)

        if not results:
            return "No se encontró información relevante en el documento."

        context = "\n\n---\n\n".join([doc.page_content for doc in results])
        return context
    except Exception as e:
        logger.error(f"Error en búsqueda vectorial: {e}")
        return f"Error al buscar en el documento: {str(e)}"


@tool
def get_asset_info(asset_code: str) -> str:
    """
    Busca información oficial y en tiempo real sobre un activo en la base de datos SQL (SGA).
    Usa esta herramienta cuando el usuario te pregunte sobre el estado del activo en el sistema,
    su descripción oficial, número de serie, o si está asignado actualmente.
    """
    logger.info(f"Tool ejecutado: Buscando info SQL del activo: {asset_code}")
    from app.core.database import SessionLocal
    from app.models.activo import Activo

    db = SessionLocal()
    try:
        activo = db.query(Activo).filter_by(AssetCode=asset_code).first()
        if not activo:
            return f"El activo con código {asset_code} no fue encontrado en la base de datos SQL del sistema."

        return (
            f"Información Oficial del Sistema:\n"
            f"- Código: {activo.AssetCode}\n"
            f"- Descripción: {activo.Description}\n"
            f"- Estado Actual: {activo.Status}\n"
            f"- Número de Serie: {activo.SerialNumber}\n"
        )
    finally:
        db.close()


# ─── Servicio de IA ──────────────────────────────────────────────────────────

@tool
def save_asset_to_db(
    clave_vieja: str,
    nombre_activo: str,
    numero_serie: str = None,
    marca: str = None,
    color: str = None,
    custodio_original: str = None,
    estado_fisico: str = None,
    categoria: str = None,
    material: str = None,
    universal_code: str = None,
    progressive_number: str = None,
    dependency_number: str = None,
    responsible_unit: str = None,
    responsible_sub_unit: str = None,
    donation_invoice: str = None,
    donor_name: str = None,
    donation_cost_iva: float = None,
    contract_number: str = None
) -> str:
    """
    Guarda un activo extraído del documento directamente en la base de datos oficial del SGA.
    Acepta todos los campos opcionales del sistema de activos (marca, estado, categoría, custodio, códigos alternativos, unidad responsable, datos de contrato/factura).
    NO USES esta herramienta si la 'clave_vieja' o el 'nombre_activo' están vacíos. Si faltan, pregúntale al usuario antes de guardarlo.
    """
    logger.info(f"Tool ejecutado: Guardando activo en BD: {clave_vieja} - {nombre_activo}")
    
    if not clave_vieja or not nombre_activo:
        return "Error: Faltan datos requeridos. Necesitas al menos la 'clave vieja' (identificador) y el 'nombre/descripción' del activo. Por favor, solicítalos al usuario."

    from app.core.database import SessionLocal
    from app.schemas.activo import FilaActivoInput
    from app.services.excel_import_service import corregir_filas_activos

    db = SessionLocal()
    try:
        fila = FilaActivoInput(
            fila=1,
            clave_vieja=clave_vieja,
            Name=nombre_activo,
            SerialNumber=numero_serie,
            marca=marca,
            color=color,
            custodio_original=custodio_original,
            estado_fisico=estado_fisico,
            categoria=categoria,
            material=material,
            universal_code=universal_code,
            progressive_number=progressive_number,
            dependency_number=dependency_number,
            responsible_unit=responsible_unit,
            responsible_sub_unit=responsible_sub_unit,
            donation_invoice=donation_invoice,
            donor_name=donor_name,
            donation_cost_iva=donation_cost_iva,
            contract_number=contract_number
        )
        
        resultado = corregir_filas_activos(db, [fila], commit=True)
        if resultado.errores:
            error_msg = resultado.errores[0].error
            return f"Error al guardar el activo en la base de datos: {error_msg}. Por favor notifica al usuario del error."
            
        return f"Éxito: El activo '{nombre_activo}' (Clave: {clave_vieja}) se ha guardado correctamente en la base de datos."
    except Exception as e:
        logger.error(f"Error en save_asset_to_db: {e}")
        return f"Error interno al intentar guardar el activo: {str(e)}"
    finally:
        db.close()



class AIService:
    """Servicio centralizado de IA con inicialización lazy."""

    def __init__(self):
        self._agent_executor: Optional[Any] = None
        self.tools = [search_document_content, get_asset_info, save_asset_to_db]

        self.system_prompt = (
             "Eres un asistente experto en análisis de documentos corporativos "
             "(resguardos, contratos, facturas, inventarios). "
             "Tu objetivo es responder a las preguntas del usuario basándote "
             "ESTRICTAMENTE en la información que encuentres en el documento "
             "proporcionado usando tus herramientas. "
             "IMPORTANTE: Si el usuario te pide guardar activos (ej. 'guárdalos', 'guarda la tabla'), "
             "PRIMERO revisa exhaustivamente el documento, extrae todos los campos posibles de "
             "cada activo detectado en la tabla y MÚESTRASELO al usuario en una lista. "
             "PREGÚNTALE si está de acuerdo con la lista extraída y si quieres que procedas a guardarlos. "
             "SÓLO si el usuario te responde afirmativamente (ej. 'sí', 'procede'), "
             "entonces DEBES invocar la herramienta 'save_asset_to_db' secuencialmente MÚLTIPLES VECES "
             "(una vez por cada activo detectado), para inyectarlos en la base de datos. "
             "Solo pregúntale por datos faltantes si a un activo específico le falta la 'clave vieja' o el 'nombre'. "
             "Si no sabes la respuesta o no está en el documento, dilo claramente. "
             "No inventes datos. Responde siempre en español."
        )

    def _get_agent(self) -> Any:
        """Inicializa el agente de forma lazy para no bloquear el arranque del servidor."""
        if self._agent_executor is not None:
            return self._agent_executor

        logger.info(
            f"Inicializando agente IA con modelo {settings.llm_model} "
            f"en {settings.ollama_base_url}..."
        )

        llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.1,
        )

        self._agent_executor = create_react_agent(
            llm, 
            self.tools,
            prompt=self.system_prompt
        )

        logger.info("Agente IA inicializado correctamente.")
        return self._agent_executor

    def process_and_index_chunks(
        self, chunks: List[str], document_id: str, entity_type: str
    ):
        """
        Toma fragmentos de texto, los convierte en objetos Document de LangChain
        y los inyecta en la base de datos vectorial Qdrant.
        """
        vector_store = get_vector_store()

        documents = []
        for i, chunk in enumerate(chunks):
            doc = Document(
                page_content=chunk,
                metadata={
                    "document_id": document_id,
                    "entity_type": entity_type,
                    "chunk_index": i,
                },
            )
            documents.append(doc)

        logger.info(f"Indexando {len(documents)} chunks para el documento {document_id}")
        vector_store.add_documents(documents)
        logger.info(f"Indexación completada para {document_id}")

    def chat(
        self,
        user_query: str,
        document_id: str,
        chat_history: list = None,
    ) -> str:
        """
        Interactúa con el Agente IA permitiéndole usar sus tools de forma autónoma.
        """
        from langchain_core.messages import HumanMessage, AIMessage
        
        if chat_history is None:
            chat_history = []

        formatted_history = []
        for msg in chat_history:
            if msg.get("role") == "user":
                formatted_history.append(HumanMessage(content=msg.get("content", "")))
            elif msg.get("role") == "assistant":
                formatted_history.append(AIMessage(content=msg.get("content", "")))

        agent = self._get_agent()
        
        # Le inyectamos el document_id al inicio del mensaje del usuario
        # para que el agente sepa a qué documento hacer referencia en sus tools.
        enriched_query = f"[Contexto interno: el usuario se refiere al documento {document_id}].\nUsuario: {user_query}"
        
        state = {
            "messages": formatted_history + [HumanMessage(content=enriched_query)]
        }
        
        result = agent.invoke(state)
        
        # El resultado de langgraph contiene la lista actualizada de mensajes.
        # El último mensaje es la respuesta de la IA.
        last_message = result["messages"][-1]
        
        content = last_message.content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
                elif isinstance(part, str):
                    text_parts.append(part)
            return " ".join(text_parts)
        
        return str(content)

    def analyze_document(self, document_id: str) -> Optional[dict]:
        """
        Analiza un documento de forma estructurada para detectar si pertenece a una
        entidad clave (Activo, Resguardo, Personal) y extrae sus datos principales.
        """
        from app.schemas.ai_extraction import DocumentExtraction
        
        vector_store = get_vector_store()
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        qdrant_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.document_id",
                    match=MatchValue(value=document_id)
                )
            ]
        )
        
        # Recuperamos los primeros 10 chunks del documento (suele ser suficiente para clasificar)
        results = vector_store.similarity_search(" ", k=1000, filter=qdrant_filter)
        if not results:
            return None
            
        context = "\n\n".join([doc.page_content for doc in results])
        
        # BUSCAR EXPERIENCIAS PREVIAS EN KNOWLEDGE BASE
        from app.services.vector_db_service import get_knowledge_vector_store
        kb_store = get_knowledge_vector_store()
        
        # OPTIMIZACIÓN: Solo enviar los primeros 300 caracteres (el título/encabezado del doc) 
        # para buscar documentos similares, en lugar de 2000. Ahorra 80% de cuota de tokens.
        query_text = f"Correcciones previas para este tipo de documento:\n{context[:300]}"
        past_experiences = kb_store.similarity_search(query_text, k=3)
        few_shot_prompt = ""
        if past_experiences:
            few_shot_prompt = "EXPERIENCIAS PREVIAS (Usa esto para aprender de errores pasados):\n"
            for i, exp in enumerate(past_experiences):
                few_shot_prompt += f"--- Ejemplo {i+1} ---\n{exp.page_content}\n"
        
        logger.info(f"Analizando estructura de document_id: {document_id}")
        
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            google_api_key=settings.gemini_api_key,
            temperature=0.0,
        )
        
        structured_llm = llm.with_structured_output(DocumentExtraction)
        
        prompt = (
            "Analiza el siguiente documento y extrae los datos solicitados en formato de tabla (lista de objetos). "
            "Si no es Activo, Personal o Resguardo, clasifícalo como 'Otro'.\n"
            "Presta especial atención a la sección de 'EXPERIENCIAS PREVIAS' si existe, para ver cómo el usuario corrigió extracciones anteriores y NO cometer los mismos errores.\n\n"
            f"{few_shot_prompt}\n"
            f"Documento a analizar:\n{context}"
        )
        
        try:
            extraction = structured_llm.invoke(prompt)
            if extraction:
                return extraction.model_dump()
            return None
        except Exception as e:
            logger.error(f"Error al analizar documento estructuradamente: {e}")
            return None

    def save_knowledge_experience(self, document_text: str, original_extraction: dict, corrected_extraction: dict):
        """Guarda la experiencia en la base de conocimientos vectorial."""
        from langchain_core.documents import Document
        from app.services.vector_db_service import get_knowledge_vector_store
        import json
        
        kb_store = get_knowledge_vector_store()
        
        experience_content = (
            f"TEXTO DEL DOCUMENTO ORIGINAL:\n{document_text[:4000]}\n\n"
            f"EXTRACCIÓN INCORRECTA (Lo que hizo la IA):\n{json.dumps(original_extraction, indent=2, ensure_ascii=False)}\n\n"
            f"EXTRACCIÓN CORRECTA (Lo que corrigió el usuario):\n{json.dumps(corrected_extraction, indent=2, ensure_ascii=False)}"
        )
        
        doc = Document(
            page_content=experience_content,
            metadata={
                "type": "correction_experience"
            }
        )
        
        kb_store.add_documents([doc])
        logger.info("Experiencia guardada en la Base de Conocimientos.")


# Instancia singleton (lazy — no inicializa el LLM al importar)
ai_service = AIService()
