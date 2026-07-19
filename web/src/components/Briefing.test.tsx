import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Briefing as BriefingModel } from "../api/types";
import { Briefing, type BriefingApi } from "./Briefing";

const briefing: BriefingModel = {
  user_id: "u",
  generated_at: "2026-07-19T12:00:00Z",
  window_hours: 24,
  event_count: 2,
  lines: [{ kind: "spend", summary: "You spent BRL 45.99 on food.", evidence: ["e1", "e2"] }],
};

describe("Briefing", () => {
  it("renders the briefing lines after delivering", async () => {
    const deliverBriefing = vi.fn().mockResolvedValue(briefing);
    const client: BriefingApi = { deliverBriefing };
    render(<Briefing client={client} userId="u" />);

    fireEvent.click(screen.getByText("Deliver briefing"));

    expect(await screen.findByText(/You spent BRL 45.99 on food\./)).toBeInTheDocument();
    expect(screen.getByText(/2 evidence/)).toBeInTheDocument();
    expect(deliverBriefing).toHaveBeenCalledWith("u");
  });

  it("shows an error state when delivery fails", async () => {
    const deliverBriefing = vi.fn().mockRejectedValue(new Error("boom"));
    const client: BriefingApi = { deliverBriefing };
    render(<Briefing client={client} userId="u" />);

    fireEvent.click(screen.getByText("Deliver briefing"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not deliver the briefing.");
  });
});
