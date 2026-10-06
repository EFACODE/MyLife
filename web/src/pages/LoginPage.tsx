import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

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
      setError("E-mail ou senha inválidos.");
    }
  }

  return (
    <main className="mx-auto mt-12 max-w-sm px-4 sm:mt-24">
      <h1 className="mb-6 text-2xl font-semibold">Entrar no My Life</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          E-mail
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-base sm:px-2 sm:py-1 sm:text-sm"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Senha
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-gray-300 px-3 py-2 text-base sm:px-2 sm:py-1 sm:text-sm"
            required
          />
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          className="mt-2 rounded bg-blue-600 px-3 py-3 text-base font-medium text-white sm:py-2 sm:text-sm"
        >
          Entrar
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-600">
        Ainda não tem uma conta?{" "}
        <Link to="/signup" className="text-blue-600 underline">
          Cadastre-se
        </Link>
      </p>
    </main>
  );
}
