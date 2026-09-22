import { NavLink, Outlet } from "react-router-dom";

import { MeProvider } from "../auth/MeContext";
import { useAuth } from "../auth/AuthContext";
import { NAV } from "../nav";

export function Layout() {
  const { logout } = useAuth();
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-56 shrink-0 flex-col border-r border-gray-200 bg-gray-50">
        <div className="px-4 py-3 text-lg font-semibold">My Life</div>
        <nav className="flex flex-1 flex-col">
          {NAV.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === "/"}
              className={({ isActive }) =>
                "px-4 py-2 text-sm " +
                (isActive ? "bg-blue-100 font-medium text-blue-700" : "text-gray-700 hover:bg-gray-100")
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <button
          type="button"
          onClick={logout}
          className="border-t border-gray-200 px-4 py-3 text-left text-sm text-blue-600 hover:underline"
        >
          Sair
        </button>
      </aside>
      <MeProvider>
        <main className="flex-1 overflow-auto px-6 py-8">
          <Outlet />
        </main>
      </MeProvider>
    </div>
  );
}
