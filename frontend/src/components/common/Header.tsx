import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Microphone,
  ChartBar,
  CircleNotch,
  CheckCircle,
  XCircle,
  Waveform,
  Gear,
} from '@phosphor-icons/react';
import type { ReadyResponse } from '../../types/api';

interface HeaderProps {
  ready: ReadyResponse | null;
  isLoadingReady: boolean;
  isDark: boolean;
  onToggleTheme: () => void;
  onOpenSystemChecks: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  ready,
  isLoadingReady,
  onOpenSystemChecks,
}) => {
  const isReady = ready?.status === 'ready';

  return (
    <header className="sticky top-0 z-40 w-full h-[64px] border-b border-white/8 bg-[#070b14]/80 backdrop-blur-xl transition-colors select-none">
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:shadow-lg focus:font-semibold focus:text-xs"
      >
        Skip to main content
      </a>

      <div className="max-w-7xl mx-auto h-full px-4 sm:px-6 lg:px-8 flex items-center justify-between gap-4">
        {/* Left: Brand Identity */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-blue-600 to-cyan-400 flex items-center justify-center text-white shadow-[0_0_15px_rgba(6,182,212,0.4)]">
            <Waveform size={18} weight="bold" />
          </div>
          <div className="flex flex-col">
            <span className="text-sm font-extrabold tracking-tight text-white leading-none">
              VANI <span className="text-cyan-400">RAG</span>
            </span>
            <span className="text-[9px] font-semibold text-slate-400 tracking-wider uppercase mt-0.5">
              MSMARCO-XI Multilingual RAG
            </span>
          </div>
        </div>

        {/* Center: Clean Nav Pills */}
        <nav aria-label="Main Navigation" className="flex items-center gap-1 bg-white/5 p-1 rounded-full border border-white/10">
          <NavLink
            to="/ask"
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3.5 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-blue-600/90 text-white shadow-xs border border-blue-400/30'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`
            }
          >
            <Microphone size={14} weight="bold" />
            <span>Voice Workspace</span>
          </NavLink>

          <NavLink
            to="/evidence"
            className={({ isActive }) =>
              `flex items-center gap-1.5 px-3.5 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-blue-600/90 text-white shadow-xs border border-blue-400/30'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
              }`
            }
          >
            <ChartBar size={14} weight="bold" />
            <span>System Evidence</span>
          </NavLink>
        </nav>

        {/* Right: Operational Readiness & Diagnostics Button */}
        <div className="flex items-center gap-3">
          {/* Readiness Status Button */}
          <button
            type="button"
            onClick={onOpenSystemChecks}
            aria-haspopup="dialog"
            className={`hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium border transition-all cursor-pointer ${
              isLoadingReady
                ? 'bg-white/5 border-white/10 text-slate-400'
                : isReady
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30 hover:bg-emerald-500/20'
                : 'bg-rose-500/10 text-rose-300 border-rose-500/30 hover:bg-rose-500/20'
            }`}
            title="Backend operational readiness (/ready). Proves request-serving ability; independent from benchmark qualification."
          >
            {isLoadingReady ? (
              <CircleNotch size={12} className="animate-spin text-slate-400" />
            ) : isReady ? (
              <CheckCircle size={12} weight="fill" className="text-emerald-400" />
            ) : (
              <XCircle size={12} weight="fill" className="text-rose-400" />
            )}

            <span className="font-semibold">
              {isLoadingReady ? 'Checking' : isReady ? 'Backend operationally ready' : 'Backend not ready'}
            </span>
          </button>

          {/* System Settings / Diagnostics Cog Icon */}
          <button
            type="button"
            onClick={onOpenSystemChecks}
            className="w-8 h-8 rounded-full bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white border border-white/10 flex items-center justify-center transition-all cursor-pointer active:scale-95"
            title="System Diagnostics & Settings"
            aria-label="System Diagnostics & Settings"
          >
            <Gear size={16} />
          </button>
        </div>
      </div>
    </header>
  );
};
