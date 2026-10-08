import {
  Bot,
  Brain,
  FileClock,
  HeartPulse,
  LayoutDashboard,
  LineChart,
  ShieldCheck,
  Target,
  UserCheck,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  path: string;
  label: string;
  icon: LucideIcon;
}

/**
 * Sidebar navigation registry. Feature tasks (T10.2–T10.9) append their entries
 * here as their pages land.
 */
export const NAV: NavItem[] = [
  { path: "/finance", label: "Finanças", icon: Wallet },
  { path: "/health", label: "Saúde", icon: HeartPulse },
  { path: "/goals", label: "Metas", icon: Target },
  { path: "/knowledge", label: "Conhecimento", icon: Brain },
  { path: "/assistant", label: "Assistente", icon: Bot },
  { path: "/forecast", label: "Previsões", icon: LineChart },
  { path: "/consent", label: "Consentimentos", icon: UserCheck },
  { path: "/audit", label: "Auditoria", icon: FileClock },
  { path: "/privacy", label: "Privacidade", icon: ShieldCheck },
  { path: "/", label: "Painel", icon: LayoutDashboard },
];

/** The nav entry that owns `pathname` (exact match for "/", prefix otherwise). */
export function navItemFor(pathname: string): NavItem | undefined {
  return NAV.find((item) =>
    item.path === "/" ? pathname === "/" : pathname === item.path || pathname.startsWith(item.path + "/"),
  );
}
