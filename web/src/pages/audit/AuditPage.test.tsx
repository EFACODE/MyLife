import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({ getAudit: vi.fn() }));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { AuditPage } from "./AuditPage";

describe("AuditPage", () => {
  beforeEach(() => {
    client.getAudit.mockResolvedValue([
      {
        audit_id: "a1",
        action: "data.access",
        actor_user_id: "u",
        subject_user_id: "u",
        resource: "timeline",
        correlation_id: "c",
        occurred_at: "2026-07-19T12:00:00Z",
        recorded_at: "2026-07-19T12:00:00Z",
      },
    ]);
  });

  it("lists audit entries", async () => {
    render(<AuditPage />);
    expect(await screen.findByText("data.access")).toBeInTheDocument();
  });
});
