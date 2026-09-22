import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";

const client = vi.hoisted(() => ({
  listSleep: vi.fn(),
  recordSleep: vi.fn(),
  listWorkouts: vi.fn(),
  recordWorkout: vi.fn(),
  importHealth: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { HealthPage } from "./HealthPage";

describe("HealthPage", () => {
  beforeEach(() => {
    client.listSleep.mockResolvedValue([
      { event_id: "s1", occurred_at: "2026-07-19T00:00:00Z", duration_minutes: 420, quality: "ok" },
    ]);
    client.recordSleep.mockResolvedValue({ event_id: "s2" });
    client.listWorkouts.mockResolvedValue([]);
    client.recordWorkout.mockResolvedValue({ event_id: "w1" });
    client.importHealth.mockRejectedValue(new ApiError(403, "forbidden"));
  });

  it("lists sleep and records a workout", async () => {
    render(<HealthPage />);
    expect(await screen.findByText(/420 min/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Atividade"), { target: { value: "run" } });
    const minutes = screen.getAllByLabelText("Duração (minutos)");
    fireEvent.change(minutes[minutes.length - 1], { target: { value: "30" } });
    fireEvent.click(screen.getByText("Registrar treino"));
    await waitFor(() =>
      expect(client.recordWorkout).toHaveBeenCalledWith(
        expect.objectContaining({ activity: "run", duration_minutes: 30 }),
      ),
    );
  });

  it("surfaces a 403 health import as a consent hint", async () => {
    render(<HealthPage />);
    fireEvent.change(screen.getByLabelText("CSV"), { target: { value: "a,b" } });
    fireEvent.click(screen.getByText("Importar"));
    expect(await screen.findByText(/Conceda o consentimento de 'saúde' primeiro/)).toBeInTheDocument();
  });
});
