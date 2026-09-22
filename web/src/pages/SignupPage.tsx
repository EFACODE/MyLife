import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ApiError, ApiClient, apiBaseUrl } from "../api/client";
import { useAuth } from "../auth/AuthContext";

const client = new ApiClient(apiBaseUrl, () => null);

export function SignupPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await client.registerUser({ email, display_name: displayName, password });
      const token = await client.login(email, password);
      login(token);
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("Já existe uma conta com este e-mail.");
      } else if (err instanceof ApiError && err.status === 422) {
        setError("Verifique seu e-mail e use uma senha com pelo menos 8 caracteres.");
      } else {
        setError("Não foi possível cadastrar. Tente novamente.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto mt-24 max-w-sm px-4">
      <h1 className="mb-6 text-2xl font-semibold">Crie sua conta My Life</h1>
      <form onSubmit={onSubmit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Nome
          <input
            type="text"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          E-mail
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-gray-300 px-2 py-1"
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Senha
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            minLength={8}
            className="rounded border border-gray-300 px-2 py-1"
            required
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="mt-2 rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Cadastrar
        </button>
      </form>
      <p className="mt-4 text-sm text-gray-600">
        Já tem uma conta?{" "}
        <Link to="/login" className="text-blue-600 underline">
          Entrar
        </Link>
      </p>
    </main>
  );
}
