import { useState, type ChangeEvent, type FormEvent } from "react";

import type { ApiClient } from "../../api/client";
import type { SearchHit } from "../../api/types";
import { useApiClient } from "../../api/useApiClient";
import { Button } from "../../components/ui/Button";
import { ErrorText } from "../../components/ui/ErrorText";
import { Field, TextInput } from "../../components/ui/Field";
import { Section } from "../../components/ui/Section";
import { useAsync } from "../../lib/useAsync";

type KnowledgeApi = Pick<
  ApiClient,
  | "uploadDocument"
  | "listDocuments"
  | "extractDocument"
  | "indexDocument"
  | "memorySearch"
  | "consolidateGraph"
  | "listEntities"
>;

export function KnowledgePage() {
  const client = useApiClient();
  return (
    <>
      <Documents client={client} />
      <MemorySearch client={client} />
      <Graph client={client} />
    </>
  );
}

function Documents({ client }: { client: KnowledgeApi }) {
  const documents = useAsync(() => client.listDocuments(), [client]);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  function pick(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  async function upload(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!file) return;
    try {
      await client.uploadDocument(file);
      setFile(null);
      await documents.run();
    } catch {
      setError("Não foi possível enviar o documento.");
    }
  }

  async function extract(id: string) {
    setNote(null);
    const result = await client.extractDocument(id);
    setNote(`Extraídos ${result.char_count} caracteres de ${id.slice(0, 8)}…`);
  }

  async function index(id: string) {
    setNote(null);
    const memory = await client.indexDocument(id);
    setNote(`Indexado ${id.slice(0, 8)}… (dim ${memory.dimension}).`);
  }

  return (
    <Section title="Documentos">
      <form onSubmit={upload} className="mb-3 flex items-center gap-2">
        <input aria-label="Arquivo do documento" type="file" onChange={pick} />
        <Button type="submit" disabled={!file}>
          Enviar
        </Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {note && <p className="mb-2 text-sm text-green-700">{note}</p>}
      <ul className="flex flex-col gap-2 text-sm">
        {(documents.data ?? []).map((doc) => (
          <li
            key={doc.document_id}
            className="flex items-center justify-between rounded border border-gray-200 px-3 py-2"
          >
            <span>
              <span className="font-medium">{doc.filename}</span>
              <span className="text-gray-500"> · {doc.byte_size} bytes</span>
            </span>
            <span className="flex gap-3">
              <button
                type="button"
                onClick={() => extract(doc.document_id)}
                className="text-blue-600 hover:underline"
              >
                Extrair
              </button>
              <button
                type="button"
                onClick={() => index(doc.document_id)}
                className="text-blue-600 hover:underline"
              >
                Indexar
              </button>
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

function MemorySearch({ client }: { client: KnowledgeApi }) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      setHits(await client.memorySearch(query.trim()));
    } catch {
      setError("Não foi possível buscar.");
    }
  }

  return (
    <Section title="Busca na memória">
      <form onSubmit={submit} className="mb-3 flex items-end gap-2">
        <Field label="Consulta">
          <TextInput value={query} onChange={(e) => setQuery(e.target.value)} required />
        </Field>
        <Button type="submit">Buscar</Button>
      </form>
      {error && <ErrorText>{error}</ErrorText>}
      {hits && hits.length === 0 && <p className="text-sm text-gray-500">Nenhum resultado.</p>}
      <ul className="flex flex-col gap-1 text-sm">
        {(hits ?? []).map((hit) => (
          <li key={hit.document_id} className="rounded border border-gray-200 px-3 py-2">
            <span className="text-gray-500">score {hit.score.toFixed(3)} · </span>
            {hit.preview}
          </li>
        ))}
      </ul>
    </Section>
  );
}

function Graph({ client }: { client: KnowledgeApi }) {
  const entities = useAsync(() => client.listEntities(), [client]);
  const [note, setNote] = useState<string | null>(null);

  async function consolidate() {
    const result = await client.consolidateGraph();
    setNote(`${result.entities} entidades, ${result.relationships} relações.`);
    await entities.run();
  }

  return (
    <Section
      title="Grafo de conhecimento"
      actions={<Button onClick={consolidate}>Consolidar</Button>}
    >
      {note && <p className="mb-2 text-sm text-green-700">{note}</p>}
      <ul className="flex flex-col gap-1 text-sm">
        {(entities.data ?? []).map((entity) => (
          <li key={entity.entity_id} className="rounded border border-gray-200 px-3 py-2">
            <span className="font-medium">{entity.entity_type}</span>: {entity.entity_key}
            <span className="text-gray-500"> · ×{entity.occurrences}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
