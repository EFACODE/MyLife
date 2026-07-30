import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({ captureEvent: vi.fn(), getTimeline: vi.fn() }));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));
vi.mock("../../auth/MeContext", () => ({
  useMe: () => ({
    user: {
      user_id: "u",
      email: "a@b.c",
      display_name: "Ada",
      status: "active",
      household_id: null,
      created_at: "x",
    },
    status: "ready",
  }),
}));

import { CapturePage } from "./CapturePage";

describe("CapturePage", () => {
  beforeEach(() => {
    client.getTimeline.mockResolvedValue({ items: [], limit: 50, offset: 0, has_more: false });
    client.captureEvent.mockResolvedValue({ event_id: "e1" });
  });

  it("records an event with the user id and entered fields", async () => {
    render(<CapturePage />);
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Ran 5k" } });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "fitness" } });
    fireEvent.click(screen.getByText("Record event"));
    await waitFor(() =>
      expect(client.captureEvent).toHaveBeenCalledWith(
        expect.objectContaining({ user_id: "u", title: "Ran 5k", category: "fitness" }),
      ),
    );
  });
});
