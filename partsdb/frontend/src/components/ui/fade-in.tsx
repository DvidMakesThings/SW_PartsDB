import React, { ReactNode } from 'react';

interface FadeInProps {
  children: ReactNode;
  delay?: number;
  duration?: number;
  className?: string;
}

export const FadeIn: React.FC<FadeInProps> = ({ 
  children, 
  delay = 0, 
  duration = 300, 
  className = '' 
}) => {
  const style = {
    animation: `fadeIn ${duration}ms ease forwards`,
    animationDelay: `${delay}ms`,
    opacity: 0
  };

  return (
    <div style={style} className={className}>
      {children}
    </div>
  );
};