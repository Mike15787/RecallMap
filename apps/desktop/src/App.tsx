import { useState, useCallback, DragEvent } from "react";
import type { ISessionResponse, IIngestResponse } from "./types/api";

const API_BASE = "http://localhost:8000";

export default function App() {
  const [session, setSession] = useState<ISessionResponse | null>(null);
  const [subject, setSubject] = useState("");
  const [ingestLog, setIngestLog] = useState<IIngestResponse[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const createSession = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/v1/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject: subject.trim() || null }),
      });
      if (!res.ok) throw new Error(`Create session failed: ${res.status}`);
      const data: ISessionResponse = await res.json();
      setSession(data);
      setIngestLog([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [subject]);

  const uploadFile = useCallback(
    async (file: File) => {
      if (!session) {
        setError("Create a session first.");
        return;
      }
      setBusy(true);
      setError(null);
      try {
        const form = new FormData();
        form.append("file", file);
        const res = await fetch(
          `${API_BASE}/v1/sessions/${session.session_id}/ingest`,
          { method: "POST", body: form }
        );
        if (!res.ok) {
          const text = await res.text();
          throw new Error(`Ingest failed (${res.status}): ${text}`);
        }
        const data: IIngestResponse = await res.json();
        setIngestLog((prev) => [data, ...prev]);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [session]
  );

  const onDrop = useCallback(
    (e: DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files?.[0];
      if (file) uploadFile(file);
    },
    [uploadFile]
  );

  return (
    <div className="min-h-full max-w-3xl mx-auto p-8 flex flex-col gap-6">
      <header>
        <h1 className="text-2xl font-semibold">RecallMap</h1>
        <p className="text-sm text-neutral-400">
          Walking-skeleton UI — drop a file to test the ingest pipeline.
        </p>
      </header>

      <section className="flex flex-col gap-3 rounded-lg border border-neutral-800 p-4">
        <h2 className="text-sm font-medium text-neutral-300">Session</h2>
        {session ? (
          <div className="text-sm">
            <div className="font-mono text-neutral-200">{session.session_id}</div>
            <div className="text-neutral-500">
              subject: {session.subject ?? "(none)"} · status: {session.status}
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <input
              className="flex-1 rounded bg-neutral-900 border border-neutral-700 px-3 py-2 text-sm"
              placeholder="Subject (optional)"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              disabled={busy}
            />
            <button
              className="rounded bg-blue-600 hover:bg-blue-500 disabled:bg-neutral-700 px-4 py-2 text-sm font-medium"
              onClick={createSession}
              disabled={busy}
            >
              Create session
            </button>
          </div>
        )}
      </section>

      <section
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`rounded-lg border-2 border-dashed p-10 text-center transition-colors ${
          dragOver
            ? "border-blue-500 bg-blue-500/10"
            : "border-neutral-700 bg-neutral-900/50"
        }`}
      >
        <p className="text-neutral-300">
          {session
            ? busy
              ? "Uploading…"
              : "Drop a PDF / image / JSON here"
            : "Create a session above first"}
        </p>
        <p className="text-xs text-neutral-500 mt-2">
          Supported: .pdf .jpg .png .webp .json (ChatGPT / Gemini export)
        </p>
      </section>

      {error && (
        <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {ingestLog.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-neutral-300">Ingest log</h2>
          <ul className="flex flex-col gap-2">
            {ingestLog.map((entry, i) => (
              <li
                key={i}
                className="rounded border border-neutral-800 bg-neutral-900/40 p-3 text-sm"
              >
                <div className="font-mono text-neutral-200">{entry.filename}</div>
                <div className="text-neutral-500">
                  +{entry.chunks_added} chunks · total {entry.total_chunks}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
