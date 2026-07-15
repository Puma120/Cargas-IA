import { useState, useRef, useEffect } from 'react';
import { uploadExcel, getCollections, saveExcelData, startRagProcessing, getStatus, saveAndLearn } from './api';
import { Upload, FileText, Brain, Database, Save, CheckCircle, XCircle } from 'lucide-react';

function App() {
  const [file, setFile] = useState(null);
  
  // Helper para extraer campos dinámicamente
  const getAllFields = (records) => {
    const fields = new Set();
    records.forEach(r => {
      Object.keys(r.data).forEach(k => fields.add(k));
      if (r.data.extra_data) {
        Object.keys(r.data.extra_data).forEach(k => fields.add(`extra_data.${k}`));
      }
    });
    return Array.from(fields);
  };

  const getNestedValue = (obj, path) => {
    return path.split('.').reduce((prev, curr) => (prev ? prev[curr] : null), obj);
  };

  const setNestedValue = (obj, path, value) => {
    const keys = path.split('.');
    const lastKey = keys.pop();
    const lastObj = keys.reduce((prev, curr) => prev[curr], obj);
    lastObj[lastKey] = value;
  };

  const [isDragging, setIsDragging] = useState(false);

  const [uploading, setUploading] = useState(false);

  const [status, setStatus] = useState('IDLE'); // IDLE, PROCESSING_OCR, PROCESSING_VECTOR, PROCESSING_LLM, COMPLETED, ERROR
  const [errorMsg, setErrorMsg] = useState('');
  const [extractedData, setExtractedData] = useState(null);

  const [availableCollections, setAvailableCollections] = useState([]);
  const [selectedCollections, setSelectedCollections] = useState({}); // sheetName -> collectionName

  const [documentInfo, setDocumentInfo] = useState(null);
  const intervalRef = useRef(null);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleUploadAndProcess = async () => {
    if (!file) return;
    setUploading(true);
    setStatus('PROCESSING_OCR');
    setErrorMsg('');
    setExtractedData(null);

    try {
      if (file.name.endsWith('.xlsx') || file.name.endsWith('.xls')) {
        const uploadRes = await uploadExcel(file);
        
        // Cargar colecciones disponibles
        const colls = await getCollections();
        setAvailableCollections(colls);
        
        // Set defaults
        const initialSelections = {};
        uploadRes.forEach(s => {
            const detected = s.data.records[0]?.collection || 'generic_migration';
            initialSelections[s.sheet] = detected;
        });
        setSelectedCollections(initialSelections);
        
        setExtractedData({ excelData: uploadRes });
        setStatus('COMPLETED');
        setUploading(false);
        return;
      }

      // 1. Upload PDF
      const uploadRes = await uploadPdf(file);
      // ... rest of logic for pdf ...
      // 3. Poll Status
      intervalRef.current = setInterval(async () => {
        try {
          const res = await getStatus(uploadRes.entity_type, uploadRes.document_id);
          
          if (res.status === 'COMPLETED') {
            setStatus('COMPLETED');
            setExtractedData(res.extracted_data);
            clearInterval(intervalRef.current);
          } else if (res.status === 'ERROR') {
            setStatus('ERROR');
            setErrorMsg(res.error_message || 'Error desconocido');
            clearInterval(intervalRef.current);
          } else {
            setStatus(res.status);
          }
        } catch (pollErr) {
          console.error("Error polling", pollErr);
        }
      }, 1500);

    } catch (err) {
      console.error(err);
      setStatus('ERROR');
      setErrorMsg(err.response?.data?.detail || err.message || "Fallo en la subida");
    } finally {
      setUploading(false);
    }
  };

  const handleSaveAndLearn = async () => {
    if (!extractedData || !documentInfo) return;
    try {
      
      const isComprobante = extractedData.comprobantes && extractedData.comprobantes.length > 0;
      const dataToSave = isComprobante ? extractedData.comprobantes : extractedData.activos;
      const dataType = isComprobante ? 'comprobantes' : 'activos';

      await saveAndLearn(
        `${documentInfo.entity_type}_${documentInfo.document_id}`,
        extractedData,
        dataToSave,
        null,
        dataType
      );
      alert("¡Conocimiento guardado en la Base Vectorial exitosamente!");
      setStatus('IDLE');
      setExtractedData(null);
      setFile(null);
    } catch (err) {
      console.error(err);
      alert("Error al guardar: " + err.message);
    }
  };

  const handleCellChange = (e, idx, field, type = 'activos') => {
    const newData = [...extractedData[type]];
    newData[idx] = { ...newData[idx], [field]: e.target.value };
    setExtractedData({ ...extractedData, [type]: newData });
  };

  return (
    <div className="container">
      <div className="header">
        <h1>SGA IA Agente</h1>
        <p>Motor Autónomo de Extracción RAG</p>
      </div>

      <div className="glass-panel">
        {!extractedData && status === 'IDLE' && (
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
              style={{display: 'none'}}
              accept=".pdf, .xlsx, .xls"
              onChange={handleFileChange}
            />
            <div className="dropzone-icon">
              <Upload size={48} />
            </div>
            {file ? (
              <h3>{file.name}</h3>
            ) : (
              <>
                <h3>Arrastra y suelta tu PDF aquí</h3>
                <p style={{color: 'var(--text-secondary)', marginTop: '0.5rem'}}>o haz clic para explorar</p>
              </>
            )}
            
            {file && (
              <button 
                className="btn btn-block" 
                style={{marginTop: '2rem'}}
                onClick={(e) => { e.stopPropagation(); handleUploadAndProcess(); }}
                disabled={uploading}
              >
                Comenzar Análisis IA
              </button>
            )}
          </div>
        )}

        {status !== 'IDLE' && (
          <div className="progress-container">
            <h3 style={{marginBottom: '2rem', textAlign: 'center'}}>
              {status === 'ERROR' ? 'Análisis Fallido' : 'Procesando Documento...'}
            </h3>
            
            <div className="progress-steps">
              <div className={`step ${status === 'PROCESSING_OCR' ? 'active' : ''} ${['PROCESSING_VECTOR', 'PROCESSING_LLM', 'COMPLETED'].includes(status) ? 'completed' : ''}`}>
                <div className="step-icon">
                  {status === 'PROCESSING_OCR' ? <FileText className="animate-pulse" /> : <FileText />}
                </div>
                <span>1. Extracción OCR</span>
              </div>
              
              <div className={`step ${status === 'PROCESSING_VECTOR' ? 'active' : ''} ${['PROCESSING_LLM', 'COMPLETED'].includes(status) ? 'completed' : ''}`}>
                <div className="step-icon">
                  {status === 'PROCESSING_VECTOR' ? <Database className="animate-pulse" /> : <Database />}
                </div>
                <span>2. Vectorización</span>
              </div>
              
              <div className={`step ${status === 'PROCESSING_LLM' ? 'active' : ''} ${status === 'COMPLETED' ? 'completed' : ''}`}>
                <div className="step-icon">
                  {status === 'PROCESSING_LLM' ? <Brain className="animate-pulse" /> : <Brain />}
                </div>
                <span>3. Inferencia LLM</span>
              </div>
            </div>

            {status === 'ERROR' && (
              <div style={{background: 'rgba(239, 68, 68, 0.1)', border: '1px solid var(--error)', padding: '1rem', borderRadius: '0.5rem', marginTop: '2rem', color: 'var(--error)'}}>
                <div style={{display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem'}}>
                  <XCircle size={20} />
                  <strong>Error de Procesamiento</strong>
                </div>
                <p>{errorMsg}</p>
                <button className="btn btn-secondary" style={{marginTop: '1rem'}} onClick={() => {setStatus('IDLE'); setFile(null);}}>Reintentar</button>
              </div>
            )}
          </div>
        )}

        {extractedData && (
          <div style={{marginTop: '2rem'}}>
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem'}}>
              <h2>Datos Extraídos</h2>
              {/* Solo mostrar botón si hay comprobantes procesados vía RAG */}
              {extractedData.comprobantes && (
                <button className="btn" onClick={handleSaveAndLearn}>
                  <Save size={20} /> Guardar Experiencia
                </button>
              )}
            </div>

            {extractedData.excelData ? (
              extractedData.excelData.map((sheetResult, sheetIdx) => (
                <div key={sheetIdx} className="result-card" style={{marginBottom: '2rem'}}>
                  <h3>Hoja: {sheetResult.sheet}</h3>
                  <p style={{color: 'var(--text-secondary)'}}>
                    Colección destino detectada: <strong>{sheetResult.data.records[0]?.collection || 'generic_migration'}</strong>
                  </p>
                  <p style={{color: 'var(--text-secondary)'}}>
                    Seleccionar destino final: 
                    <select 
                      value={selectedCollections[sheetResult.sheet]}
                      onChange={(e) => setSelectedCollections({...selectedCollections, [sheetResult.sheet]: e.target.value})}
                      style={{marginLeft: '0.5rem', background: '#222', color: 'white', padding: '0.2rem', borderRadius: '4px'}}
                    >
                      {availableCollections.map(c => <option key={c} value={c}>{c}</option>)}
                      <option value="nueva_coleccion">+ Crear nueva colección</option>
                    </select>
                  </p>
                  
                  <div className="table-container" style={{overflowX: 'auto', marginTop: '1rem'}}>
                    <table style={{width: '100%', borderCollapse: 'collapse'}}>
                      <thead>
                        <tr style={{background: 'rgba(255,255,255,0.05)'}}>
                          {sheetResult.data.records && sheetResult.data.records.length > 0 && 
                            getAllFields(sheetResult.data.records).map(field => (
                              <th key={field} style={{padding: '0.5rem', textAlign: 'left', borderBottom: '1px solid #444', textTransform: 'capitalize'}}>{field.replace(/\./g, ' ')}</th>
                            ))
                          }
                        </tr>
                      </thead>
                      <tbody>
                        {sheetResult.data.records && sheetResult.data.records.map((record, recIdx) => (
                          <tr key={recIdx}>
                            {getAllFields(sheetResult.data.records).map((field, cellIdx) => (
                              <td key={cellIdx} style={{padding: '0.5rem', borderBottom: '1px solid #333'}}>
                                <input 
                                  value={getNestedValue(record.data, field) || ''}
                                  onChange={(e) => {
                                    const newData = {...extractedData};
                                    setNestedValue(newData.excelData[sheetIdx].data.records[recIdx].data, field, e.target.value);
                                    setExtractedData(newData);
                                  }}
                                  style={{background: 'transparent', border: '1px solid #555', color: 'white', padding: '0.2rem', width: '100%'}}
                                />
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    <button className="btn" style={{marginTop: '1rem'}} onClick={async () => {
                      await saveExcelData(sheetResult.sheet, selectedCollections[sheetResult.sheet], sheetResult.data);
                      alert("Datos guardados en " + selectedCollections[sheetResult.sheet]);
                    }}>Guardar Hoja</button>
                  </div>
                </div>
              ))
            ) : extractedData.comprobantes?.length > 0 ? (
              extractedData.comprobantes.map((comp, idx) => (
                <div key={idx} className="result-card" style={{marginBottom: '1rem'}}>
                  <div className="result-row">
                    <span className="result-label">Tipo Servicio</span>
                    <span className="result-value">
                      <input value={comp.tipo_servicio || ''} onChange={(e) => handleCellChange(e, idx, 'tipo_servicio', 'comprobantes')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Nombre</span>
                    <span className="result-value">
                      <input value={comp.nombre || ''} onChange={(e) => handleCellChange(e, idx, 'nombre', 'comprobantes')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Domicilio</span>
                    <span className="result-value">
                      <input value={comp.domicilio || ''} onChange={(e) => handleCellChange(e, idx, 'domicilio', 'comprobantes')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Periodo</span>
                    <span className="result-value">
                      <input value={comp.periodo_facturacion || ''} onChange={(e) => handleCellChange(e, idx, 'periodo_facturacion', 'comprobantes')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Monto</span>
                    <span className="result-value">
                      <input value={comp.monto_a_pagar || ''} type="number" onChange={(e) => handleCellChange(e, idx, 'monto_a_pagar', 'comprobantes')} />
                    </span>
                  </div>
                </div>
              ))
            ) : (
              extractedData.activos?.map((activo, idx) => (
                <div key={idx} className="result-card" style={{marginBottom: '1rem'}}>
                  <div className="result-row">
                    <span className="result-label">Clave</span>
                    <span className="result-value">
                      <input value={activo.clave_vieja || ''} onChange={(e) => handleCellChange(e, idx, 'clave_vieja', 'activos')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Descripción</span>
                    <span className="result-value">
                      <input value={activo.nombre_activo || ''} onChange={(e) => handleCellChange(e, idx, 'nombre_activo', 'activos')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">No. Serie</span>
                    <span className="result-value">
                      <input value={activo.numero_serie || ''} onChange={(e) => handleCellChange(e, idx, 'numero_serie', 'activos')} />
                    </span>
                  </div>
                  <div className="result-row">
                    <span className="result-label">Custodio</span>
                    <span className="result-value">
                      <input value={activo.custodio || ''} onChange={(e) => handleCellChange(e, idx, 'custodio', 'activos')} />
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
