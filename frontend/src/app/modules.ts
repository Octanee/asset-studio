/** The 13 modules of the navigation rail, in the approved order ([[Navigation]]).
 * Icon paths are the 20×20 stroke icons from the approved "Navigation rail" artboard. */
export interface Module {
  id: ModuleId;
  path: string;
  icon: string;
  /** Shown in the phone bottom bar (< 720 px). */
  phone?: boolean;
  /** Work package that builds the screen; the shell shows a placeholder until then. */
  wp: string;
}

export type ModuleId =
  | "dashboard"
  | "generate"
  | "queue"
  | "library"
  | "review"
  | "styles"
  | "references"
  | "poses"
  | "training"
  | "models"
  | "workflows"
  | "publish"
  | "settings";

export const MODULES: readonly Module[] = [
  {
    id: "dashboard",
    path: "/",
    phone: true,
    wp: "WP-16",
    icon: "M3 3h6v6H3zM11 3h6v4h-6zM11 9h6v8h-6zM3 11h6v6H3z",
  },
  {
    id: "generate",
    path: "/generate",
    wp: "WP-08",
    icon: "M10 2v4M10 14v4M2 10h4M14 10h4M4.5 4.5l2.5 2.5M13 13l2.5 2.5M15.5 4.5L13 7M7 13l-2.5 2.5",
  },
  { id: "queue", path: "/queue", phone: true, wp: "WP-08", icon: "M3 5h14M3 10h14M3 15h9" },
  {
    id: "library",
    path: "/library",
    phone: true,
    wp: "WP-10",
    icon: "M3 3h6v6H3zM11 3h6v6h-6zM3 11h6v6H3zM11 11h6v6h-6z",
  },
  { id: "review", path: "/review", phone: true, wp: "WP-10", icon: "M4 10l4 4 8-8" },
  {
    id: "styles",
    path: "/styles",
    wp: "WP-07",
    icon: "M10 3a7 7 0 1 0 0 14c1 0 1.5-.8 1-1.7-.5-1 .2-2.3 1.3-2.3H15a2 2 0 0 0 2-2 7 7 0 0 0-7-8zM6.5 9.5h.01M9 6.5h.01M13 7.5h.01",
  },
  {
    id: "references",
    path: "/references",
    wp: "WP-07",
    icon: "M3 5h14v10H3zM3 13l4-4 3 3 2-2 5 5",
  },
  { id: "poses", path: "/poses", wp: "WP-07", icon: "M10 4.5h.01M10 7v5M6 9l4-2 4 2M8 17l2-5 2 5" },
  { id: "training", path: "/training", wp: "WP-13", icon: "M3 15l4-4 3 3 7-7M12 7h5v5" },
  {
    id: "models",
    path: "/models",
    wp: "WP-12",
    icon: "M10 2l7 4v8l-7 4-7-4V6zM3 6l7 4 7-4M10 10v8",
  },
  {
    id: "workflows",
    path: "/workflows",
    wp: "WP-08",
    icon: "M4 4h4v4H4zM12 12h4v4h-4zM8 6h3a2 2 0 0 1 2 2v4",
  },
  { id: "publish", path: "/publish", wp: "WP-11", icon: "M10 13V3M6 7l4-4 4 4M4 13v4h12v-4" },
  {
    id: "settings",
    path: "/settings",
    wp: "WP-16",
    icon: "M10 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM10 2v2M10 16v2M2 10h2M16 10h2M4.3 4.3l1.4 1.4M14.3 14.3l1.4 1.4M15.7 4.3l-1.4 1.4M5.7 14.3l-1.4 1.4",
  },
];

export function moduleFor(pathname: string): Module | undefined {
  if (pathname === "/") return MODULES[0];
  return MODULES.find((m) => m.path !== "/" && pathname.startsWith(m.path));
}
