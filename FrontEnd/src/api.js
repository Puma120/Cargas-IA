import axios from 'axios';

const api = axios.create({
  baseURL: 'http://localhost:8000',
});

export const uploadPdf = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/rag/upload', formData);
  return res.data;
};

export const startRagProcessing = async (documentId, entityType, filePath) => {
  const res = await api.post('/rag/process', {
    document_id: documentId,
    entity_type: entityType,
    file_path: filePath
  });
  return res.data;
};

export const getStatus = async (entityType, entityId) => {
  const res = await api.get(`/rag/status/${entityType}/${entityId}`);
  return res.data;
};

export const saveAndLearn = async (documentId, originalExtraction, correctedData, documentText, dataType = 'activos') => {
  const res = await api.post('/rag/save-and-learn', {
    document_id: documentId,
    original_extraction: originalExtraction,
    corrected_data: correctedData,
    document_text: documentText,
    data_type: dataType
  });
  return res.data;
};

export default api;
