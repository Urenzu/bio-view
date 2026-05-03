import type { AskRequest } from "./types";

export type SSEEvent =
  | { event: "conversation"; data: { conversation_id: number } }
  | { event: "hits"; data: unknown[] }
  | { event: "token"; data: string }
  | { event: "error"; data: { message: string } }
  | { event: "done"; data: "" };

export async function streamAsk(
  req: AskRequest,
  onEvent: (ev: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch("/ask", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(req),
    signal,
  });
  if (!res.ok || !res.body) {
    throw new Error(`ask failed: ${res.status} ${await res.text()}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");

    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const parsed = parseBlock(block);
      if (parsed) onEvent(parsed);
    }
  }
}

function parseBlock(block: string): SSEEvent | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const raw of block.split("\n")) {
    if (raw.startsWith(":")) continue; // SSE comment / keep-alive ping
    if (raw.startsWith("event:")) event = raw.slice(6).trim();
    else if (raw.startsWith("data:")) dataLines.push(raw.slice(5).replace(/^ /, ""));
  }
  const data = dataLines.join("\n");
  switch (event) {
    case "conversation":
    case "hits":
    case "error":
      try {
        return { event, data: JSON.parse(data) } as SSEEvent;
      } catch {
        return null;
      }
    case "token":
      return { event: "token", data };
    case "done":
      return { event: "done", data: "" };
    default:
      return null;
  }
}
