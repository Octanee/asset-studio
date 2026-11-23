import { create } from "zustand";
import { createJSONStorage, persist, type StateStorage } from "zustand/middleware";

export type Theme = "dark" | "light";
export type Language = "pl" | "en";

/** UI preferences kept in this browser only (ADR-003: Zustand for UI state). */
interface UiState {
  theme: Theme;
  language: Language;
  projectId: string | null;
  setTheme: (theme: Theme) => void;
  setLanguage: (language: Language) => void;
  setProjectId: (projectId: string | null) => void;
}

/** Storage can be blocked (private mode, policies); the app then works without remembering. */
const safeStorage: StateStorage = {
  getItem: (name) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name, value) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      /* not persisted */
    }
  },
  removeItem: (name) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      /* nothing to remove */
    }
  },
};

export function browserLanguage(): Language {
  const lang = typeof navigator === "undefined" ? "" : navigator.language;
  return lang.toLowerCase().startsWith("pl") ? "pl" : "en";
}

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      theme: "dark",
      language: browserLanguage(),
      projectId: null,
      setTheme: (theme) => set({ theme }),
      setLanguage: (language) => set({ language }),
      setProjectId: (projectId) => set({ projectId }),
    }),
    {
      name: "asset-studio.ui",
      version: 1,
      storage: createJSONStorage(() => safeStorage),
      partialize: ({ theme, language, projectId }) => ({ theme, language, projectId }),
    },
  ),
);
