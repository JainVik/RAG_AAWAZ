import React, { useEffect, useState } from 'react';
import {
  X,
  ArrowClockwise,
  CheckCircle,
  XCircle,
  WarningCircle,
  ShieldCheck,
  Cpu,
  Database,
  Waveform,
  Clock,
  Info,
} from '@phosphor-icons/react';
import type { HealthResponse, ReadyResponse, ReadyCheck } from '../../types/api';

interface SystemChecksDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  health: HealthResponse | null;
  ready: ReadyResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
}

export const SystemChecksDrawer: React.FC<SystemChecksDrawerProps> = ({
  isOpen,
  onClose,
  health,
  ready,
  isLoading,
  onRefresh,
}) => {
  const [activeTab, setActiveTab] = useState<'readiness' | 'liveness'>('readiness');

  // Close on Escape key press
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const isReady = ready?.status === 'ready';
  const isAlive = health?.status !== 'offline' && health?.status !== 'error';

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
      className="fixed inset-0 z-50 overflow-hidden"
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-slate-950/60 backdrop-blur-xs transition-opacity"
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10">
        <div className="w-screen max-w-md bg-[#0b1220] border-l border-white/10 shadow-2xl flex flex-col justify-between text-slate-100">
          {/* Drawer Header */}
          <div className="p-6 border-b border-white/10 flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-white/5 border border-white/10">
                <ShieldCheck size={20} className="text-cyan-400" weight="bold" />
              </div>
              <div>
                <h2 id="drawer-title" className="text-lg font-bold text-white tracking-tight">
                  System Diagnostics
                </h2>
                <p className="text-xs text-slate-400">Process liveness & operational readiness</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/5 transition-colors cursor-pointer"
              aria-label="Close diagnostics drawer"
            >
              <X size={20} />
            </button>
          </div>

          {/* Drawer Body */}
          <div className="p-6 overflow-y-auto flex-1 space-y-6">
            {/* Top Level Status Summaries */}
            <div className="grid grid-cols-2 gap-3">
              {/* Operational Readiness Card */}
              <div
                className={`p-3.5 rounded-xl border ${
                  isReady
                    ? 'bg-emerald-950/20 border-emerald-500/30'
                    : 'bg-rose-950/20 border-rose-500/30'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-slate-300">Operational Readiness</span>
                  {isReady ? (
                    <CheckCircle size={16} className="text-emerald-400" weight="fill" />
                  ) : (
                    <XCircle size={16} className="text-rose-400" weight="fill" />
                  )}
                </div>
                <div
                  className={`text-sm font-bold ${
                    isReady ? 'text-emerald-400' : 'text-rose-400'
                  }`}
                >
                  {isReady ? 'Operationally ready' : 'Not ready'}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  {isReady
                    ? 'Qdrant, E5-small, and Sarvam smoke verified'
                    : 'Required service dependencies not yet initialized'}
                </p>
              </div>

              {/* Process Liveness Card */}
              <div
                className={`p-3.5 rounded-xl border ${
                  isAlive
                    ? 'bg-blue-950/20 border-blue-500/30'
                    : 'bg-slate-900/50 border-white/10'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-semibold text-slate-300">Process Liveness</span>
                  {isAlive ? (
                    <CheckCircle size={16} className="text-blue-400" weight="fill" />
                  ) : (
                    <WarningCircle size={16} className="text-amber-400" weight="fill" />
                  )}
                </div>
                <div
                  className={`text-sm font-bold ${
                    isAlive ? 'text-blue-400' : 'text-slate-400'
                  }`}
                >
                  {isAlive ? 'Process active' : 'Process offline'}
                </div>
                <p className="text-[11px] text-slate-400 mt-1">
                  Backend version: {health?.version || '0.1.0-dev'}
                </p>
              </div>
            </div>

            {/* Note banner explaining decoupling */}
            <div className="p-3 bg-white/5 border border-white/10 rounded-xl flex items-start gap-2.5 text-xs text-slate-300">
              <Info size={18} className="text-cyan-400 shrink-0 mt-0.5" />
              <p>
                <strong>Operational readiness</strong> confirms the backend can receive and process queries. It is independent of benchmark evaluation qualification.
              </p>
            </div>

            {/* Tab Navigation */}
            <div className="flex border-b border-white/10">
              <button
                type="button"
                onClick={() => setActiveTab('readiness')}
                className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
                  activeTab === 'readiness'
                    ? 'border-cyan-400 text-cyan-400'
                    : 'border-transparent text-slate-400 hover:text-white'
                }`}
              >
                Dependency Checks (/ready)
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('liveness')}
                className={`pb-2.5 px-3 text-xs font-semibold border-b-2 transition-colors cursor-pointer ${
                  activeTab === 'liveness'
                    ? 'border-cyan-400 text-cyan-400'
                    : 'border-transparent text-slate-400 hover:text-white'
                }`}
              >
                Runtime & Deadlines
              </button>
            </div>

            {/* Tab Content: Dependency Checks */}
            {activeTab === 'readiness' && (
              <div className="space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                  Required Subsystems
                </h3>

                {/* Subsystem items */}
                <div className="space-y-2.5">
                  {/* Qdrant Vector Collection */}
                  <div className="p-3 bg-white/5 border border-white/10 rounded-lg flex items-start gap-3">
                    <Database size={18} className="text-slate-400 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-white">Qdrant Vector DB</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                            ready?.checks?.qdrant
                              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800'
                              : 'bg-rose-950/40 text-rose-400 border-rose-800'
                          }`}
                        >
                          {ready?.checks?.qdrant ? 'ONLINE' : 'NOT INITIALIZED'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {typeof ready?.checks?.qdrant === 'object' && ready?.checks?.qdrant !== null
                          ? (ready.checks.qdrant as ReadyCheck).message || 'Collection active'
                          : 'goa_gov_chunks_v1 (384d Cosine)'}
                      </p>
                    </div>
                  </div>

                  {/* Multilingual E5-small */}
                  <div className="p-3 bg-white/5 border border-white/10 rounded-lg flex items-start gap-3">
                    <Cpu size={18} className="text-slate-400 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-white">Dense Embeddings</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                            ready?.checks?.model || ready?.checks?.e5_embeddings
                              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800'
                              : 'bg-rose-950/40 text-rose-400 border-rose-800'
                          }`}
                        >
                          {ready?.checks?.model || ready?.checks?.e5_embeddings ? 'LOADED' : 'UNVERIFIED'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        intfloat/multilingual-e5-small (384 dimensions)
                      </p>
                    </div>
                  </div>

                  {/* Sarvam Realtime STT */}
                  <div className="p-3 bg-white/5 border border-white/10 rounded-lg flex items-start gap-3">
                    <Waveform size={18} className="text-slate-400 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-white">Sarvam Speech STT</span>
                        <span
                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                            ready?.checks?.sarvam || ready?.checks?.sarvam_speech
                              ? 'bg-emerald-950/40 text-emerald-400 border-emerald-800'
                              : 'bg-rose-950/40 text-rose-400 border-rose-800'
                          }`}
                        >
                          {ready?.checks?.sarvam || ready?.checks?.sarvam_speech ? 'CONFIGURED' : 'UNCONFIGURED'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        Realtime 16kHz PCM WebSocket streaming (saaras:v3-realtime)
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Tab Content: Runtime & Deadlines */}
            {activeTab === 'liveness' && (
              <div className="space-y-4">
                <div className="p-3.5 bg-white/5 border border-white/10 rounded-xl space-y-3">
                  <div className="flex items-center gap-2 text-xs font-semibold text-white">
                    <Clock size={16} className="text-cyan-400" />
                    <span>Configured Frozen Deadlines</span>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div className="p-2.5 bg-white/5 rounded-lg border border-white/10">
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Fallback Deadline</span>
                      <span className="text-white font-mono font-semibold text-sm">
                        {ready?.deadlines?.fallback_ms || 8000} ms
                      </span>
                    </div>
                    <div className="p-2.5 bg-white/5 rounded-lg border border-white/10">
                      <span className="text-slate-400 block text-[10px] uppercase font-bold">Hard Cap Deadline</span>
                      <span className="text-white font-mono font-semibold text-sm">
                        {ready?.deadlines?.hard_ms || 12000} ms
                      </span>
                    </div>
                  </div>
                </div>

                <div className="p-3.5 bg-white/5 border border-white/10 rounded-xl space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Instance ID:</span>
                    <span className="font-mono text-white font-medium">
                      {ready?.instance_id || 'local-loopback-01'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Process Started:</span>
                    <span className="font-mono text-white">
                      {ready?.started_at ? new Date(ready.started_at).toLocaleTimeString() : 'Running'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Proxy Target:</span>
                    <span className="font-mono text-white">127.0.0.1:8000</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Drawer Footer */}
          <div className="p-6 border-t border-white/10 bg-white/5 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Auto-polled every 15s
            </span>
            <button
              type="button"
              onClick={onRefresh}
              disabled={isLoading}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-500 transition-colors disabled:opacity-50 cursor-pointer"
            >
              <ArrowClockwise size={14} className={isLoading ? 'animate-spin' : ''} />
              {isLoading ? 'Checking...' : 'Refresh status'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
