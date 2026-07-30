import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const client = vi.hoisted(() => ({
  uploadDocument: vi.fn(),
  listDocuments: vi.fn(),
  extractDocument: vi.fn(),
  indexDocument: vi.fn(),
  memorySearch: vi.fn(),
  consolidateGraph: vi.fn(),
  listEntities: vi.fn(),
}));
vi.mock("../../api/useApiClient", () => ({ useApiClient: () => client }));

import { KnowledgePage } from "./KnowledgePage";

describe("KnowledgePage", () => {
  beforeEach(() => {
    client.listDocuments.mockResolvedValue([
      {
        document_id: "d1",
        filename: "notes.txt",
        content_type: "text/plain",
        byte_size: 12,
        checksum: "x",
        created_at: "y",
      },
    ]);
    client.uploadDocument.mockResolvedValue({ document_id: "d2" });
    client.memorySearch.mockResolvedValue([{ document_id: "d1", score: 0.5, preview: "hello" }]);
    client.consolidateGraph.mockResolvedValue({ entities: 3, relationships: 2 });
    client.listEntities.mockResolvedValue([]);
  });

  it("uploads a document", async () => {
    render(<KnowledgePage />);
    const file = new File(["hi"], "note.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("Document file"), { target: { files: [file] } });
    fireEvent.click(screen.getByText("Upload"));
    await waitFor(() => expect(client.uploadDocument).toHaveBeenCalledWith(file));
  });

  it("searches memory and renders hits", async () => {
    render(<KnowledgePage />);
    fireEvent.change(screen.getByLabelText("Query"), { target: { value: "hello" } });
    fireEvent.click(screen.getByText("Search"));
    expect(await screen.findByText(/hello/)).toBeInTheDocument();
    expect(client.memorySearch).toHaveBeenCalledWith("hello");
  });

  it("consolidates the graph", async () => {
    render(<KnowledgePage />);
    fireEvent.click(screen.getByText("Consolidate"));
    expect(await screen.findByText(/3 entities, 2 relationships/)).toBeInTheDocument();
  });
});
