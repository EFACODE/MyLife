import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { ApiClient, apiBaseUrl } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const client = new ApiClient(apiBaseUrl, () => null);

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const token = await client.login(email, password);
      login(token);
      navigate("/");
    } catch {
      setError("Invalid email or password.");
    }
  }

  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-6 text-2xl font-semibold">Sign in to My Life</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
            required
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          className="mt-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white"
        >
          Sign in
        </button>
      </form>
    </main>
  );
}
