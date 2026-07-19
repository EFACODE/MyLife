import { useMe } from "../auth/MeContext";
import { useApiClient } from "../api/useApiClient";
import { Briefing } from "../components/Briefing";
import { ErrorText } from "../components/ui/ErrorText";
import { Timeline } from "../components/Timeline";

export function HomePage() {
  const client = useApiClient();
  const { user, status } = useMe();

  if (status === "loading" || status === "idle")
    return <p className="text-sm text-gray-500">Loading…</p>;
  if (status === "error" || !user) return <ErrorText>Could not load your account.</ErrorText>;

  return (
    <>
      <h1 className="mb-6 text-xl font-semibold">Welcome, {user.display_name}</h1>
      <Briefing client={client} userId={user.user_id} />
      <Timeline client={client} userId={user.user_id} />
    </>
  );
}
