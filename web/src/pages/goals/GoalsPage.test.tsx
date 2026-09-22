import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  listGoals: vi.fn(),
  createGoal: vi.fn(),
  goalProgressAll: vi.fn(),
  recordMilestone: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { GoalsPage } from "./GoalsPage";

describe("GoalsPage", () => {
  beforeEach(() => {
    client.listGoals.mockResolvedValue([
      {
        goal_id: "g1",
        title: "Read 100 pages",
        metric: "reading_pages",
        target_value: 100,
        unit: "pages",
        currency: null,
        due_at: null,
        created_at: "x",
      },
    ]);
    client.goalProgressAll.mockResolvedValue([
      {
        goal_id: "g1",
        metric: "reading_pages",
        current_value: 40,
        target_value: 100,
        progress_ratio: 0.4,
        achieved: false,
        source: "milestone",
        evidence: [],
      },
    ]);
    client.createGoal.mockResolvedValue({ goal_id: "g2" });
    client.recordMilestone.mockResolvedValue({ event_id: "m1" });
  });

  it("shows progress joined with the goal title", async () => {
    render(<GoalsPage />);
    expect(await screen.findByText(/Read 100 pages/)).toBeInTheDocument();
    expect(screen.getByText(/40\/100 reading_pages \(40%\)/)).toBeInTheDocument();
  });

  it("creates a goal", async () => {
    render(<GoalsPage />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Run" } });
    fireEvent.change(screen.getByLabelText("Métrica"), { target: { value: "workout_minutes" } });
    fireEvent.change(screen.getByLabelText("Valor alvo"), { target: { value: "1000" } });
    fireEvent.change(screen.getByLabelText("Unidade"), { target: { value: "minutes" } });
    fireEvent.click(screen.getByText("Criar"));
    await waitFor(() =>
      expect(client.createGoal).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Run", metric: "workout_minutes", target_value: 1000 }),
      ),
    );
  });

  it("records a milestone", async () => {
    render(<GoalsPage />);
    fireEvent.change(screen.getByLabelText("Id da meta"), { target: { value: "g1" } });
    fireEvent.change(screen.getByLabelText("Valor"), { target: { value: "50" } });
    fireEvent.click(screen.getByText("Registrar"));
    await waitFor(() => expect(client.recordMilestone).toHaveBeenCalledWith("g1", 50, null));
  });
});
