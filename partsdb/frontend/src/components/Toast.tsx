import React, { createContext, useContext, useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import { Check, X, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { cn } from '../lib/utils';

// Types
export type ToastType = 'success' | 'error' | 'info' | 'warning';

interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration: number;
}

interface ToastContextType {
  addToast: (message: string, type?: ToastType, duration?: number) => void;
  removeToast: (id: string) => void;
}

// Context
const ToastContext = createContext<ToastContextType | undefined>(undefined);

// Toast Item Component
interface ToastItemProps {
  toast: Toast;
  onClose: () => void;
}

const ToastItem = ({ toast, onClose }: ToastItemProps) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, toast.duration);

    return () => clearTimeout(timer);
  }, [toast.duration, onClose]);

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <Check className="h-4 w-4" />;
      case 'error':
        return <AlertCircle className="h-4 w-4" />;
      case 'warning':
        return <AlertTriangle className="h-4 w-4" />;
      case 'info':
      default:
        return <Info className="h-4 w-4" />;
    }
  };

  return (
    <div
      className={cn(
        "flex items-center justify-between p-3 mb-2 rounded-md shadow-md border border-[var(--border)] animate-fade-in",
        toast.type === 'success' && "bg-green-50 text-green-900 dark:bg-green-900/20 dark:text-green-300",
        toast.type === 'error' && "bg-red-50 text-red-900 dark:bg-red-900/20 dark:text-red-300",
        toast.type === 'warning' && "bg-yellow-50 text-yellow-900 dark:bg-yellow-900/20 dark:text-yellow-300",
        toast.type === 'info' && "bg-blue-50 text-blue-900 dark:bg-blue-900/20 dark:text-blue-300"
      )}
      role="alert"
    >
      <div className="flex items-center">
        <span className="mr-2">{getIcon()}</span>
        <p className="text-sm font-medium">{toast.message}</p>
      </div>
      <button 
        onClick={onClose}
        className="ml-4 p-1 hover:bg-[var(--surface)]/40 rounded-full"
        aria-label="Close"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
};

// Toast Container Component
interface ToastContainerProps {
  toasts: Toast[];
  removeToast: (id: string) => void;
}

const ToastContainer = ({ toasts, removeToast }: ToastContainerProps) => {
  return ReactDOM.createPortal(
    <div className="fixed top-4 right-4 z-50 max-w-xs w-full">
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          toast={toast}
          onClose={() => removeToast(toast.id)}
        />
      ))}
    </div>,
    document.body
  );
};

// Provider Component
export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = (message: string, type: ToastType = 'info', duration: number = 5000) => {
    const id = Math.random().toString(36).substring(2, 9);
    const newToast: Toast = { id, message, type, duration };
    
    // Replace any existing toast with the same message and type
    setToasts((prevToasts) => {
      const existingToastIndex = prevToasts.findIndex(
        (t) => t.message === message && t.type === type
      );
      
      if (existingToastIndex >= 0) {
        const newToasts = [...prevToasts];
        newToasts[existingToastIndex] = newToast;
        return newToasts;
      }
      
      return [...prevToasts, newToast];
    });
  };

  const removeToast = (id: string) => {
    setToasts((prevToasts) => prevToasts.filter((toast) => toast.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast, removeToast }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  );
};

// Hook
export const useToast = () => {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};