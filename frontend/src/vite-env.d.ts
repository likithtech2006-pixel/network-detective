/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend origin when it is hosted separately, e.g. https://network-detective-api.onrender.com */
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
