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

class DocumentExtraction(BaseModel):
    """
    Esquema principal para la extracción estructurada de datos a partir de documentos OCR.
    Permite extraer tablas enteras como listas de registros.
    """
    entity_type: Literal["Activo", "Comprobante de Domicilio", "Resguardo", "Personal", "Otro"] = Field(
        description="Clasificación del documento. Si es recibo de luz/agua/predial usa 'Comprobante de Domicilio'."
    )
    
    activos: Optional[List[ActivoExtraido]] = Field(
        default=[], description="Lista de activos extraídos del documento (útil para tablas o listas de inventario)."
    )

    comprobantes: Optional[List[ComprobanteDomicilioExtraido]] = Field(
        default=[], description="Datos extraídos si el documento es un comprobante de domicilio."
    )
    
    reasoning: str = Field(description="Breve explicación de por qué clasificaste el documento así y de dónde sacaste los datos.")

