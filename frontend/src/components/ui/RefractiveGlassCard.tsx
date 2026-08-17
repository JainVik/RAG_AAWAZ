import React from 'react';

export interface RefractiveGlassCardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'default' | 'primary' | 'synthesis';
  as?: 'div' | 'article' | 'section' | 'aside';
  children?: React.ReactNode;
  className?: string;
}

export const RefractiveGlassCard: React.FC<RefractiveGlassCardProps> = ({
  variant = 'default',
  as: Component = 'div',
  children,
  className = '',
  ...rest
}) => {
  const variantClass =
    variant === 'primary'
      ? 'refractive-glass-card-primary'
      : variant === 'synthesis'
        ? 'refractive-glass-card-synthesis'
        : '';

  return (
    <Component
      className={`refractive-glass-card ${variantClass} ${className}`.trim()}
      {...rest}
    >
      {children}
    </Component>
  );
};
