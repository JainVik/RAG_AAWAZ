import type {
  HealthResponse,
  ReadyResponse,
  TextQueryRequest,
  QueryResponse,
  EvidenceSummary,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api';

/**
 * Fetch backend liveness and version info (GET /health)
 */
export async function getHealth(): Promise<HealthResponse> {
  try {
    const res = await fetch(`${API_BASE}/health`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      return {
        status: 'unhealthy',
        error: `HTTP ${res.status}: ${res.statusText}`,
      };
    }
    return await res.json();
  } catch (err) {
    return {
      status: 'offline',
      error: err instanceof Error ? err.message : 'Backend unreachable on port 8000',
    };
  }
}

/**
 * Fetch backend operational readiness (GET /ready)
 * Note: Proves backend can serve requests. Does not imply final benchmark qualification.
 */
export async function getReady(): Promise<ReadyResponse> {
  try {
    const res = await fetch(`${API_BASE}/ready`, {
      headers: { Accept: 'application/json' },
    });
    if (!res.ok) {
      if (res.status === 503) {
        const data = await res.json().catch(() => ({}));
        return {
          status: 'not_ready',
          checks: data.checks || {},
          runtime: data.runtime,
        };
      }
      throw new Error(`Ready check returned HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    return {
      status: 'not_ready',
      checks: {
        backend_process: {
          name: 'backend_process',
          ready: false,
          message: 'FastAPI backend is offline at 127.0.0.1:8000',
        },
      },
      error: err instanceof Error ? err.message : 'Connection refused at 127.0.0.1:8000',
    };
  }
}

/**
 * Send text test mode query (POST /v1/query/text)
 */
export async function sendTextQuery(payload: TextQueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/v1/query/text`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(
      errorData.detail ||
        errorData.message ||
        `Query failed with status ${res.status} (${res.statusText})`
    );
  }

  return await res.json();
}

/**
 * Fetch real sanitized evidence summary for the Evidence page (GET /v1/evidence/summary)
 */
export async function getEvidenceSummary(): Promise<EvidenceSummary> {
  const res = await fetch(`${API_BASE}/v1/evidence/summary`, {
    headers: { Accept: 'application/json' },
  });

  if (!res.ok) {
    throw new Error(`Evidence endpoint returned HTTP ${res.status} (${res.statusText})`);
  }

  return await res.json();
}
