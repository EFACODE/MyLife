import { useState, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import type { Calibration } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

type ForecastApi = Pick<
  ApiClient,
  "listForecasts" | "runForecasts" | "simulateForecast" | "recordOutcome" | "calibration"
>;

export function ForecastPage() {
  const client = useApiClient();
  const forecasts = useAsync(() => client.listForecasts(), [client]);
  const [horizon, setHorizon] = useState("30");
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    try {
      await client.runForecasts(Number(horizon));
      await forecasts.run();
    } catch {
      setError("Não foi possível executar as previsões.");
    }
  }

  return (
    <>
      <Section
        title="Previsões"
        actions={
          <span className="flex items-end gap-2">
            <Field label="Horizonte (dias)">
              <TextInput
                type="number"
                value={horizon}
                onChange={(e) => setHorizon(e.target.value)}
                className="w-24"
              />
            </Field>
            <Button onClick={run}>Executar modelos</Button>
          </span>
        }
      >
        {error && <ErrorText>{error}</ErrorText>}
        {forecasts.status === "ready" && forecasts.data?.length === 0 && (
          <p className="text-sm text-gray-500">Nenhuma previsão ainda — execute os modelos.</p>
        )}
        <ul className="flex flex-col gap-2 text-sm">
          {(forecasts.data ?? []).map((forecast) => (
            <li key={forecast.forecast_id} className="rounded border border-gray-200 px-3 py-2">
              <span className="font-medium">
                {forecast.metric} ({forecast.unit})
              </span>
              <span className="text-gray-500">
                {" · conf "}
                {forecast.confidence.toFixed(2)} · {forecast.points.length} pontos ·{" "}
                {forecast.assumptions.map((a) => a.name).join(", ")}
              </span>
              <div className="font-mono text-xs text-gray-400">{forecast.forecast_id}</div>
            </li>
          ))}
        </ul>
      </Section>
      <Simulate client={client} onDone={() => forecasts.run()} />
      <RecordOutcome client={client} />
      <CalibrationView client={client} />
    </>
  );
}

function Simulate({ client, onDone }: { client: ForecastApi; onDone: () => void }) {
  const [forecastId, setForecastId] = useState("");
  const [scale, setScale] = useState("1.2");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await client.simulateForecast(forecastId.trim(), Number(scale), label.trim() || undefined);
      onDone();
    } catch {
      setError("Não foi possível simular (escala ≠ 1 ou é necessário um override).");
    }
  }

  return (
    <Section title="Cenário hipotético">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Id da previsão">
          <TextInput value={forecastId} onChange={(e) => setForecastId(e.target.value)} required />
        </Field>
        <Field label="Escala">
          <TextInput
            type="number"
            step="0.1"
            value={scale}
            onChange={(e) => setScale(e.target.value)}
            required
          />
        </Field>
        <Field label="Rótulo">
          <TextInput value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
        <Button type="submit">Simular</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
    </Section>
  );
}

function RecordOutcome({ client }: { client: ForecastApi }) {
  const [forecastId, setForecastId] = useState("");
  const [value, setValue] = useState("");
  const [observedAt, setObservedAt] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("idle");
    try {
      await client.recordOutcome(
        forecastId.trim(),
        Number(value),
        new Date(observedAt).toISOString(),
      );
      setValue("");
      setStatus("ok");
    } catch {
      setStatus("error");
    }
  }

  return (
    <Section title="Registrar resultado">
      <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
        <Field label="Id da previsão">
          <TextInput value={forecastId} onChange={(e) => setForecastId(e.target.value)} required />
        </Field>
        <Field label="Valor observado">
          <TextInput
            type="number"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            required
          />
        </Field>
        <Field label="Observado em">
          <TextInput
            type="datetime-local"
            value={observedAt}
            onChange={(e) => setObservedAt(e.target.value)}
            required
          />
        </Field>
        <Button type="submit">Registrar</Button>
      </form>
      {status === "ok" && <p className="mt-2 text-sm text-green-700">Registrado.</p>}
      {status === "error" && <ErrorText>Não foi possível registrar o resultado.</ErrorText>}
    </Section>
  );
}

function CalibrationView({ client }: { client: ForecastApi }) {
  const [calibration, setCalibration] = useState<Calibration | null>(null);

  async function load() {
    setCalibration(await client.calibration());
  }

  return (
    <Section title="Calibração" actions={<Button onClick={load}>Carregar</Button>}>
      {calibration ? (
        <p className="text-sm">
          {calibration.total} resultados · {calibration.within_interval} dentro do intervalo · taxa
          de acerto {(calibration.hit_rate * 100).toFixed(0)}% · erro absoluto médio{" "}
          {calibration.mean_abs_error}
        </p>
      ) : (
        <p className="text-sm text-gray-500">
          Carregue para ver como suas previsões se saíram frente aos resultados registrados.
        </p>
      )}
    </Section>
  );
}
