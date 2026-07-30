import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { TimelineEvent, TimelinePage } from "../api/types";
import { Timeline, type TimelineApi } from "./Timeline";

function event(overrides: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    event_id: "e1",
    user_id: "u",
    event_type: "finance.expense_created",
    occurred_at: "2026-07-19T12:00:00Z",
    recorded_at: "2026-07-19T12:00:00Z",
    schema_version: 1,
    source: "manual",
    correlation_id: "c",
    raw_record_id: null,
    corrects_event_id: null,
    payload: {},
    ...overrides,
  };
}

function page(items: TimelineEvent[]): TimelinePage {
  return { items, limit: 50, offset: 0, has_more: false };
}

describe("Timeline", () => {
  it("renders events from the API", async () => {
    const getTimeline = vi.fn().mockResolvedValue(page([event()]));
    const client: TimelineApi = { getTimeline };
    render(<Timeline client={client} userId="u" />);
    expect(await screen.findByText("finance.expense_created")).toBeInTheDocument();
  });

  it("re-queries with the event type when the filter changes", async () => {
    const getTimeline = vi.fn().mockResolvedValue(page([]));
    const client: TimelineApi = { getTimeline };
    render(<Timeline client={client} userId="u" />);
    await waitFor(() => expect(getTimeline).toHaveBeenCalledWith("u", {}));

    fireEvent.change(screen.getByLabelText("Filter by event type"), {
      target: { value: "health.sleep_recorded" },
    });
    await waitFor(() =>
      expect(getTimeline).toHaveBeenLastCalledWith("u", { eventType: "health.sleep_recorded" }),
    );
    expect(await screen.findByText("No events yet.")).toBeInTheDocument();
  });

  it("shows an error state when the call fails", async () => {
    const getTimeline = vi.fn().mockRejectedValue(new Error("boom"));
    const client: TimelineApi = { getTimeline };
    render(<Timeline client={client} userId="u" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load the timeline.");
  });
});
