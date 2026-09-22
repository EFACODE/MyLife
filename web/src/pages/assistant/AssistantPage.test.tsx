import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  assistantQuery: vi.fn(),
  runAlerts: vi.fn(),
  listInsights: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { AssistantPage } from "./AssistantPage";

const insight = {
  insight_id: "i1",
  claim: "You overspent on food.",
  rationale: "r",
  confidence: 0.8,
  limitations: "l",
  next_safe_action: null,
  generator: "alerts-v1",
  evidence: ["e1", "e2"],
  generated_at: "x",
};

describe("AssistantPage", () => {
  beforeEach(() => {
    client.assistantQuery.mockResolvedValue({
      grounded: true,
      answer: "Found 1 record.",
      insight,
      tools_used: ["timeline-keyword"],
      evidence_count: 1,
    });
    client.runAlerts.mockResolvedValue([insight]);
    client.listInsights.mockResolvedValue([insight]);
  });

  it("asks a question and renders the grounded answer", async () => {
    render(<AssistantPage />);
    fireEvent.change(screen.getByLabelText("Pergunta"), { target: { value: "how much on food?" } });
    fireEvent.click(screen.getByRole("button", { name: "Perguntar" }));
    expect(await screen.findByText("Found 1 record.")).toBeInTheDocument();
    expect(client.assistantQuery).toHaveBeenCalledWith("how much on food?");
  });

  it("runs alerts and lists the fired insights", async () => {
    render(<AssistantPage />);
    fireEvent.click(screen.getByText("Executar alertas"));
    expect(await screen.findAllByText(/You overspent on food\./)).not.toHaveLength(0);
  });
});
