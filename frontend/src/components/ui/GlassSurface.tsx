import React, { useId, useMemo } from 'react';
import './GlassSurface.css';

export interface GlassSurfaceProps {
  children?: React.ReactNode;
  width?: number | string;
  height?: number | string;
  borderRadius?: number | string;
  blur?: number;
  displace?: number;
  distortionScale?: number;
  redOffset?: number;
  greenOffset?: number;
  blueOffset?: number;
  mixBlendMode?: string;
  className?: string;
  style?: React.CSSProperties;
  onClick?: (e: React.MouseEvent<HTMLDivElement>) => void;
}

export const GlassSurface: React.FC<GlassSurfaceProps> = ({
  children,
  width,
  height,
  borderRadius = 16,
  blur = 16,
  displace = 8,
  distortionScale = 20,
  redOffset = 2,
  greenOffset = 4,
  blueOffset = 6,
  mixBlendMode = 'normal',
  className = '',
  style = {},
  onClick,
}) => {
  const uniqueId = useId().replace(/:/g, '_');
  const filterId = `glass-filter-${uniqueId}`;

  const containerStyle = useMemo<React.CSSProperties>(() => {
    return {
      width: width !== undefined ? (typeof width === 'number' ? `${width}px` : width) : undefined,
      height: height !== undefined ? (typeof height === 'number' ? `${height}px` : height) : undefined,
      borderRadius: typeof borderRadius === 'number' ? `${borderRadius}px` : borderRadius,
      ...style,
    };
  }, [width, height, borderRadius, style]);

  return (
    <div
      onClick={onClick}
      className={`glass-surface glass-surface--fallback ${className}`.trim()}
      style={containerStyle}
    >
      <svg className="glass-surface-svg" aria-hidden="true">
        <defs>
          <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
            <feTurbulence
              type="fractalNoise"
              baseFrequency={0.04 * (distortionScale / 20)}
              numOctaves={3}
              result="noise"
            />
            <feDisplacementMap
              in="SourceGraphic"
              in2="noise"
              scale={displace}
              xChannelSelector="R"
              yChannelSelector="G"
              result="displaced"
            />
            <feGaussianBlur in="displaced" stdDeviation={blur * 0.05} result="blurred" />
            <feColorMatrix
              in="blurred"
              type="matrix"
              values={`
                1 0 0 0 ${redOffset * 0.01}
                0 1 0 0 ${greenOffset * 0.01}
                0 0 1 0 ${blueOffset * 0.01}
                0 0 0 1 0
              `}
              result="colored"
            />
            <feBlend in="SourceGraphic" in2="colored" mode={mixBlendMode as any} />
          </filter>
        </defs>
      </svg>
      <div className="glass-surface-content">{children}</div>
    </div>
  );
};

export default GlassSurface;
