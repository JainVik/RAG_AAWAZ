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
        {/* Centered Clean Nav Pills */}
        <nav aria-label="Main Navigation" className="flex items-center gap-1.5 bg-[#0a1020]/90 p-1.5 rounded-full border border-white/10 shadow-xl backdrop-blur-xl">
          <NavLink
            to="/ask"
            className={({ isActive }) =>
              `flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md border border-blue-400/40'
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
              `flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                isActive
                  ? 'bg-blue-600 text-white shadow-md border border-blue-400/40'
                  : 'text-slate-400 hover:text-white hover:bg-white/5'
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
