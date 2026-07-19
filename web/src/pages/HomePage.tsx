import { Header } from "../components/Header";

export function HomePage() {
  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-2xl px-4 py-8">
        <h1 className="text-xl font-semibold">Welcome back</h1>
        <p className="mt-2 text-sm text-gray-600">
          Your timeline and daily briefing will appear here.
        </p>
      </main>
    </div>
  );
}
