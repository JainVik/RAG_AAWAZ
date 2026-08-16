import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { Header } from '../common/Header';
import type { HealthResponse, ReadyResponse } from '../../types/api';
import { getHealth, getReady } from '../../services/api';
import { GradientWaves } from '../ui/GradientWaves';

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
      <div className="relative min-h-[100dvh] flex flex-col text-slate-100 overflow-x-hidden selection:bg-cyan-500/30 selection:text-cyan-200">
        {/* Full-Screen Animated 3D WebGL Gradient Waves Background */}
        <div className="fixed inset-0 z-0 pointer-events-none w-screen h-screen overflow-hidden bg-[#070b14]">
          <GradientWaves
            horizonColor="#050814"
            waveColor="#1e40af"
            crestColor="#06b6d4"
            speed={0.4}
            amplitude={2.6}
            waveScale={0.7}
            waveRatio={0.9}
            swell={35}
            turbulence={20}
            tilt={1.11}
            zoom={1.0}
            height={4.8}
            fogDepth={16}
            detail="medium"
            brightness={1.15}
            opacity={0.9}
            mouseInteraction={true}
            parallaxStrength={0.4}
            grain={true}
            grainIntensity={0.04}
          />
        </div>

        {/* Global Application Header */}
        <div className="relative z-20">
          <Header
            ready={ready}
            isLoadingReady={isLoadingStatus}
            isDark={isDark}
            onToggleTheme={onToggleTheme}
          />
        </div>

        {/* Main Content Area with Skip Target */}
        <main id="main-content" className="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col relative z-10">
          {children}
        </main>
      </div>
    </ShellContext.Provider>
  );
};
