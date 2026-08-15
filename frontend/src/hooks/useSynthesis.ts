import { useEffect, useMemo, useState } from 'react';
import type { QueryResponse, SynthesisResponse } from '../types/api';
import { ApiError, sendSynthesis } from '../services/api';

interface SynthesisState {
  key: string | null;
  isLoading: boolean;
  result: SynthesisResponse | null;
  error: string | null;
}

export interface UseSynthesisResult {
  isLoading: boolean;
  result: SynthesisResponse | null;
  error: string | null;
}

const pendingRequests = new Map<string, Promise<SynthesisResponse>>();

function requestOnce(requestId: string, token: string): Promise<SynthesisResponse> {
  const key = `${requestId}:${token}`;
  const existing = pendingRequests.get(key);
  if (existing) return existing;

  const request = sendSynthesis({ request_id: requestId, token });
  pendingRequests.set(key, request);
  void request.then(
    () => pendingRequests.delete(key),
    () => pendingRequests.delete(key)
  );
  return request;
}

function synthesisErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return 'The synthesis response could not be verified. The evidence answer remains available.';
}

export function useSynthesis(primaryResult: QueryResponse | null): UseSynthesisResult {
  const requestId = primaryResult?.request_id ?? null;
  const offer = primaryResult?.synthesis ?? null;
  const key = requestId && offer ? `${requestId}:${offer.token}` : null;
  const [state, setState] = useState<SynthesisState>({
    key: null,
    isLoading: false,
    result: null,
    error: null,
  });

  useEffect(() => {
    if (!key || !requestId || !offer) {
      setState({ key: null, isLoading: false, result: null, error: null });
      return;
    }

    let active = true;
    setState({ key, isLoading: true, result: null, error: null });
    // The promise is shared by token so React StrictMode cannot consume a one-shot offer twice.
    void requestOnce(requestId, offer.token).then(
      (result) => {
        if (!active) return;
        if (result.request_id !== requestId) {
          setState({
            key,
            isLoading: false,
            result: null,
            error: 'The synthesis response did not match this query.',
          });
          return;
        }
        setState({ key, isLoading: false, result, error: null });
      },
      (error: unknown) => {
        if (!active) return;
        setState({
          key,
          isLoading: false,
          result: null,
          error: synthesisErrorMessage(error),
        });
      }
    );

    return () => {
      active = false;
    };
  }, [key, offer, requestId]);

  return useMemo(() => {
    if (!key) return { isLoading: false, result: null, error: null };
    if (state.key !== key) return { isLoading: true, result: null, error: null };
    return { isLoading: state.isLoading, result: state.result, error: state.error };
  }, [key, state]);
}
