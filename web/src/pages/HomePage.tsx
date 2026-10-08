import { useState } from "react";

import { useMe } from "../auth/MeContext";
import { useApiClient } from "../api/useApiClient";
import { Briefing } from "../components/Briefing";
import { ErrorText } from "../components/ui/ErrorText";
import { Timeline } from "../components/Timeline";
import { CaptureEventForm } from "./timeline/CaptureEventForm";

export function HomePage() {
  const client = useApiClient();
  const { user, status } = useMe();
  // Bumped after a manual capture so the timeline below reloads.
  const [timelineKey, setTimelineKey] = useState(0);

  if (status === "loading" || status === "idle")
    return <p className="text-sm text-gray-500">Carregando…</p>;
  if (status === "error" || !user) return <ErrorText>Não foi possível carregar sua conta.</ErrorText>;

  return (
    <>
      <h1 className="mb-6 text-xl font-semibold">Bem-vindo(a), {user.display_name}</h1>
      <Briefing client={client} userId={user.user_id} />
      <CaptureEventForm
        client={client}
        userId={user.user_id}
        onCaptured={() => setTimelineKey((key) => key + 1)}
      />
      <Timeline key={timelineKey} client={client} userId={user.user_id} />
    </>
  );
}
