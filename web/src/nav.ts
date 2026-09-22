export interface NavItem {
  path: string;
  label: string;
}

/**
 * Sidebar navigation registry. Feature tasks (T10.2–T10.9) append their entries
 * here as their pages land.
 */
export const NAV: NavItem[] = [
  { path: "/", label: "Painel" },
  { path: "/capture", label: "Registrar" },
  { path: "/finance", label: "Finanças" },
  { path: "/health", label: "Saúde" },
  { path: "/goals", label: "Metas" },
  { path: "/knowledge", label: "Conhecimento" },
  { path: "/assistant", label: "Assistente" },
  { path: "/forecast", label: "Previsões" },
  { path: "/consent", label: "Consentimentos" },
  { path: "/audit", label: "Auditoria" },
  { path: "/privacy", label: "Privacidade" },
];
