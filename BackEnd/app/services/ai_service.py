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


def _correct_curp_ocr_confusion(curp: Optional[str]) -> Optional[str]:
    """
    Corrige confusiones típicas de OCR ('0' vs 'O', 'I' vs '1') en un CURP,
    usando el patrón posicional oficial de 18 caracteres:
    LLLL DDDDDD L LL LLL A D
    (4 letras, 6 dígitos, 1 letra, 2 letras, 3 letras, 1 alfanumérico, 1 dígito).
    """
    if not curp or len(curp) != 18:
        return curp

    is_letter_position = [
        True, True, True, True,        # 1-4: letras
        False, False, False, False, False, False,  # 5-10: dígitos (fecha nacimiento)
        True,                          # 11: letra (H/M)
        True, True,                    # 12-13: letras
        True, True, True,              # 14-16: letras
        None,                          # 17: alfanumérico, no se corrige
        False,                         # 18: dígito
    ]

    chars = list(curp)
    for i, expects_letter in enumerate(is_letter_position):
        if expects_letter is True and chars[i] == '0':
            chars[i] = 'O'
        elif expects_letter is True and chars[i] == '1':
            chars[i] = 'I'
        elif expects_letter is False and chars[i] == 'O':
            chars[i] = '0'
        elif expects_letter is False and chars[i] == 'I':
            chars[i] = '1'

    return ''.join(chars)


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

@tool
def save_cfdi_to_db(
    uuid: str,
    rfc_emisor: str = None,
    rfc_receptor: str = None,
    fecha: str = None,
    subtotal: float = None,
    iva: float = None,
    total: float = None,
    metodo_pago: str = None,
    forma_pago: str = None,
    moneda: str = None
) -> str:
    """
    Guarda un CFDI (Comprobante Fiscal Digital por Internet) extraído de un documento en la base de datos.
    El campo 'uuid' es el único requerido. Los valores monetarios (subtotal, iva, total) deben ser
    números en pesos mexicanos (MXN) sin símbolo de moneda.
    NO USES esta herramienta si el 'uuid' está vacío o ausente.
    """
    logger.info(f"Tool ejecutado: Guardando CFDI en BD: UUID={uuid}")

    if not uuid:
        return "Error: Falta el UUID del CFDI. Es el campo requerido. Por favor solícitalo al usuario."

    from app.core.database import SessionLocal
    from app.models.rag import CFDI_BD

    db = SessionLocal()
    try:
        # Verificar duplicado por UUID
        existing = db.query(CFDI_BD).filter(CFDI_BD.UUID == uuid).first()
        is_duplicate = existing is not None

        nuevo_cfdi = CFDI_BD(
            AiDocumentId=0,  # Se actualiza en el flujo de procesamiento background
            UUID=uuid,
            RfcEmisor=rfc_emisor,
            RfcReceptor=rfc_receptor,
            Fecha=fecha,
            Subtotal=subtotal,
            Iva=iva,
            Total=total,
            MetodoPago=metodo_pago,
            FormaPago=forma_pago,
            Moneda=moneda or "MXN",
            IsDuplicate=is_duplicate
        )
        db.add(nuevo_cfdi)
        db.commit()
        dup_msg = " (DUPLICADO: ya existía un CFDI con este UUID)" if is_duplicate else ""
        return f"Éxito: CFDI con UUID '{uuid}' guardado en la base de datos.{dup_msg}"
    except Exception as e:
        logger.error(f"Error en save_cfdi_to_db: {e}")
        return f"Error interno al intentar guardar el CFDI: {str(e)}"
    finally:
        db.close()


@tool
def save_identificacion_to_db(
    tipo_identificacion: str,
    nombre: str,
    curp: str = None,
    clave_elector: str = None,
    numero_identificacion: str = None,
    ocr: str = None,
    vigencia: str = None,
    domicilio: str = None
) -> str:
    """
    Guarda los datos de una Identificación Oficial (INE, Pasaporte, Cédula Profesional) en la base de datos.
    Los campos 'tipo_identificacion' y 'nombre' son requeridos.
    NO USES esta herramienta si el 'nombre' o el 'tipo_identificacion' están vacíos o ausentes.
    """
    logger.info(f"Tool ejecutado: Guardando Identificacion en BD: {nombre} ({tipo_identificacion})")

    if not nombre or not tipo_identificacion:
        return "Error: Faltan datos requeridos (nombre o tipo_identificacion). Por favor solícitalos al usuario."

    from app.core.database import SessionLocal
    from app.models.rag import Identificacion_BD

    db = SessionLocal()
    try:
        # Verificar duplicado por CURP o numero_identificacion
        is_duplicate = False
        if curp:
            is_duplicate = db.query(Identificacion_BD).filter(Identificacion_BD.CURP == curp).count() > 0
        elif numero_identificacion:
            is_duplicate = db.query(Identificacion_BD).filter(Identificacion_BD.NumeroIdentificacion == numero_identificacion).count() > 0

        nueva_ident = Identificacion_BD(
            AiDocumentId=0,
            TipoIdentificacion=tipo_identificacion,
            Nombre=nombre,
            CURP=curp,
            ClaveElector=clave_elector,
            NumeroIdentificacion=numero_identificacion,
            OCR=ocr,
            Vigencia=vigencia,
            Domicilio=domicilio,
            IsDuplicate=is_duplicate
        )
        db.add(nueva_ident)
        db.commit()
        dup_msg = " (DUPLICADO: ya existía una identificación con esta CURP/número)" if is_duplicate else ""
        return f"Éxito: Identificación de '{nombre}' guardada en la base de datos.{dup_msg}"
    except Exception as e:
        logger.error(f"Error en save_identificacion_to_db: {e}")
        return f"Error interno al intentar guardar la Identificación: {str(e)}"
    finally:
        db.close()


@tool
def save_acta_constitutiva_to_db(
    razon_social: str,
    rfc: str = None,
    fecha_constitucion: str = None,
    objeto_social: str = None,
    representante_legal: str = None,
    notaria: str = None,
    ciudad: str = None,
    notario: str = None,
    numero_escritura: str = None
) -> str:
    """
    Guarda los datos de un Acta Constitutiva (escritura notarial de empresa) en la base de datos.
    El campo 'razon_social' es el único requerido.
    NO USES esta herramienta si la 'razon_social' está vacía o ausente.
    """
    logger.info(f"Tool ejecutado: Guardando Acta Constitutiva en BD: {razon_social}")

    if not razon_social:
        return "Error: Falta la razón social de la empresa. Es el campo requerido. Por favor solícitalo al usuario."

    from app.core.database import SessionLocal
    from app.models.rag import ActaConstitutiva_BD

    db = SessionLocal()
    try:
        # Verificar duplicado por RFC o razón social + número de escritura
        is_duplicate = False
        if rfc:
            is_duplicate = db.query(ActaConstitutiva_BD).filter(ActaConstitutiva_BD.RFC == rfc).count() > 0
        elif razon_social and numero_escritura:
            is_duplicate = db.query(ActaConstitutiva_BD).filter(
                ActaConstitutiva_BD.RazonSocial == razon_social,
                ActaConstitutiva_BD.NumeroEscritura == numero_escritura
            ).count() > 0

        nueva_acta = ActaConstitutiva_BD(
            AiDocumentId=0,
            RazonSocial=razon_social,
            RFC=rfc,
            FechaConstitucion=fecha_constitucion,
            ObjetoSocial=objeto_social,
            RepresentanteLegal=representante_legal,
            Notaria=notaria,
            Ciudad=ciudad,
            Notario=notario,
            NumeroEscritura=numero_escritura,
            IsDuplicate=is_duplicate
        )
        db.add(nueva_acta)
        db.commit()
        dup_msg = " (DUPLICADO: ya existía un acta con este RFC/escritura)" if is_duplicate else ""
        return f"Éxito: Acta Constitutiva de '{razon_social}' guardada en la base de datos.{dup_msg}"
    except Exception as e:
        logger.error(f"Error en save_acta_constitutiva_to_db: {e}")
        return f"Error interno al intentar guardar el Acta Constitutiva: {str(e)}"
    finally:
        db.close()


class AIService:
    """Servicio centralizado de IA con inicialización lazy."""

    def __init__(self):
        self._agent_executor: Optional[Any] = None
        self.tools = [
            search_document_content,
            get_asset_info,
            save_asset_to_db,
            save_cfdi_to_db,
            save_identificacion_to_db,
            save_acta_constitutiva_to_db,
        ]

        self.system_prompt = (
             "Eres un asistente experto en análisis de documentos corporativos "
             "(resguardos, contratos, facturas, inventarios, CFDIs, identificaciones oficiales, actas constitutivas). "
             "Tu objetivo es responder a las preguntas del usuario basándote "
             "ESTRICTAMENTE en la información que encuentres en el documento "
             "proporcionado usando tus herramientas. "
             "IMPORTANTE: Si el usuario te pide guardar activos (ej. 'guárdalos', 'guarda la tabla'), "
             "PRIMERO revisa exhaustivamente el documento, extrae todos los campos posibles de "
             "cada activo detectado en la tabla y MÚESTRASELO al usuario en una lista. "
             "PREGÚNTALE si está de acuerdo con la lista extraída y si quieres que procedas a guardarlos. "
             "SÓLO si el usuario te responde afirmativamente (ej. 'sí', 'procede'), "
             "entonces DEBES invocar la herramienta correspondiente según el tipo de documento: "
             "- Para activos de inventario: usa 'save_asset_to_db'. "
             "- Para CFDIs (facturas fiscales del SAT con UUID): usa 'save_cfdi_to_db'. Los montos siempre en pesos mexicanos (MXN). "
             "- Para identificaciones (INE, Pasaporte, Cédula): usa 'save_identificacion_to_db'. "
             "- Para actas constitutivas o escrituras notariales de empresa: usa 'save_acta_constitutiva_to_db'. "
             "Invoca la herramienta secuencialmente MÚLTIPLES VECES si hay varios registros. "
             "Solo pregunta por datos faltantes si al registro específico le falta su campo requerido (clave_vieja, uuid, nombre o razon_social). "
             "Si no sabes la respuesta o no está en el documento, dílo claramente. "
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
            model="gemini-3.1-flash-lite",
            google_api_key=settings.gemini_api_key,
            temperature=0.1,
            max_retries=4,
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
        y los inyecta en la base de datos vectorial Qdrant (limpiando vectores previos).
        """
        vector_store = get_vector_store()
        
        # Eliminar vectores viejos para evitar duplicación/basura si se resube el archivo
        from app.services.vector_db_service import get_qdrant_client
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from app.core.config import settings
        
        client = get_qdrant_client()
        try:
            client.delete(
                collection_name=settings.qdrant_collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.document_id",
                            match=MatchValue(value=document_id)
                        )
                    ]
                )
            )
            logger.info(f"Vectores previos eliminados para el documento {document_id}")
        except Exception as e:
            logger.warning(f"Ignorando limpieza previa de vectores para {document_id} (puede no existir aún): {e}")

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
            max_retries=4,
        )
        
        structured_llm = llm.with_structured_output(DocumentExtraction)
        
        prompt = (
            "Analiza el siguiente documento y extrae los datos solicitados en formato de tabla (lista de objetos). "
            "Clasifícalo correctamente en 'Activo', 'Comprobante de Domicilio', 'Resguardo', 'Personal', 'CFDI', 'Identificación Oficial', 'Acta Constitutiva' u 'Otro'.\n"
            "REGLAS ESTRICTAS DE CLASIFICACIÓN:\n"
            "1. 'Identificación Oficial': Úsalo INVARIABLEMENTE si el documento menciona 'Instituto Nacional Electoral', 'IFE', 'INE', 'Credencial para Votar', 'Pasaporte', 'Secretaría de Relaciones Exteriores' o similares. ¡NUNCA clasifiques una identificación o pasaporte como 'Activo'!\n"
            "2. 'Activo': Úsalo SOLO si el documento es un listado de bienes, equipo, mobiliario, vehículos o catálogo de inventario.\n"
            "Presta especial atención a la sección de 'EXPERIENCIAS PREVIAS' si existe, para ver cómo el usuario corrigió extracciones anteriores y NO cometer los mismos errores.\n"
            "Para campos alfanuméricos como CURP, Clave de Elector y OCR: transcribe carácter por carácter con "
            "mucho cuidado, sin adivinar. No confundas el dígito '0' con la letra 'O', ni la letra 'I' con el "
            "dígito '1'. Usa el contexto del formato oficial de cada campo (ej. el CURP siempre tiene dígitos en "
            "las posiciones 5-10 y letras en las posiciones 1-4) para decidir cuál es el carácter correcto.\n\n"
            f"{few_shot_prompt}\n"
            f"Documento a analizar:\n{context}"
        )

        try:
            extraction = structured_llm.invoke(prompt)
            if not extraction:
                return None

            for ident in extraction.identificaciones or []:
                ident.curp = _correct_curp_ocr_confusion(ident.curp)

            return extraction.model_dump()
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
