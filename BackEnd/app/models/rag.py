from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
import sqlalchemy.orm

from app.core.database import Base


class AiDocument(Base):
    """
    Modelo para llevar el control de los documentos que han sido 
    procesados por la IA (Extracción de texto y Embeddings en Qdrant).
    """
    __tablename__ = "AiDocument"

    DocumentId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Entidad a la que pertenece el documento (ej. 'Resguardo', 'Factura')
    EntityType: Mapped[str] = mapped_column(String(50), nullable=False) 
    
    # ID de la entidad en su tabla respectiva
    EntityId: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Ruta o URL donde se encuentra físicamente el PDF
    FileUrl: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Estado del procesamiento: PENDING, PROCESSING, COMPLETED, ERROR
    Status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING") 
    
    # Mensaje de error si algo falló durante el OCR o Vectorización
    ErrorMessage: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Datos extraídos estructurados (JSON/string) por la IA para auto-guardado
    ExtractedData: Mapped[str | None] = mapped_column(String, nullable=True)
    
    CreatedAt: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    ProcessedAt: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relación a los activos extraídos (1 a Muchos)
    # Se debe definir como string para evitar dependencias circulares antes de definir la clase
    ActivosExtraidos = sqlalchemy.orm.relationship("Activos_BD", back_populates="DocumentoOrigen", cascade="all, delete-orphan")
    
    # Relación a los comprobantes de domicilio extraídos
    ComprobantesExtraidos = sqlalchemy.orm.relationship("Comprobantes_BD", back_populates="DocumentoOrigen", cascade="all, delete-orphan")




class Activos_BD(Base):
    """
    Modelo que almacena cada activo extraído individualmente de los PDFs.
    Permite validar redundancias contra registros existentes.
    """
    __tablename__ = "Activos_BD"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AiDocumentId: Mapped[int] = mapped_column(Integer, ForeignKey("AiDocument.DocumentId"), nullable=False)
    
    # Columnas mapeadas exactamente al Excel Prueba_Activos_Completa.xlsx
    CodigoUniversal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    NumeroProgresivo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ClaveVieja: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Código de Identificación
    NumeroDependencia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    UnidadResponsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    SubUnidadResponsable: Mapped[str | None] = mapped_column(String(200), nullable=True)
    NombreActivo: Mapped[str | None] = mapped_column(String(500), nullable=True)  # Descripción del bien
    Marca: Mapped[str | None] = mapped_column(String(100), nullable=True)
    Color: Mapped[str | None] = mapped_column(String(100), nullable=True)
    Material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    NumeroSerie: Mapped[str | None] = mapped_column(String(100), nullable=True)
    EstadoFisico: Mapped[str | None] = mapped_column(String(50), nullable=True)
    Categorizacion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    NumeroFactura: Mapped[str | None] = mapped_column(String(100), nullable=True)
    NombreDonante: Mapped[str | None] = mapped_column(String(200), nullable=True)
    CostoIva: Mapped[float | None] = mapped_column(Float, nullable=True)
    NumeroActaContrato: Mapped[str | None] = mapped_column(String(100), nullable=True)
    Custodio: Mapped[str | None] = mapped_column(String(200), nullable=True)
    
    # Bandera para identificar si este registro se detectó como duplicado de otro
    IsDuplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Relación inversa
    DocumentoOrigen = sqlalchemy.orm.relationship("AiDocument", back_populates="ActivosExtraidos")


class Comprobantes_BD(Base):
    """
    Modelo que almacena cada comprobante de domicilio extraído individualmente.
    Permite validar redundancias contra registros existentes.
    """
    __tablename__ = "Comprobantes_BD"

    Id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    AiDocumentId: Mapped[int] = mapped_column(Integer, ForeignKey("AiDocument.DocumentId"), nullable=False)
    
    TipoServicio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    PeriodoFacturacion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    MontoAPagar: Mapped[float | None] = mapped_column(Float, nullable=True)
    FechaExpedicion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    FechaPago: Mapped[str | None] = mapped_column(String(100), nullable=True)
    Nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    Domicilio: Mapped[str | None] = mapped_column(String(500), nullable=True)
    Folio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    # Bandera para identificar si este registro se detectó como duplicado de otro
    IsDuplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # Relación inversa
    DocumentoOrigen = sqlalchemy.orm.relationship("AiDocument", back_populates="ComprobantesExtraidos")
