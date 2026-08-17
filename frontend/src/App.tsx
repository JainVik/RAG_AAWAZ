import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { lazy, Suspense, useEffect, useState } from 'react';
import { Shell } from './components/layout/Shell';

const AskPage = lazy(() => import('./pages/AskPage').then((module) => ({ default: module.AskPage })));
const EvidencePage = lazy(() => import('./pages/EvidencePage').then((module) => ({ default: module.EvidencePage })));

export default function App() {
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('vani_theme');
    if (saved === 'dark') return true;
    if (saved === 'light') return false;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

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
      <Shell isDark={isDark} onToggleTheme={() => setIsDark((prev) => !prev)}>
        <Suspense fallback={<div className="py-20 text-center text-sm text-slate-600 dark:text-slate-400">Loading workspace…</div>}><Routes>
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
        </Routes></Suspense>
      </Shell>
    </BrowserRouter>
  );
}
