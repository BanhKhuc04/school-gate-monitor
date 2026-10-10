import client from '../api/client';

/** Adapter cho Task 3 training/dataset/jobs/candidates/export/import.
 *  Dùng chung axios client với Task 1/2 để không phải duplicate cookie/auth.
 */
const client_ = client;

export async function listDatasets(engine) {
  const { data } = await client_.get('/api/training/datasets', {
    params: engine ? { engine } : {},
  });
  return data.items || [];
}

export async function createDataset(payload) {
  const { data } = await client_.post('/api/training/datasets', payload);
  return data;
}

export async function freezeDataset(datasetId) {
  const { data } = await client_.post(`/api/training/datasets/${datasetId}/freeze`);
  return data;
}

export async function listSamples(datasetId, split) {
  const { data } = await client_.get(`/api/training/datasets/${datasetId}/samples`, {
    params: split ? { split } : {},
  });
  return data;
}

export async function addSamples(datasetId, samples) {
  const { data } = await client_.post(`/api/training/datasets/${datasetId}/samples`,
    { samples });
  return data;
}

export async function runSplit(datasetId, { seed = 42, ratios } = {}) {
  const { data } = await client_.post(`/api/training/datasets/${datasetId}/split`,
    { seed, ratios });
  return data;
}

export async function getLeakage(datasetId) {
  const { data } = await client_.get(`/api/training/datasets/${datasetId}/leakage`);
  return data;
}

export async function patchSampleBBox(datasetId, targetId, { bbox, expectedVersion, reason }) {
  const { data } = await client_.patch(
    `/api/training/datasets/${datasetId}/samples/${targetId}/bbox`,
    { bbox, expected_version: expectedVersion, reason: reason || 'manual_edit' },
  );
  return data;
}

export async function listJobs(state) {
  const { data } = await client_.get('/api/training/jobs', {
    params: state ? { state } : {},
  });
  return data.items || [];
}

export async function createJob(payload) {
  const { data } = await client_.post('/api/training/jobs', payload);
  return data;
}

export async function getJob(jobId) {
  const { data } = await client_.get(`/api/training/jobs/${jobId}`);
  return data;
}

export async function cancelJob(jobId) {
  const { data } = await client_.post(`/api/training/jobs/${jobId}/cancel`);
  return data;
}

export async function listCandidates(engine, state) {
  const { data } = await client_.get('/api/training/candidates', {
    params: {
      ...(engine ? { engine } : {}),
      ...(state ? { state } : {}),
    },
  });
  return data.items || [];
}

export async function getActiveCandidate(engine) {
  const { data } = await client_.get('/api/training/candidates/active', {
    params: { engine },
  });
  return data.active;
}

export async function promoteCandidate(candidateId, expectedMetrics) {
  const { data } = await client_.post(`/api/training/candidates/${candidateId}/promote`,
    { expected_metrics: expectedMetrics || null });
  return data;
}

export async function rollbackCandidate(engine) {
  const { data } = await client_.post('/api/training/candidates/rollback',
    null, { params: { engine } });
  return data;
}

export async function exportZip(datasetId) {
  const { data } = await client_.post('/api/training/export', { dataset_id: datasetId });
  return data;
}

export async function previewImport(file) {
  const fd = new FormData();
  fd.append('file', file);
  const { data } = await client_.post('/api/training/import/preview', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function applyImport(file, datasetName) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('dataset_name', datasetName);
  const { data } = await client_.post('/api/training/import/apply', fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}