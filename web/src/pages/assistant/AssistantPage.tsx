import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import type { Answer, Insight } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

type AssistantApi = Pick<ApiClient, "assistantQuery" | "runAlerts" | "listInsights">;

function InsightItem({ insight }: { insight: Insight }) {
  return (
    <li className="rounded border border-gray-200 px-3 py-2 text-sm">
      <span className="font-medium">{insight.claim}</span>
      <span className="text-gray-500">
        {" · conf "}
        {insight.confidence.toFixed(2)} · {insight.evidence.length} evidence
      </span>
    </li>
  );
}

export function AssistantPage() {
  const client = useApiClient();
  return (
    <>
      <Ask client={client} />
      <Alerts client={client} />
      <Insights client={client} />
    </>
  );
}

function Ask({ client }: { client: AssistantApi }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setAnswer(await client.assistantQuery(question.trim()));
    } catch {
      setError("Could not answer.");
    }
  }

  return (
    <Section title="Ask">
      <form onSubmit={submit} className="mb-3 flex items-end gap-2">
        <Field label="Question">
          <TextInput value={question} onChange={(e) => setQuestion(e.target.value)} required />
        </Field>
        <Button type="submit">Ask</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {answer && (
        <div className="rounded border border-gray-200 px-3 py-2 text-sm">
          <p className={answer.grounded ? "text-gray-900" : "text-gray-500"}>{answer.answer}</p>
          <p className="mt-1 text-xs text-gray-500">
            {answer.grounded ? "grounded" : "refused"} · tools: {answer.tools_used.join(", ") || "—"}{" "}
            · {answer.evidence_count} evidence
          </p>
        </div>
      )}
    </Section>
  );
}

function Alerts({ client }: { client: AssistantApi }) {
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    try {
      setInsights(await client.runAlerts());
    } catch {
      setError("Could not run alerts.");
    }
  }

  return (
    <Section title="Alerts" actions={<Button onClick={run}>Run alerts</Button>}>
      {error && <ErrorText>{error}</ErrorText>}
      {insights && insights.length === 0 && <p className="text-sm text-gray-500">No alerts fired.</p>}
      <ul className="flex flex-col gap-2">
        {(insights ?? []).map((insight) => (
          <InsightItem key={insight.insight_id} insight={insight} />
        ))}
      </ul>
    </Section>
  );
}

function Insights({ client }: { client: AssistantApi }) {
  const insights = useAsync(() => client.listInsights(), [client]);
  return (
    <Section title="Insights" actions={<Button onClick={() => insights.run()}>Refresh</Button>}>
      {insights.status === "error" && <ErrorText>Could not load insights.</ErrorText>}
      {insights.status === "ready" && insights.data?.length === 0 && (
        <p className="text-sm text-gray-500">No insights yet.</p>
      )}
      <ul className="flex flex-col gap-2">
        {(insights.data ?? []).map((insight) => (
          <InsightItem key={insight.insight_id} insight={insight} />
        ))}
      </ul>
    </Section>
  );
}
