import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// Fonts are bundled locally (no requests to font CDNs; NFR-006, NFR-012).
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/archivo/700.css";
import "./styles/tokens.css";
import "./i18n";
import { App } from "./app/App";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
