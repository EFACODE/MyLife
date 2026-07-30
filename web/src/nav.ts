export interface NavItem {
  path: string;
  label: string;
}

/**
 * Sidebar navigation registry. Feature tasks (T10.2–T10.9) append their entries
 * here as their pages land.
 */
export const NAV: NavItem[] = [
  { path: "/", label: "Dashboard" },
  { path: "/capture", label: "Capture" },
  { path: "/finance", label: "Finance" },
  { path: "/health", label: "Health" },
  { path: "/goals", label: "Goals" },
  { path: "/knowledge", label: "Knowledge" },
  { path: "/assistant", label: "Assistant" },
  { path: "/forecast", label: "Forecast" },
  { path: "/consent", label: "Consent" },
  { path: "/audit", label: "Audit" },
  { path: "/privacy", label: "Privacy" },
];
