import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect, useState } from 'react';
import { Shell } from './components/layout/Shell';
import { BrandLoader } from './components/common/BrandLoader';
import { trackPageView } from './utils/analytics';

const AskPage = lazy(() => import('./pages/AskPage').then((module) => ({ default: module.AskPage })));
const EvidencePage = lazy(() => import('./pages/EvidencePage').then((module) => ({ default: module.EvidencePage })));

import { playThemeSound } from './utils/soundEffects';

function PageViewTracker() {
  const location = useLocation();
  useEffect(() => {
    trackPageView(location.pathname + location.search);
  }, [location]);
  return null;
}

export default function App() {
  const [showBrandLoader, setShowBrandLoader] = useState(true);
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('vani_theme');
    if (saved === 'dark') return true;
    if (saved === 'light') return false;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  const handleToggleTheme = () => {
    setIsDark((prev) => {
      const next = !prev;
      playThemeSound(next);
      return next;
    });
  };

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('vani_theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('vani_theme', 'light');
    }
  }, [isDark]);

  return (
    <BrowserRouter>
      {showBrandLoader && (
        <BrandLoader onComplete={() => setShowBrandLoader(false)} />
      )}
      <PageViewTracker />
      <Shell isDark={isDark} onToggleTheme={handleToggleTheme}>
        <Suspense fallback={<div className="py-20 text-center text-sm text-slate-600 dark:text-slate-400">Loading workspace…</div>}>
          <Routes>
            <Route path="/" element={<Navigate to="/ask" replace />} />
            <Route path="/ask" element={<AskPage />} />
            <Route path="/evidence" element={<EvidencePage />} />
            <Route
              path="*"
              element={
                <div className="py-20 max-w-md mx-auto text-center space-y-4">
                  <h1 className="text-5xl font-extrabold text-slate-900 dark:text-white">404</h1>
                  <p className="text-slate-600 dark:text-slate-400">The requested page does not exist.</p>
                  <a
                    href="/ask"
                    className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-500 transition-colors shadow-md"
                  >
                    Return to Voice Workspace
                  </a>
                </div>
              }
            />
          </Routes>
        </Suspense>
      </Shell>
    </BrowserRouter>
  );
}

