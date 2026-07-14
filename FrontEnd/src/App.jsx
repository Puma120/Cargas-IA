import { useState, useRef, useEffect } from 'react';
import { Upload, FileText, Brain, Save, CheckCircle, XCircle, ChevronDown, ChevronUp, Trash2 } from 'lucide-react';
import { uploadPdf, startRagProcessing, getStatus, saveAndLearn } from './api';

// Cuántos documentos se procesan (OCR + LLM) al mismo tiempo. Gemini free-tier
// tiene límites de pocos requests/minuto, así que un número bajo evita 429s
// cuando se sube un lote grande de archivos.
const MAX_CONCURRENT = 2;

const ACTIVE_PHASES = ['UPLOADING', 'PROCESSING_OCR', 'PROCESSING_VECTOR', 'PROCESSING_LLM'];
const POLLABLE_PHASES = ['PROCESSING_OCR', 'PROCESSING_VECTOR', 'PROCESSING_LLM'];

const PHASE_PROGRESS = {
  QUEUED: 0,
  UPLOADING: 10,
  PROCESSING_OCR: 35,
  PROCESSING_VECTOR: 60,
  PROCESSING_LLM: 85,
  COMPLETED: 100,
  ERROR: 100,
};

const PHASE_LABELS = {
  QUEUED: 'En cola',
  UPLOADING: 'Subiendo...',
  PROCESSING_OCR: '1/3 Extracción OCR',
  PROCESSING_VECTOR: '2/3 Vectorización',
  PROCESSING_LLM: '3/3 Inferencia LLM',
  COMPLETED: 'Completado',
  ERROR: 'Error',
};

const DOCUMENT_TYPE_TO_DATA_TYPE = {
  'Comprobante de Domicilio': 'comprobantes',
  'CFDI': 'cfdis',
  'Identificación Oficial': 'identificaciones',
  'Acta Constitutiva': 'actas_constitutivas',
  'Activo': 'activos',
};

const DATA_TYPES = ['comprobantes', 'cfdis', 'identificaciones', 'actas_constitutivas', 'activos'];

const DATA_TYPE_TITLES = {
  comprobantes: '(Comprobantes)',
  cfdis: '(CFDIs)',
  identificaciones: '(Identificaciones Oficiales)',
  actas_constitutivas: '(Actas Constitutivas)',
  activos: '(Activos)',
};

const DATA_TYPE_FIELDS = {
  comprobantes: [
    { key: 'tipo_servicio', label: 'Tipo Servicio' },
    { key: 'nombre', label: 'Nombre' },
    { key: 'domicilio', label: 'Domicilio' },
    { key: 'periodo_facturacion', label: 'Periodo' },
    { key: 'monto_a_pagar', label: 'Monto', type: 'number' },
  ],
  cfdis: [
    { key: 'uuid', label: 'UUID' },
    { key: 'rfc_emisor', label: 'RFC Emisor' },
    { key: 'fecha', label: 'Fecha' },
    { key: 'total', label: 'Total MXN', type: 'number' },
  ],
  identificaciones: [
    { key: 'tipo_identificacion', label: 'Tipo ID' },
    { key: 'nombre', label: 'Nombre' },
    { key: 'curp', label: 'CURP' },
    { key: 'clave_elector', label: 'Clave Elector' },
    { key: 'domicilio', label: 'Domicilio' },
    { key: 'sexo', label: 'Sexo' },
    { key: 'seccion', label: 'Sección' },
    { key: 'fecha_nacimiento', label: 'Fecha de Nacimiento' },
    { key: 'ocr', label: 'OCR' },
    { key: 'vigencia', label: 'Vigencia' },
  ],
  actas_constitutivas: [
    { key: 'razon_social', label: 'Razón Social' },
    { key: 'rfc', label: 'RFC' },
    { key: 'fecha_constitucion', label: 'Fecha' },
    { key: 'objeto_social', label: 'Objeto Social' },
    { key: 'representante_legal', label: 'Representante' },
    { key: 'notaria', label: 'Notaría' },
    { key: 'ciudad', label: 'Ciudad' },
    { key: 'notario', label: 'Notario' },
    { key: 'numero_escritura', label: 'No. Escritura' },
  ],
  activos: [
    { key: 'clave_vieja', label: 'Clave' },
    { key: 'nombre_activo', label: 'Descripción' },
    { key: 'numero_serie', label: 'No. Serie' },
    { key: 'custodio', label: 'Custodio' },
  ],
};

let nextItemId = 1;

function App() {
  const [queue, setQueue] = useState([]);
  const [isDragging, setIsDragging] = useState(false);

  const queueRef = useRef(queue);
  const startedIdsRef = useRef(new Set());

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);

  const updateItem = (id, patch) => {
    setQueue(q => q.map(it => it.id === id ? { ...it, ...(typeof patch === 'function' ? patch(it) : patch) } : it));
  };

  const addFiles = (fileList) => {
    const pdfFiles = Array.from(fileList).filter(f => f.name.toLowerCase().endsWith('.pdf'));
    if (pdfFiles.length === 0) return;

    const newItems = pdfFiles.map(file => ({
      id: nextItemId++,
      file,
      name: file.name,
      phase: 'QUEUED',
      documentInfo: null,
      extractedData: null,
      errorMsg: '',
      duplicateWarning: false,
      expanded: false,
    }));
    setQueue(q => [...q, ...newItems]);
  };

  const handleDragOver = (e) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = () => setIsDragging(false);
  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files?.length > 0) addFiles(e.dataTransfer.files);
  };
  const handleFileChange = (e) => {
    if (e.target.files?.length > 0) addFiles(e.target.files);
    e.target.value = '';
  };

  const startProcessingItem = async (item) => {
    updateItem(item.id, { phase: 'UPLOADING' });
    try {
      const uploadRes = await uploadPdf(item.file);
      updateItem(item.id, {
        documentInfo: uploadRes,
        phase: 'PROCESSING_OCR',
        duplicateWarning: !!uploadRes.duplicate,
      });
      await startRagProcessing(uploadRes.document_id, uploadRes.entity_type, uploadRes.file_path);
    } catch (err) {
      updateItem(item.id, {
        phase: 'ERROR',
        errorMsg: err.response?.data?.detail || err.message || 'Fallo en la subida',
      });
    }
  };

  // Bucle maestro: cada 1.5s arranca items en cola si hay cupo de concurrencia
  // libre, y sondea el estado de los que ya están procesándose.
  useEffect(() => {
    const interval = setInterval(async () => {
      const current = queueRef.current;

      const activeCount = current.filter(it => ACTIVE_PHASES.includes(it.phase)).length;
      const freeSlots = MAX_CONCURRENT - activeCount;
      if (freeSlots > 0) {
        const toStart = current
          .filter(it => it.phase === 'QUEUED' && !startedIdsRef.current.has(it.id))
          .slice(0, freeSlots);
        toStart.forEach(it => {
          startedIdsRef.current.add(it.id);
          startProcessingItem(it);
        });
      }

      const toPoll = current.filter(it => POLLABLE_PHASES.includes(it.phase) && it.documentInfo);
      await Promise.all(toPoll.map(async (it) => {
        try {
          const res = await getStatus(it.documentInfo.entity_type, it.documentInfo.document_id);
          if (res.status === 'COMPLETED') {
            updateItem(it.id, { phase: 'COMPLETED', extractedData: res.extracted_data, expanded: true });
          } else if (res.status === 'ERROR') {
            updateItem(it.id, { phase: 'ERROR', errorMsg: res.error_message || 'Error desconocido' });
          } else if (res.status !== it.phase) {
            updateItem(it.id, { phase: res.status });
          }
        } catch (pollErr) {
          console.error('Error polling', pollErr);
        }
      }));
    }, 1500);

    return () => clearInterval(interval);
  }, []);

  const getDataType = (item) => {
    const mapped = DOCUMENT_TYPE_TO_DATA_TYPE[item.extractedData?.document_type];
    if (mapped) return mapped;

    const d = item.extractedData;
    if (d.comprobantes?.length > 0) return 'comprobantes';
    if (d.cfdis?.length > 0) return 'cfdis';
    if (d.identificaciones?.length > 0) return 'identificaciones';
    if (d.actas_constitutivas?.length > 0) return 'actas_constitutivas';
    return 'activos';
  };

  const handleCellChange = (itemId, idx, field, type, value) => {
    setQueue(q => q.map(it => {
      if (it.id !== itemId) return it;
      const newData = [...it.extractedData[type]];
      newData[idx] = { ...newData[idx], [field]: value };
      return { ...it, extractedData: { ...it.extractedData, [type]: newData } };
    }));
  };

  const handleSaveAndLearn = async (item) => {
    try {
      const dataType = getDataType(item);
      const dataToSave = item.extractedData[dataType] || [];
      await saveAndLearn(
        `${item.documentInfo.entity_type}_${item.documentInfo.document_id}`,
        item.extractedData,
        dataToSave,
        null,
        dataType
      );
      alert(`¡Conocimiento de "${item.name}" guardado en la Base Vectorial!`);
      removeItem(item.id);
    } catch (err) {
      console.error(err);
      alert('Error al guardar: ' + err.message);
    }
  };

  const retryItem = (item) => {
    startedIdsRef.current.delete(item.id);
    updateItem(item.id, { phase: 'QUEUED', errorMsg: '', documentInfo: null, extractedData: null });
  };

  const removeItem = (id) => {
    startedIdsRef.current.delete(id);
    setQueue(q => q.filter(it => it.id !== id));
  };

  const toggleExpanded = (id) => updateItem(id, (it) => ({ expanded: !it.expanded }));

  const queuedCount = queue.filter(it => it.phase === 'QUEUED').length;
  const activeCount = queue.filter(it => ACTIVE_PHASES.includes(it.phase)).length;
  const completedCount = queue.filter(it => it.phase === 'COMPLETED').length;
  const errorCount = queue.filter(it => it.phase === 'ERROR').length;

  return (
    <div className="container">
      <div className="header">
        <h1>SGA IA Agente</h1>
        <p>Motor Autónomo de Extracción RAG</p>
      </div>

      <div className="glass-panel">
        <div
          className={`dropzone ${isDragging ? 'active' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => document.getElementById('fileUpload').click()}
        >
          <input
            type="file"
            id="fileUpload"
            style={{ display: 'none' }}
            accept=".pdf"
            multiple
            onChange={handleFileChange}
          />
          <div className="dropzone-icon">
            <Upload size={48} />
          </div>
          <h3>Arrastra y suelta uno o varios PDFs aquí</h3>
          <p style={{ color: 'var(--text-secondary)', marginTop: '0.5rem' }}>
            o haz clic para explorar — se procesan hasta {MAX_CONCURRENT} a la vez
          </p>
        </div>
      </div>

      {queue.length > 0 && (
        <>
          <div className="queue-summary">
            {queuedCount > 0 && <span>{queuedCount} en cola</span>}
            {activeCount > 0 && <span className="active">{activeCount} procesando</span>}
            {completedCount > 0 && <span className="success">{completedCount} completado{completedCount !== 1 ? 's' : ''}</span>}
            {errorCount > 0 && <span className="error">{errorCount} con error</span>}
          </div>

          <div className="queue-list">
            {queue.map(item => (
              <div key={item.id} className="glass-panel queue-item">
                <div className="queue-item-header">
                  <div className="queue-item-title">
                    <FileText size={18} />
                    <span>{item.name}</span>
                    {item.duplicateWarning && <span className="badge-warning">duplicado</span>}
                  </div>
                  <div className="queue-item-actions">
                    {item.phase === 'COMPLETED' && (
                      <button className="btn-icon" onClick={() => toggleExpanded(item.id)} title="Ver datos extraídos">
                        {item.expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                      </button>
                    )}
                    {item.phase !== 'UPLOADING' && !POLLABLE_PHASES.includes(item.phase) && (
                      <button className="btn-icon" onClick={() => removeItem(item.id)} title="Quitar de la lista">
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                </div>

                <div className="progress-bar-track">
                  <div
                    className={`progress-bar-fill ${item.phase === 'ERROR' ? 'error' : ''} ${item.phase === 'COMPLETED' ? 'success' : ''}`}
                    style={{ width: `${PHASE_PROGRESS[item.phase]}%` }}
                  />
                </div>
                <div className="queue-item-status">
                  {item.phase === 'ERROR' ? <XCircle size={14} />
                    : item.phase === 'COMPLETED' ? <CheckCircle size={14} />
                    : <Brain size={14} className="animate-pulse" />}
                  <span>{PHASE_LABELS[item.phase]}</span>
                </div>

                {item.phase === 'ERROR' && (
                  <div className="error-box">
                    <p>{item.errorMsg}</p>
                    <button className="btn btn-secondary" onClick={() => retryItem(item)}>Reintentar</button>
                  </div>
                )}

                {item.phase === 'COMPLETED' && item.expanded && (
                  <div style={{ marginTop: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                      <h3>Datos Extraídos {DATA_TYPE_TITLES[getDataType(item)]}</h3>
                      <button className="btn" onClick={() => handleSaveAndLearn(item)}>
                        <Save size={18} /> Guardar Experiencia
                      </button>
                    </div>

                    {DATA_TYPES.map(type => (
                      item.extractedData[type]?.length > 0 && item.extractedData[type].map((entry, idx) => (
                        <div key={`${type}-${idx}`} className="result-card" style={{ marginBottom: '1rem' }}>
                          {DATA_TYPE_FIELDS[type].map(f => (
                            <div className="result-row" key={f.key}>
                              <span className="result-label">{f.label}</span>
                              <span className="result-value">
                                <input
                                  type={f.type || 'text'}
                                  value={entry[f.key] ?? ''}
                                  onChange={(e) => handleCellChange(item.id, idx, f.key, type, e.target.value)}
                                />
                              </span>
                            </div>
                          ))}
                        </div>
                      ))
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export default App;
