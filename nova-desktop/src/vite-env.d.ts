/// <reference types="vite/client" />

interface ImportMetaEnv {
	readonly VITE_NOVA_API_URL?: string;
	readonly VITE_CAT_MODEL_URL?: string;
}

interface ImportMeta {
	readonly env: ImportMetaEnv;
}
