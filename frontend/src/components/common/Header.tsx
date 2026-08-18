import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Microphone,
  ChartBar,
  Sun,
  MoonStars,
  List,
  X,
  Users,
  Lightning,
  CheckCircle,
  WarningCircle,
  ArrowUpRight,
  ShieldCheck,
} from '@phosphor-icons/react';
import { motion, AnimatePresence } from 'motion/react';
import { TeamAvatarGroup } from './TeamAvatarGroup';
import { LiveStatsCounter } from './LiveStatsCounter';
import { TEAM_MEMBERS } from '../../config/team';
import { trackDevProfileClicked } from '../../utils/analytics';
import type { ReadyResponse } from '../../types/api';

interface HeaderProps {
  isDark?: boolean;
  onToggleTheme?: () => void;
  ready?: ReadyResponse | null;
  isLoadingReady?: boolean;
  onOpenSystemChecks?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  isDark = true,
  onToggleTheme,
  ready,
  onOpenSystemChecks,
}) => {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const isReady = ready?.status === 'ready';

  return (
    <header className="sticky top-0 z-40 w-full pt-3 sm:pt-4 pb-2 transition-colors select-none">
      {/* Skip to main content link for accessibility */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-blue-600 focus:text-white focus:rounded-lg focus:shadow-lg focus:font-semibold focus:text-xs"
      >
        Skip to main content
      </a>

      <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 relative flex items-center justify-between lg:justify-center">
        {/* Top-Left Live Stats Counters Badge (Desktop Only) */}
        <div className="hidden lg:flex absolute left-4 sm:left-6 lg:left-8 items-center">
          <LiveStatsCounter />
        </div>

        {/* Centered Clean Nav Pills with Liquid Glass (Mobile: Icon only, Desktop: Icon + Text) */}
        <nav aria-label="Main Navigation" className="refractive-glass-pill flex items-center gap-1 sm:gap-1.5 p-1 sm:p-1.5">
          <NavLink
            to="/ask"
            className={({ isActive }) =>
              `flex items-center gap-1.5 sm:gap-2 p-2 sm:px-4 sm:py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                isActive
                  ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_20px_rgba(37,99,235,0.45)]'
                  : 'text-black hover:text-black dark:text-slate-400 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 font-semibold'
              }`
            }
            title="Voice Workspace"
            aria-label="Voice Workspace"
          >
            <Microphone size={16} weight="bold" className="shrink-0" />
            <span className="hidden sm:inline">Voice Workspace</span>
          </NavLink>

          <NavLink
            to="/evidence"
            className={({ isActive }) =>
              `flex items-center gap-1.5 sm:gap-2 p-2 sm:px-4 sm:py-1.5 rounded-full text-xs font-bold transition-all cursor-pointer whitespace-nowrap ${
                isActive
                  ? 'bg-gradient-to-tr from-blue-600 via-blue-500 to-cyan-400 text-white shadow-[0_0_20px_rgba(37,99,235,0.45)]'
                  : 'text-black hover:text-black dark:text-slate-400 dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 font-semibold'
              }`
            }
            title="System Evidence"
            aria-label="System Evidence"
          >
            <ChartBar size={16} weight="bold" className="shrink-0" />
            <span className="hidden sm:inline">System Evidence</span>
          </NavLink>
        </nav>

        {/* Top-Right Controls with Theme Toggle and Sidebar Button */}
        <div className="lg:absolute lg:right-4 sm:right-6 lg:right-8 flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Theme Switcher Button */}
          {onToggleTheme && (
            <button
              type="button"
              onClick={onToggleTheme}
              className="refractive-glass-pill p-2 text-black dark:text-slate-300 dark:hover:text-white transition-all cursor-pointer flex items-center justify-center group shadow-xs"
              title={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
              aria-label={isDark ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
            >
              {isDark ? (
                <Sun size={17} weight="bold" className="text-amber-400 transition-transform duration-300 group-hover:rotate-45" />
              ) : (
                <MoonStars size={17} weight="bold" className="text-blue-600 transition-transform duration-300 group-hover:-rotate-12" />
              )}
            </button>
          )}

          {/* Desktop Developer Avatars Stack */}
          <div className="hidden lg:block">
            <TeamAvatarGroup />
          </div>

          {/* Mobile Sidebar Hamburger Toggle Button */}
          <button
            type="button"
            onClick={() => setIsSidebarOpen(true)}
            className="lg:hidden refractive-glass-pill p-2 text-black dark:text-slate-300 hover:text-blue-600 dark:hover:text-white transition-all cursor-pointer flex items-center justify-center shadow-xs"
            title="Open Overview & Team Menu"
            aria-label="Open Overview & Team Menu"
          >
            <List size={18} weight="bold" />
          </button>
        </div>
      </div>

      {/* ================= MOBILE SLIDE-OVER SIDEBAR DRAWER ================= */}
      <AnimatePresence>
        {isSidebarOpen && (
          <div className="fixed inset-0 z-50 lg:hidden flex justify-end" role="dialog" aria-modal="true">
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={() => setIsSidebarOpen(false)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            />

            {/* Slide-over Drawer Panel */}
            <motion.aside
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 220 }}
              className="relative w-full max-w-xs sm:max-w-sm h-full bg-slate-100/95 dark:bg-[#0a0f1d]/95 backdrop-blur-2xl border-l border-black/10 dark:border-white/10 shadow-2xl p-5 overflow-y-auto flex flex-col justify-between text-black dark:text-white z-10"
            >
              <div className="space-y-6">
                {/* Drawer Top Header */}
                <div className="flex items-center justify-between pb-3 border-b border-black/10 dark:border-white/10">
                  <div className="flex items-center gap-2">
                    <ShieldCheck size={20} weight="bold" className="text-blue-600 dark:text-cyan-400" />
                    <span className="font-bold text-sm text-slate-900 dark:text-white">Workspace Menu</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setIsSidebarOpen(false)}
                    className="p-1.5 rounded-full hover:bg-black/5 dark:hover:bg-white/10 text-slate-500 dark:text-slate-400 transition-colors cursor-pointer"
                    aria-label="Close sidebar"
                  >
                    <X size={18} weight="bold" />
                  </button>
                </div>

                {/* Section 1: Live System Operational Metrics */}
                <div className="space-y-2.5">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Lightning size={13} weight="fill" className="text-amber-500" />
                    <span>Live Statistics</span>
                  </div>
                  <div className="p-3 rounded-xl bg-white/70 dark:bg-white/5 border border-black/5 dark:border-white/10 shadow-xs">
                    <LiveStatsCounter />
                  </div>
                </div>

                {/* Section 2: Developer Team & Profiles */}
                <div className="space-y-3">
                  <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400 flex items-center gap-1.5">
                    <Users size={13} weight="bold" className="text-blue-500" />
                    <span>Engineering Team</span>
                  </div>
                  <div className="space-y-2">
                    {TEAM_MEMBERS.map((member) => (
                      <div
                        key={member.id}
                        className="p-2.5 rounded-xl bg-white/70 dark:bg-white/5 border border-black/5 dark:border-white/10 flex items-center justify-between gap-3 shadow-xs"
                      >
                        <div className="flex items-center gap-2.5 min-w-0">
                          {member.avatar ? (
                            <img
                              src={member.avatar}
                              alt={member.name}
                              className="w-8 h-8 rounded-full object-cover shrink-0 ring-1 ring-black/10 dark:ring-white/20"
                            />
                          ) : (
                            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-600 to-cyan-500 flex items-center justify-center text-xs font-bold text-white shrink-0">
                              {member.initials}
                            </div>
                          )}
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-slate-900 dark:text-white truncate">
                              {member.name}
                            </div>
                            <div className="text-[10px] text-slate-500 dark:text-slate-400 truncate">
                              {member.links[0]?.label || 'Developer'}
                            </div>
                          </div>
                        </div>

                        {/* Portfolio Anchor Link */}
                        <a
                          href={member.profileUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={() => {
                            trackDevProfileClicked({
                              dev_name: member.name,
                              link_type: 'portfolio',
                              url: member.profileUrl,
                            });
                          }}
                          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold text-blue-600 dark:text-cyan-400 hover:bg-blue-500/10 transition-colors flex items-center gap-1 shrink-0 cursor-pointer"
                        >
                          <span>Profile</span>
                          <ArrowUpRight size={11} weight="bold" />
                        </a>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Section 3: System Status & Diagnostics Check */}
                {onOpenSystemChecks && (
                  <div className="space-y-2.5">
                    <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
                      System Diagnostics
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setIsSidebarOpen(false);
                        onOpenSystemChecks();
                      }}
                      className="w-full p-2.5 rounded-xl bg-white/70 dark:bg-white/5 border border-black/5 dark:border-white/10 hover:border-blue-500/40 text-xs font-bold flex items-center justify-between transition-all cursor-pointer shadow-xs"
                    >
                      <div className="flex items-center gap-2">
                        {isReady ? (
                          <CheckCircle size={15} weight="fill" className="text-emerald-500" />
                        ) : (
                          <WarningCircle size={15} weight="fill" className="text-amber-500" />
                        )}
                        <span>{isReady ? 'All Subsystems Online' : 'Check System Readiness'}</span>
                      </div>
                      <ArrowUpRight size={13} weight="bold" className="text-slate-400" />
                    </button>
                  </div>
                )}
              </div>

              {/* Drawer Bottom Footer */}
              <div className="pt-4 border-t border-black/10 dark:border-white/10 text-center text-[10px] text-slate-500 dark:text-slate-400">
                <span>VANI Multilingual Voice RAG Workspace</span>
              </div>
            </motion.aside>
          </div>
        )}
      </AnimatePresence>
    </header>
  );
};

