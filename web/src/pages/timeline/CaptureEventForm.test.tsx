import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CaptureEventForm } from "./CaptureEventForm";

const client = { captureEvent: vi.fn() };

describe("CaptureEventForm", () => {
  beforeEach(() => {
    client.captureEvent.mockReset();
  });

  it("records an event with the user id and entered fields, then notifies", async () => {
    client.captureEvent.mockResolvedValue({ event_id: "e1" });
    const onCaptured = vi.fn();
    render(<CaptureEventForm client={client} userId="u" onCaptured={onCaptured} />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Ran 5k" } });
    fireEvent.change(screen.getByLabelText("Categoria"), { target: { value: "fitness" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar evento" }));
    await waitFor(() =>
      expect(client.captureEvent).toHaveBeenCalledWith(
        expect.objectContaining({ user_id: "u", title: "Ran 5k", category: "fitness" }),
      ),
    );
    await waitFor(() => expect(onCaptured).toHaveBeenCalled());
    expect(screen.getByLabelText("Título")).toHaveValue("");
  });

  it("shows an error and keeps the input when capture fails", async () => {
    client.captureEvent.mockRejectedValue(new Error("boom"));
    const onCaptured = vi.fn();
    render(<CaptureEventForm client={client} userId="u" onCaptured={onCaptured} />);
    fireEvent.change(screen.getByLabelText("Título"), { target: { value: "Ran 5k" } });
    fireEvent.change(screen.getByLabelText("Categoria"), { target: { value: "fitness" } });
    fireEvent.click(screen.getByRole("button", { name: "Registrar evento" }));
    expect(await screen.findByText("Não foi possível registrar o evento.")).toBeInTheDocument();
    expect(onCaptured).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Título")).toHaveValue("Ran 5k");
  });
});
