import type {
  EvidenceSummary,
  HealthResponse,
  PipelineErrorResponse,
  QueryResponse,
  ReadyResponse,
  TextQueryRequest,
} from '../types/api';
import {
  parseEvidenceSummary,
  parseHealthResponse,
  parsePipelineError,
  parseQueryResponse,
  parseReadyResponse,
} from '../types/api';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
const WS_BASE = (import.meta.env.VITE_WS_BASE_URL || '/ws').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly response: PipelineErrorResponse | null;

  constructor(message: string, status: number, response: PipelineErrorResponse | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.response = response;
  }
}

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new ApiError(
      `Expected JSON but received ${contentType || 'an unknown content type'}`,
      response.status
    );
  }
  return await response.json();
}

export function getVoiceWebSocketUrl(): string {
  const path = `${WS_BASE}/v1/query/voice`;
  if (path.startsWith('ws://') || path.startsWith('wss://')) return path;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${protocol}//${window.location.host}${normalizedPath}`;
}

export async function getHealth(): Promise<HealthResponse> {
  try {
    const response = await fetch(`${API_BASE}/health`, {
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      return { status: 'unhealthy', version: null, error: `HTTP ${response.status}` };
    }
    return parseHealthResponse(await readJson(response));
  } catch (error) {
    return {
      status: 'offline',
      version: null,
      error: error instanceof Error ? error.message : 'Backend is unreachable',
    };
  }
}

export async function getReady(): Promise<ReadyResponse> {
  try {
    const response = await fetch(`${API_BASE}/ready`, {
      headers: { Accept: 'application/json' },
    });
    return parseReadyResponse(await readJson(response));
  } catch {
    return {
      status: 'not_ready',
      checks: { backend_process: { ready: false, reason: 'backend_unreachable' } },
      runtime: {
        process_instance_id: null,
        process_started_at: null,
        voice_requests_started: null,
        rag_deadline_ms: null,
        rag_fallback_at_ms: null,
      },
    };
  }
}

export async function sendTextQuery(payload: TextQueryRequest): Promise<QueryResponse> {
  const response = await fetch(`${API_BASE}/v1/query/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await readJson(response);
  if (!response.ok) {
    let structured: PipelineErrorResponse | null = null;
    try {
      structured = parsePipelineError(body);
    } catch {
      // Do not expose an unvalidated error payload.
    }
    throw new ApiError(
      structured?.message || `Query failed with HTTP ${response.status}`,
      response.status,
      structured
    );
  }
  return parseQueryResponse(body);
}

export async function getEvidenceSummary(): Promise<EvidenceSummary> {
  const response = await fetch(`${API_BASE}/v1/evidence/summary`, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new ApiError(`Evidence endpoint returned HTTP ${response.status}`, response.status);
  }
  return parseEvidenceSummary(await readJson(response));
}
