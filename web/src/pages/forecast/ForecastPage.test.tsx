import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  listForecasts: vi.fn(),
  runForecasts: vi.fn(),
  simulateForecast: vi.fn(),
  recordOutcome: vi.fn(),
  calibration: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { ForecastPage } from "./ForecastPage";

const forecast = {
  forecast_id: "f1",
  metric: "cash_flow",
  unit: "BRL_minor",
  horizon_days: 30,
  points: [{ at: "x", value: -1000, lower: -1500, upper: -500 }],
  assumptions: [{ name: "net_flow_rate", value: "v", basis: "b" }],
  confidence: 0.5,
  limitations: "l",
  method: "cash-flow-ma-v1",
  evidence: ["e1"],
  generated_at: "y",
};

describe("ForecastPage", () => {
  beforeEach(() => {
    client.listForecasts.mockResolvedValue([forecast]);
    client.runForecasts.mockResolvedValue([forecast]);
    client.simulateForecast.mockResolvedValue({ ...forecast, forecast_id: "f2" });
    client.recordOutcome.mockResolvedValue({ outcome_id: "o1" });
    client.calibration.mockResolvedValue({
      total: 1,
      within_interval: 1,
      hit_rate: 1,
      mean_abs_error: 5000,
      records: [],
    });
  });

  it("lists forecasts and runs the models", async () => {
    render(<ForecastPage />);
    expect(await screen.findByText(/cash_flow \(BRL_minor\)/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("Executar modelos"));
    await waitFor(() => expect(client.runForecasts).toHaveBeenCalledWith(30));
  });

  it("simulates a what-if scenario", async () => {
    render(<ForecastPage />);
    fireEvent.change(screen.getAllByLabelText("Id da previsão")[0], { target: { value: "f1" } });
    fireEvent.click(screen.getByText("Simular"));
    await waitFor(() =>
      expect(client.simulateForecast).toHaveBeenCalledWith("f1", 1.2, undefined),
    );
  });

  it("loads calibration", async () => {
    render(<ForecastPage />);
    fireEvent.click(screen.getByText("Carregar"));
    expect(
      await screen.findByText(/taxa de acerto 100% · erro absoluto médio 5000/),
    ).toBeInTheDocument();
  });
});
