import React from 'react';
import { NavLink } from 'react-router-dom';
import { Microphone, ChartBar } from '@phosphor-icons/react';

interface HeaderProps {
  isDark?: boolean;
  onToggleTheme?: () => void;
  ready?: unknown;
  isLoadingReady?: boolean;
  onOpenSystemChecks?: () => void;
}

export const Header: React.FC<HeaderProps> = () => {
  return (
    <header className="sticky top-0 z-40 w-full pt-4 pb-2 transition-colors select-none">
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:shadow-lg focus:font-semibold focus:text-xs"
      >
        Skip to main content
      </a>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex items-center justify-center">
        {/* Centered Clean Nav Pills with Liquid Glass */}
        <nav aria-label="Main Navigation" className="refractive-glass-pill flex items-center gap-1.5 p-1.5">
          <NavLink
            to="/ask"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                isActive
                  ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_20px_rgba(37,99,235,0.45)]'
                  : 'text-slate-400 hover:text-white hover:bg-white/5 font-medium'
              }`
            }
          >
            <Microphone size={14} weight="bold" />
            <span>Voice Workspace</span>
          </NavLink>

          <NavLink
            to="/evidence"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer ${
                isActive
                  ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_20px_rgba(37,99,235,0.45)]'
                  : 'text-slate-400 hover:text-white hover:bg-white/5 font-medium'
              }`
            }
          >
            <ChartBar size={14} weight="bold" />
            <span>System Evidence</span>
          </NavLink>
        </nav>
      </div>
    </header>
  );
};
