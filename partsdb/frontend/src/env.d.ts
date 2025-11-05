/// <reference types="vite/client" />

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string;
  readonly PROD: boolean;
  readonly DEV: boolean;
  // more env variables...
}

interface Window {
  showError?: (title: string, error: Error | string) => void;
}