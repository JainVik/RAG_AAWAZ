/**
 * ============================================================================
 * Ultra-Low-Latency GTAG Analytics Module
 * ============================================================================
 * Zero-overhead, fire-and-forget event tracking for VANI RAG.
 * Uses microtasks and safe ad-blocker fallbacks.
 */

declare global {
  interface Window {
    gtag?: (...args: unknown[]) => void;
    dataLayer?: unknown[];
  }
}

/**
 * Send an analytics event safely without blocking main thread execution
 */
function sendAnalyticsEvent(
  eventName: string,
  params: Record<string, string | number | boolean> = {}
) {
  if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;

  // Execute in microtask so it never delays audio capture, WebSocket frames, or UI rendering
  queueMicrotask(() => {
    try {
      window.gtag?.('event', eventName, params);
    } catch {
      // Fail silently
    }
  });
}

/**
 * 1. Track SPA page navigation (/ask, /evidence)
 */
export function trackPageView(path: string, title?: string) {
  sendAnalyticsEvent('page_view', {
    page_path: path,
    page_title: title || document.title,
  });
}

/**
 * 2. Track query submission
 */
export interface QuerySubmittedParams {
  input_mode: 'voice' | 'text';
  language: 'en' | 'hi' | 'hi-en' | string;
  source: 'mic' | 'quick_prompt' | 'palette' | 'text_box';
}

export function trackQuerySubmitted(params: QuerySubmittedParams) {
  sendAnalyticsEvent('query_submitted', {
    input_mode: params.input_mode,
    language: params.language,
    source: params.source,
  });
}

/**
 * 3. Track query completion & latency metrics
 */
export interface QueryCompletedParams {
  total_latency_ms: number;
  has_citations: boolean;
  citations_count: number;
  groq_synthesis_used: boolean;
}

export function trackQueryCompleted(params: QueryCompletedParams) {
  sendAnalyticsEvent('query_completed', {
    total_latency_ms: Math.round(params.total_latency_ms),
    has_citations: params.has_citations,
    citations_count: params.citations_count,
    groq_synthesis_used: params.groq_synthesis_used,
  });
}

/**
 * 4. Track guardrail rejections (out-of-domain / safety gates)
 */
export interface GuardrailRejectedParams {
  reason: 'out_of_domain' | 'safety_gate' | string;
  query_snippet: string;
}

export function trackGuardrailRejected(params: GuardrailRejectedParams) {
  sendAnalyticsEvent('guardrail_rejected', {
    reason: params.reason,
    query_snippet: params.query_snippet.slice(0, 60),
  });
}

/**
 * 5. Track developer profile / social link clicks
 */
export interface DevProfileClickedParams {
  dev_name: string;
  link_type: 'portfolio' | 'linkedin' | 'github' | 'x' | string;
  url?: string;
}

export function trackDevProfileClicked(params: DevProfileClickedParams) {
  sendAnalyticsEvent('dev_profile_clicked', {
    dev_name: params.dev_name,
    link_type: params.link_type,
    ...(params.url ? { url: params.url } : {}),
  });
}
