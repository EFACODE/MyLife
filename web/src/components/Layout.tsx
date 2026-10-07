import { LogOut, Menu, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { MeProvider } from "../auth/MeContext";
import { useAuth } from "../auth/AuthContext";
import { NAV, navItemFor } from "../nav";

/**
 * App shell. On desktop (`md` and up) the navigation is a sticky sidebar; on
 * phones it collapses into a top bar with a hamburger that opens an off-canvas
 * drawer, so the page content gets the full screen width.
 */
export function Layout() {
  const { logout } = useAuth();
  const { pathname } = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const current = navItemFor(pathname);

  // Navigating closes the drawer and brings the new screen to its top.
  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo?.(0, 0);
  }, [pathname]);

  // While the drawer is open: Escape closes it and the page behind it does not scroll.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [menuOpen]);

  return (
    <div className="min-h-screen bg-white md:flex">
      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b border-gray-200 bg-white/95 px-2 backdrop-blur pt-[env(safe-area-inset-top)] md:hidden">
        <button
          ref={menuButtonRef}
          type="button"
          aria-label="Abrir menu"
          aria-expanded={menuOpen}
          aria-controls="app-nav"
          onClick={() => setMenuOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-gray-700 hover:bg-gray-100 active:bg-gray-200"
        >
          <Menu className="h-6 w-6" />
        </button>
        <span className="truncate text-base font-semibold text-gray-900">
          {current?.label ?? "My Life"}
        </span>
      </header>

      {/* Backdrop behind the mobile drawer */}
      {menuOpen && (
        <div
          aria-hidden="true"
          onClick={() => setMenuOpen(false)}
          className="fixed inset-0 z-40 bg-gray-900/40 md:hidden"
        />
      )}

      <aside
        id="app-nav"
        className={
          "fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col border-r border-gray-200 bg-white shadow-xl transition-[transform,visibility] duration-200 ease-out " +
          "md:sticky md:top-0 md:z-auto md:h-screen md:w-56 md:max-w-none md:shrink-0 md:visible md:translate-x-0 md:bg-gray-50 md:shadow-none " +
          // `invisible` keeps the closed drawer out of the tab order on phones.
          (menuOpen ? "visible translate-x-0" : "invisible -translate-x-full")
        }
      >
        <div className="flex h-14 items-center justify-between px-4 pt-[env(safe-area-inset-top)] md:h-auto md:py-3">
          <span className="text-lg font-semibold">My Life</span>
          <button
            type="button"
            aria-label="Fechar menu"
            onClick={() => setMenuOpen(false)}
            className="-mr-2 flex h-11 w-11 items-center justify-center rounded-lg text-gray-500 hover:bg-gray-100 md:hidden"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <nav aria-label="Principal" className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-2 pb-2">
          {NAV.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.path}
                to={item.path}
                end={item.path === "/"}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) =>
                  "flex items-center gap-3 rounded-lg px-3 py-3 text-base md:py-2 md:text-sm " +
                  (isActive
                    ? "bg-blue-100 font-medium text-blue-700"
                    : "text-gray-700 hover:bg-gray-100 active:bg-gray-200")
                }
              >
                <Icon className="h-5 w-5 shrink-0 md:h-4 md:w-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
        <button
          type="button"
          onClick={logout}
          className="flex items-center gap-3 border-t border-gray-200 px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))] text-left text-base text-blue-600 hover:bg-gray-100 md:py-3 md:text-sm"
        >
          <LogOut className="h-5 w-5 md:h-4 md:w-4" />
          Sair
        </button>
      </aside>

      <MeProvider>
        <main className="min-w-0 flex-1 bg-white px-4 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] sm:px-6 md:py-8">
          <Outlet />
        </main>
      </MeProvider>
    </div>
  );
}
