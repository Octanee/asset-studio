import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router";

// Fonts are bundled locally (no requests to font CDNs; NFR-006, NFR-012).
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/archivo/600.css";
import "@fontsource/archivo/700.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./i18n";
import { makeQueryClient } from "./api/queries";
import { routes } from "./app/routes";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");

const queryClient = makeQueryClient();
const router = createBrowserRouter(routes);

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
