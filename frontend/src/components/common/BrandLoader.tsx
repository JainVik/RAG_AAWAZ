import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import hackerHouseLogo from '../../assets/brand-kit/Hacker-house-v2.svg';
import brandMark from '../../assets/brand-kit/2-47.svg';

interface BrandLoaderProps {
  onComplete?: () => void;
  minDisplayMs?: number;
}

export const BrandLoader: React.FC<BrandLoaderProps> = ({
  onComplete,
  minDisplayMs = 1200,
}) => {
  const [isSplitting, setIsSplitting] = useState(false);
  const [isMounted, setIsMounted] = useState(true);

  // Trigger split motion once resources are downloaded
  useEffect(() => {
    let active = true;

    async function loadAndTrigger() {
      const startTime = Date.now();

      // Download and preload page modules & fonts
      await Promise.allSettled([
        import('../../pages/AskPage'),
        import('../../pages/EvidencePage'),
        typeof document !== 'undefined' && document.fonts ? document.fonts.ready : Promise.resolve(),
      ]);

      // Respect minimum display window so branding is clearly seen
      const elapsed = Date.now() - startTime;
      const remaining = Math.max(0, minDisplayMs - elapsed);

      setTimeout(() => {
        if (active) {
          setIsSplitting(true);
        }
      }, remaining);
    }

    void loadAndTrigger();

    return () => {
      active = false;
    };
  }, [minDisplayMs]);

  const handleAnimationComplete = () => {
    if (isSplitting) {
      setIsMounted(false);
      onComplete?.();
    }
  };

  if (!isMounted) return null;

  // Constant, invariant split transition (always 1.5s smooth curve)
  const splitTransition = {
    duration: 1.5,
    ease: [0.65, 0, 0.35, 1] as const,
  };

  return (
    <div
      className="fixed inset-0 z-[99999] pointer-events-auto overflow-hidden select-none"
      aria-label="Hackathon Brand Loader"
      role="dialog"
      aria-modal="true"
    >
      <AnimatePresence onExitComplete={handleAnimationComplete}>
        {/* ================= LAYER 1: BACKGROUND CURTAINS (z-10) ================= */}
        {/* Left Curtain (Solid Green) */}
        <motion.div
          key="left-curtain"
          initial={{ x: '0%' }}
          animate={{ x: isSplitting ? '-102%' : '0%' }}
          transition={splitTransition}
          className="absolute top-0 left-0 w-[50.2vw] h-full bg-[#046735] will-change-transform transform-gpu z-10"
        />

        {/* Right Curtain (Solid Green) */}
        <motion.div
          key="right-curtain"
          initial={{ x: '0%' }}
          animate={{ x: isSplitting ? '102%' : '0%' }}
          transition={splitTransition}
          className="absolute top-0 left-[50vw] w-[50.2vw] h-full bg-[#046735] will-change-transform transform-gpu z-10"
        />

        {/* ================= LAYER 2: FOREGROUND BRAND ELEMENTS (z-30, Above all curtains) ================= */}
        {/* Left Moving Elements: Top-Left Brand Logo & "TASK" */}
        <motion.div
          key="left-elements"
          initial={{ x: '0%' }}
          animate={{ x: isSplitting ? '-102%' : '0%' }}
          transition={splitTransition}
          className="absolute top-0 left-0 w-[50vw] h-full pointer-events-none overflow-visible will-change-transform transform-gpu z-30"
        >
          {/* Top Left Brand Logo (2-47.svg) */}
          <div className="absolute top-6 left-6 sm:top-10 sm:left-10 md:top-12 md:left-12">
            <img
              src={brandMark}
              alt="Hackathon 2.47 Brand"
              className="h-9 sm:h-12 md:h-14 w-auto object-contain"
            />
          </div>

          {/* 100vw Centered Typography: "TASK" is visible, " 02" is invisible spacer */}
          <div className="absolute top-0 left-0 w-[100vw] h-full flex flex-col items-center justify-center gap-6 sm:gap-8">
            <div
              aria-hidden="true"
              className="w-36 sm:w-44 md:w-52 lg:w-56 max-w-[70vw] aspect-[291/255] invisible select-none"
            />
            <div className="flex items-center justify-center font-['Playfair_Display',serif] font-bold text-xl sm:text-3xl md:text-4xl lg:text-5xl tracking-[0.2em] uppercase text-[#FEE101] select-none whitespace-nowrap">
              <span>TASK</span>
              <span aria-hidden="true" className="invisible select-none">
                &nbsp;02
              </span>
            </div>
          </div>
        </motion.div>

        {/* Right Moving Elements: Center Hacker House Logo & "02" */}
        <motion.div
          key="right-elements"
          initial={{ x: '0%' }}
          animate={{ x: isSplitting ? '102%' : '0%' }}
          transition={splitTransition}
          onAnimationComplete={handleAnimationComplete}
          className="absolute top-0 left-[50vw] w-[50vw] h-full pointer-events-none overflow-visible will-change-transform transform-gpu z-30"
        >
          {/* 100vw Centered Container for Logo & "02" */}
          <div className="absolute top-0 left-[-50vw] w-[100vw] h-full flex flex-col items-center justify-center gap-6 sm:gap-8">
            {/* Middle Hackathon Logo (Hacker-house-v2.svg) - Centered at 50vw */}
            <img
              src={hackerHouseLogo}
              alt="Hacker House Goa"
              className="w-36 sm:w-44 md:w-52 lg:w-56 max-w-[70vw] h-auto object-contain"
            />

            {/* Centered Typography: "TASK " is invisible spacer, "02" is visible */}
            <div className="flex items-center justify-center font-['Playfair_Display',serif] font-bold text-xl sm:text-3xl md:text-4xl lg:text-5xl tracking-[0.2em] uppercase text-[#FEE101] select-none whitespace-nowrap">
              <span aria-hidden="true" className="invisible select-none">
                TASK&nbsp;
              </span>
              <span>02</span>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );
};




