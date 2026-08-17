import React, { useEffect, useRef } from 'react';
import { ArrowClockwise, CheckCircle, Clock, Info, ShieldCheck, WarningCircle, X, XCircle } from '@phosphor-icons/react';
import type { HealthResponse, ReadyResponse } from '../../types/api';

interface Props { isOpen: boolean; onClose: () => void; health: HealthResponse | null; ready: ReadyResponse | null; isLoading: boolean; onRefresh: () => void; }

export const SystemChecksDrawer: React.FC<Props> = ({ isOpen, onClose, health, ready, isLoading, onRefresh }) => {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!isOpen) return;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [isOpen, onClose]);
  if (!isOpen) return null;

  const alive = health?.status === 'healthy';
  const operational = ready?.status === 'ready';
  const checks = Object.entries(ready?.checks ?? {});
  const format = (value: number | null, suffix = '') => value === null ? 'Not reported' : `${value}${suffix}`;

  return (
    <div role="dialog" aria-modal="true" aria-labelledby="checks-title" className="fixed inset-0 z-50 overflow-hidden">
      <button type="button" aria-label="Close system checks" onClick={onClose} className="fixed inset-0 bg-black/30 backdrop-blur-[2px] cursor-pointer" />
      <div className="fixed inset-y-0 right-0 flex max-w-full pl-10 pointer-events-none">
        <div className="refractive-glass-card refractive-glass-card-primary flex w-screen max-w-md flex-col text-slate-100 shadow-2xl rounded-none rounded-l-2xl border-y-0 border-r-0 pointer-events-auto">
          <header className="flex items-center justify-between border-b border-white/10 p-6">
            <div><h2 id="checks-title" className="flex items-center gap-2 text-lg font-bold"><ShieldCheck className="text-blue-400" />System checks</h2><p className="text-xs text-slate-400">Liveness is separate from operational readiness.</p></div>
            <button
              ref={closeRef}
              type="button"
              aria-label="Close system checks drawer"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                onClose();
              }}
              className="relative z-20 rounded-lg p-1.5 text-slate-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
            >
              <X size={20} className="pointer-events-none" />
            </button>
          </header>
          <div className="flex-1 space-y-5 overflow-y-auto p-6">
            <div className="grid grid-cols-2 gap-3">
              <StatusCard title="Backend process" ok={alive} value={alive ? 'Alive' : 'Offline'} detail={health?.version ? `Version ${health.version}` : health?.error ?? 'No response'} />
              <StatusCard title="Operational readiness" ok={operational} value={operational ? 'Ready' : 'Not ready'} detail={operational ? 'All required checks passed' : 'One or more checks failed'} />
            </div>
            <div className="glass-inner-box flex gap-2 p-3 text-xs text-slate-300"><Info size={18} className="shrink-0 text-blue-400" />Benchmark qualification is shown on the Evidence page and does not determine runtime readiness.</div>
            <section className="space-y-2"><h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">Readiness checks</h3>{checks.length ? checks.map(([name, check]) => <div key={name} className="flex items-start justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.04] p-3 transition-colors hover:bg-white/[0.07]"><div><span className="text-xs font-semibold text-white">{name.replaceAll('_', ' ')}</span>{check.reason && <p className="mt-1 text-[11px] text-slate-400">{check.reason}</p>}</div>{check.ready ? <CheckCircle className="shrink-0 text-emerald-400" weight="fill" /> : <XCircle className="shrink-0 text-rose-400" weight="fill" />}</div>) : <p className="glass-inner-box p-4 text-xs text-slate-400">No readiness payload available.</p>}</section>
            <section className="space-y-3 rounded-xl border border-white/10 bg-white/[0.04] p-4"><h3 className="flex items-center gap-2 text-xs font-bold text-white"><Clock className="text-blue-400" />Runtime contract</h3><Row label="Hard deadline" value={format(ready?.runtime.rag_deadline_ms ?? null, ' ms')} /><Row label="Fallback threshold" value={format(ready?.runtime.rag_fallback_at_ms ?? null, ' ms')} /><Row label="Process instance" value={ready?.runtime.process_instance_id ?? 'Not reported'} /><Row label="Started at" value={ready?.runtime.process_started_at ? new Date(ready.runtime.process_started_at).toLocaleString() : 'Not reported'} /><Row label="Voice requests" value={format(ready?.runtime.voice_requests_started ?? null)} /></section>
          </div>
          <footer className="flex items-center justify-between border-t border-white/10 p-6"><span className="text-xs text-slate-400">Auto-polled every 15s</span><button type="button" onClick={onRefresh} disabled={isLoading} className="flex items-center gap-1.5 rounded-xl bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_15px_rgba(37,99,235,0.45)] hover:shadow-[0_0_20px_rgba(6,182,212,0.6)] px-3.5 py-2 text-xs font-bold transition-all transform hover:scale-105 active:scale-95 disabled:opacity-50 disabled:transform-none cursor-pointer"><ArrowClockwise size={14} className={isLoading ? 'animate-spin' : ''} />Refresh</button></footer>
        </div>
      </div>
    </div>
  );
};

const StatusCard = ({ title, ok, value, detail }: { title: string; ok: boolean; value: string; detail: string }) => <div className={`rounded-xl border p-3.5 ${ok ? 'border-status-ready-border bg-status-ready-bg' : 'border-status-error-border bg-status-error-bg'}`}><div className="mb-1.5 flex items-center justify-between text-xs font-semibold text-slate-300">{title}{ok ? <CheckCircle className="text-emerald-400" weight="fill" /> : <WarningCircle className="text-rose-400" weight="fill" />}</div><div className={`text-sm font-bold ${ok ? 'text-emerald-400' : 'text-rose-400'}`}>{value}</div><p className="mt-1 text-[11px] text-slate-400">{detail}</p></div>;
const Row = ({ label, value }: { label: string; value: string }) => <div className="flex justify-between gap-3 text-xs"><span className="text-slate-400">{label}</span><span className="break-all text-right font-mono text-white">{value}</span></div>;
