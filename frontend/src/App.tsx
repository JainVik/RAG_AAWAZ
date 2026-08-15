import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { Shell } from './components/layout/Shell';
import { AskPage } from './pages/AskPage';
import { EvidencePage } from './pages/EvidencePage';

export default function App() {
  const [isDark, setIsDark] = useState<boolean>(() => {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  return (
    <BrowserRouter>
      <Shell isDark={isDark} onToggleTheme={() => setIsDark(!isDark)}>
        <Routes>
          <Route path="/" element={<Navigate to="/ask" replace />} />
          <Route path="/ask" element={<AskPage />} />
          <Route path="/evidence" element={<EvidencePage />} />
          <Route
            path="*"
            element={
              <div className="py-20 max-w-md mx-auto text-center space-y-4">
                <h1 className="text-5xl font-extrabold text-white">404</h1>
                <p className="text-slate-400">The requested page does not exist.</p>
                <a
                  href="/ask"
                  className="inline-block px-4 py-2 bg-blue-600 text-white rounded-lg text-xs font-semibold hover:bg-blue-500 transition-colors"
                >
                  Return to Voice Workspace
                </a>
              </div>
            }
          />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
