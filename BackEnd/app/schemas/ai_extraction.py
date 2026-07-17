from typing import Literal, Optional, List
from pydantic import BaseModel, Field

class ActivoExtraido(BaseModel):
    clave_vieja: Optional[str] = Field(None, description="Código de identificación, Asset Code, número de inventario o clave vieja.")
    nombre_activo: Optional[str] = Field(None, description="Descripción del bien, modelo o nombre comercial.")
    numero_serie: Optional[str] = Field(None, description="Número de serie del equipo.")
    marca: Optional[str] = Field(None, description="Marca comercial del equipo o bien.")
    color: Optional[str] = Field(None, description="Color del equipo.")
    estado_fisico: Optional[str] = Field(None, description="Estado físico (Bueno, Malo, Regular).")
    categoria: Optional[str] = Field(None, description="Categoría (Equipo de Cómputo, Mobiliario, etc).")
    material: Optional[str] = Field(None, description="Material del activo.")
    universal_code: Optional[str] = Field(None, description="Código Universal (si aplica).")
    progressive_number: Optional[str] = Field(None, description="Número progresivo (si aplica).")
    dependency_number: Optional[str] = Field(None, description="Número de dependencia.")
    responsible_unit: Optional[str] = Field(None, description="Unidad responsable.")
    responsible_sub_unit: Optional[str] = Field(None, description="Sub-unidad responsable.")
    donation_invoice: Optional[str] = Field(None, description="Número de factura o documento legal.")
    donor_name: Optional[str] = Field(None, description="Nombre del donante o proveedor.")
    donation_cost_iva: Optional[float] = Field(None, description="Costo incluyendo IVA.")
    contract_number: Optional[str] = Field(None, description="Número de acta o contrato.")
    custodio_original: Optional[str] = Field(None, description="Nombre o número de empleado del custodio.")

class ComprobanteDomicilioExtraido(BaseModel):
    tipo_servicio: Optional[str] = Field(None, description="Tipo de servicio (ej. Luz, Agua, Gas, Predial, Internet, etc.)")
    periodo_facturacion: Optional[str] = Field(None, description="Periodo de consumo, bimestre o meses facturados (ej. 29.04.2026 a 27.05.2026).")
    monto_a_pagar: Optional[float] = Field(None, description="Total a pagar o importe de la factura.")
    fecha_expedicion: Optional[str] = Field(None, description="Fecha de emisión o impresión del recibo.")
    fecha_pago: Optional[str] = Field(None, description="Fecha límite de pago o fecha en la que se pagó.")
    nombre: Optional[str] = Field(None, description="Nombre del titular o receptor del comprobante.")
    domicilio: Optional[str] = Field(None, description="Dirección o domicilio que ampara el comprobante.")
    folio: Optional[str] = Field(None, description="Folio, número de recibo, cuenta contrato o número de servicio.")

class CFDIExtraido(BaseModel):
    """Campos clave de un Comprobante Fiscal Digital por Internet (CFDI)."""
    uuid: Optional[str] = Field(None, description="UUID del timbre fiscal, formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.")
    rfc_emisor: Optional[str] = Field(None, description="RFC del emisor de la factura.")
    rfc_receptor: Optional[str] = Field(None, description="RFC del receptor o cliente de la factura.")
    fecha: Optional[str] = Field(None, description="Fecha y hora de emisión del CFDI (ej. 2026-01-15T12:00:00).")
    subtotal: Optional[float] = Field(None, description="Subtotal del CFDI en pesos mexicanos (MXN), sin IVA, sin símbolo de moneda.")
    iva: Optional[float] = Field(None, description="Monto del IVA en pesos mexicanos (MXN), sin símbolo de moneda.")
    total: Optional[float] = Field(None, description="Total del CFDI en pesos mexicanos (MXN), sin símbolo de moneda.")
    metodo_pago: Optional[str] = Field(None, description="Método de pago del SAT (ej. PUE, PPD).")
    forma_pago: Optional[str] = Field(None, description="Forma de pago del SAT (ej. 01 Efectivo, 03 Transferencia, 04 Tarjeta de crédito).")
    moneda: Optional[str] = Field(None, description="Clave de moneda del CFDI. Si está en pesos mexicanos será 'MXN'.")

class IdentificacionExtraida(BaseModel):
    """Campos de una Identificación Oficial (INE, Pasaporte, Cédula Profesional)."""
    tipo_identificacion: Optional[str] = Field(
        None, description="El tipo de identificación oficial (ej. INE, Pasaporte, Cédula Profesional)."
    )
    nombre: Optional[str] = Field(None, description="Nombre completo del titular tal como aparece en el documento.")
    curp: Optional[str] = Field(
        None,
        description=(
            "CURP del titular, exactamente 18 caracteres con este patrón posicional estricto: "
            "posiciones 1-4 SIEMPRE letras, posiciones 5-10 SIEMPRE dígitos (fecha de nacimiento AAMMDD), "
            "posición 11 SIEMPRE letra (H o M), posiciones 12-13 SIEMPRE letras (estado), "
            "posiciones 14-16 SIEMPRE letras, posición 17 alfanumérico, posición 18 SIEMPRE dígito. "
            "CUIDADO: no confundas el dígito '0' (cero) con la letra 'O', ni la letra 'I' con el dígito '1'; "
            "usa el patrón posicional de arriba para decidir cuál es correcto en cada caso."
        )
    )
    clave_elector: Optional[str] = Field(
        None,
        description=(
            "Clave de elector del INE (18 caracteres, solo aplica para INE), etiquetada en la credencial como "
            "'CLAVE DE ELECTOR'. Primeros 6 caracteres son letras, el resto son dígitos. "
            "CUIDADO: no confundas el dígito '0' con la letra 'O' — revisa el trazo del carácter con cuidado."
        )
    )
    numero_identificacion: Optional[str] = Field(None, description="Número principal: Número de Pasaporte o Número de Cédula (si no es INE).")
    ocr: Optional[str] = Field(None, description="Número OCR (solo aplica para INE), son puros dígitos.")
    vigencia: Optional[str] = Field(
        None,
        description=(
            "Rango de vigencia de la credencial tal como aparece impreso (ej. '2021-2031' o '2021 - 2027'), "
            "etiquetado como 'VIGENCIA' en el documento. No lo confundas con 'AÑO DE REGISTRO' ni con la 'SECCIÓN'."
        )
    )
    domicilio: Optional[str] = Field(None, description="Domicilio completo (solo si aparece en el documento).")
    sexo: Optional[str] = Field(None, description="Sexo del titular tal como aparece en el documento (ej. H, M, F).")
    seccion: Optional[str] = Field(None, description="Número de sección electoral (solo aplica para INE), etiquetado como 'SECCIÓN'.")
    fecha_nacimiento: Optional[str] = Field(None, description="Fecha de nacimiento del titular tal como aparece impresa (ej. '28/09/2003').")

class ActaConstitutivaExtraida(BaseModel):
    """Campos de un Acta Constitutiva o escritura pública de constitución de empresa."""
    razon_social: Optional[str] = Field(None, description="Nombre o razón social de la empresa constituida.")
    rfc: Optional[str] = Field(None, description="RFC de la empresa (si aparece en el documento).")
    fecha_constitucion: Optional[str] = Field(None, description="Fecha de constitución o firma de la escritura.")
    objeto_social: Optional[str] = Field(None, description="Objeto social o actividades de la empresa según el acta.")
    representante_legal: Optional[str] = Field(None, description="Nombre del representante legal o apoderado.")
    notaria: Optional[str] = Field(None, description="Nombre o número de la notaría pública donde se protocolizó.")
    ciudad: Optional[str] = Field(None, description="Ciudad o municipio donde se firmó el acta.")
    notario: Optional[str] = Field(None, description="Nombre del notario público que certificó la escritura.")
    numero_escritura: Optional[str] = Field(None, description="Número de escritura o instrumento notarial.")

class DocumentExtraction(BaseModel):
    """
    Esquema principal para la extracción estructurada de datos a partir de documentos OCR.
    Permite extraer tablas enteras como listas de registros.
    """
    entity_type: str = Field(
        description=(
            "Clasificación del documento. "
            "Si es recibo de luz/agua/predial usa 'Comprobante de Domicilio'. "
            "Si es una factura fiscal con UUID del SAT, usa 'CFDI'. "
            "Si es credencial para votar (IFE/INE), Pasaporte o Cédula Profesional, usa 'Identificación Oficial'. "
            "Si es escritura pública de constitución de empresa, usa 'Acta Constitutiva'."
        )
    )
    
    activos: Optional[List[ActivoExtraido]] = Field(
        default=[], description="Lista de activos extraídos del documento (útil para tablas o listas de inventario)."
    )

    comprobantes: Optional[List[ComprobanteDomicilioExtraido]] = Field(
        default=[], description="Datos extraídos si el documento es un comprobante de domicilio."
    )

    cfdis: Optional[List[CFDIExtraido]] = Field(
        default=[], description="Datos extraídos si el documento es un CFDI (factura fiscal del SAT)."
    )

    identificaciones: Optional[List[IdentificacionExtraida]] = Field(
        default=[], description="Datos extraídos si el documento es una Identificación Oficial (INE, Pasaporte, Cédula)."
    )

    actas_constitutivas: Optional[List[ActaConstitutivaExtraida]] = Field(
        default=[], description="Datos extraídos si el documento es un acta constitutiva o escritura notarial de empresa."
    )
    
    reasoning: str = Field(description="Breve explicación de por qué clasificaste el documento así y de dónde sacaste los datos.")
