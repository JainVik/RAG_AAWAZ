import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Header } from '../common/Header';
import type { HealthResponse, ReadyResponse } from '../../types/api';
import { getHealth, getReady } from '../../services/api';
import { GradientWaves } from '../ui/GradientWaves';
import { LiquidGlassDefs } from '../ui/LiquidGlassDefs';

interface ShellContextType {
  openSystemChecks: () => void;
  health: HealthResponse | null;
  ready: ReadyResponse | null;
  isLoadingStatus: boolean;
  refreshStatus: () => void;
}

const ShellContext = createContext<ShellContextType>({
  openSystemChecks: () => {},
  health: null,
  ready: null,
  isLoadingStatus: false,
  refreshStatus: () => {},
});

export const useShell = () => useContext(ShellContext);

interface ShellProps {
  children: React.ReactNode;
  isDark: boolean;
  onToggleTheme: () => void;
}

export const Shell: React.FC<ShellProps> = ({ children, isDark, onToggleTheme }) => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [ready, setReady] = useState<ReadyResponse | null>(null);
  const [isLoadingStatus, setIsLoadingStatus] = useState<boolean>(true);

  const fetchStatus = useCallback(async () => {
    setIsLoadingStatus(true);
    try {
      const [h, r] = await Promise.all([getHealth(), getReady()]);
      setHealth(h);
      setReady(r);
    } catch {
      // Handled gracefully in service methods
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  // Initial fetch on page load (no recurring polling)
  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  return (
    <ShellContext.Provider
      value={{
        openSystemChecks: () => {},
        health,
        ready,
        isLoadingStatus,
        refreshStatus: fetchStatus,
      }}
    >
      <div className="relative min-h-[100dvh] flex flex-col text-black dark:text-slate-100 selection:bg-blue-500/30 selection:text-blue-900 dark:selection:text-blue-200">
        {/* Global SVG Optical Displacement Definitions */}
        <LiquidGlassDefs />

        {/* Full-Screen Animated 3D WebGL Gradient Waves Background */}
        <div className="fixed inset-0 z-0 pointer-events-none w-screen h-screen overflow-hidden bg-canvas transition-colors duration-500">
          <GradientWaves
            horizonColor={isDark ? '#03050c' : '#E8E8E9'}
            waveColor={isDark ? '#2e1065' : '#4338ca'}
            crestColor={isDark ? '#7c3aed' : '#8b5cf6'}
            speed={0.35}
            amplitude={2.7}
            waveScale={0.7}
            waveRatio={0.9}
            swell={35}
            turbulence={22}
            tilt={1.11}
            zoom={1.0}
            height={4.8}
            fogDepth={16}
            detail="medium"
            brightness={isDark ? 0.95 : 0.85}
            opacity={isDark ? 0.92 : 0.70}
            mouseInteraction={true}
            parallaxStrength={0.4}
            grain={true}
            grainIntensity={isDark ? 0.035 : 0.015}
          />
        </div>

        {/* Global Application Header */}
        <Header
          ready={ready}
          isLoadingReady={isLoadingStatus}
          isDark={isDark}
          onToggleTheme={onToggleTheme}
        />

        {/* Main Content Area with Skip Target */}
        <main id="main-content" className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col relative z-10">
          {children}
        </main>
      </div>
    </ShellContext.Provider>
  );
};
