import { useAuth } from "../auth/AuthContext";

export function Header() {
  const { logout } = useAuth();
  return (
    <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3">
      <span className="font-semibold">My Life</span>
      <button
        type="button"
        onClick={logout}
        className="text-sm text-blue-600 hover:underline"
      >
        Log out
      </button>
    </header>
  );
}
