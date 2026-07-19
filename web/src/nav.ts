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
  { path: "/consent", label: "Consent" },
  { path: "/audit", label: "Audit" },
  { path: "/privacy", label: "Privacy" },
];
