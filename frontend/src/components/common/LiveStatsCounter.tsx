import React, { useEffect, useState } from 'react';
import { Eye, Lightning } from '@phosphor-icons/react';
import { getOperationalMetrics } from '../../services/api';

const STORAGE_VIEWS_KEY = 'vani_real_views_count';
const SESSION_VIEW_FLAG = 'vani_session_tracked';

function getStoredViews(): number {
  try {
    const stored = localStorage.getItem(STORAGE_VIEWS_KEY);
    const parsed = stored ? parseInt(stored, 10) : 0;
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  } catch {
    return 1;
  }
}

export const LiveStatsCounter: React.FC = () => {
  const [views, setViews] = useState<number>(getStoredViews);
  const [queries, setQueries] = useState<number | null>(null);
  const [isQueryPulse, setIsQueryPulse] = useState(false);

  // 1. Increment view count strictly ONCE per session/tab lifecycle
  useEffect(() => {
    try {
      if (!sessionStorage.getItem(SESSION_VIEW_FLAG)) {
        sessionStorage.setItem(SESSION_VIEW_FLAG, 'true');
        const current = getStoredViews();
        const next = current + 1;
        localStorage.setItem(STORAGE_VIEWS_KEY, String(next));
        setViews(next);
      } else {
        setViews(getStoredViews());
      }
    } catch {
      // Ignore storage errors
    }
  }, []);

  // 2. Fetch authentic live request/query count directly from backend /metrics
  useEffect(() => {
    let isMounted = true;
    const fetchBackendMetrics = async () => {
      try {
        const data = await getOperationalMetrics();
        if (isMounted && typeof data.requests_total === 'number') {
          setQueries(data.requests_total);
        }
      } catch {
        // Fallback silently if offline
      }
    };

    void fetchBackendMetrics();
    // Non-blocking background sync every 15s
    const interval = setInterval(fetchBackendMetrics, 15_000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // 3. Increment query count live immediately when a query completes in this browser
  useEffect(() => {
    const handleQueryEvent = () => {
      setQueries((prev) => (prev !== null ? prev + 1 : 1));
      setIsQueryPulse(true);
      setTimeout(() => setIsQueryPulse(false), 700);
    };

    window.addEventListener('vani:query_completed', handleQueryEvent);
    return () => {
      window.removeEventListener('vani:query_completed', handleQueryEvent);
    };
  }, []);

  return (
    <div
      className="refractive-glass-pill flex items-center p-1.5 px-3.5 transition-all duration-300 select-none shadow-xs text-xs font-semibold text-black dark:text-slate-200"
      title="Live Backend Operational Metrics"
      aria-label={`Live site statistics: ${views.toLocaleString()} views, ${queries ?? '...'} queries`}
    >
      <div className="flex items-center gap-2.5 sm:gap-3 py-0.5">
        {/* Real Views Counter */}
        <div className="flex items-center gap-1.5">
          <Eye size={13} weight="bold" className="text-blue-600 dark:text-cyan-400 shrink-0" />
          <span className="font-mono tabular-nums font-bold text-black dark:text-white">
            {views.toLocaleString()}
          </span>
          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium hidden sm:inline">
            views
          </span>
        </div>

        {/* Subtle Divider */}
        <div className="w-[1px] h-3 bg-black/10 dark:bg-white/10 shrink-0" aria-hidden="true" />

        {/* Real Backend Queries Counter */}
        <div
          className={`flex items-center gap-1.5 transition-transform duration-300 ${
            isQueryPulse ? 'scale-110 text-amber-500' : ''
          }`}
        >
          <Lightning size={13} weight="fill" className="text-amber-500 shrink-0" />
          <span className="font-mono tabular-nums font-bold text-black dark:text-white">
            {queries !== null ? queries.toLocaleString() : '...'}
          </span>
          <span className="text-[10px] text-slate-500 dark:text-slate-400 font-medium hidden sm:inline">
            queries
          </span>
        </div>
      </div>
    </div>
  );
};
