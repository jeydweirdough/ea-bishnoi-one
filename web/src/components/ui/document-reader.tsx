"use client";

import { useRef, useState } from "react";
import { Camera, FileCheck2, LoaderCircle, ScanText, TriangleAlert, Upload, X } from "lucide-react";
import { api, type ApiError } from "@/lib/api";
import { Button } from "./controls";
import { cn } from "@/lib/cn";

export type ScanKind = "registration" | "travel_document" | "contract" | "vehicle_renewal" | "fleet_card" | "corporate_card" | "vehicle";

export type ScanResult = {
  method: "text-layer" | "ocr" | "none";
  readable: boolean;
  fields: Record<string, { value: string; confidence: number }>;
  matched: Record<string, { label: string; company?: string | null; matched?: boolean }>;
  document_kind: string | null;
  /** Passport holder not in the directory: name parts, sex and date of birth to pre-fill "Add a person". */
  person?: { first_name?: string; middle_name?: string; last_name?: string; gender?: string; birth_date?: string } | null;
};

/** Below this, a value read from the document is marked "Verify". */
export const VERIFY_BELOW = 0.8;

const WHAT: Record<ScanKind, string> = {
  registration: "the document name, number, registration date and expiry",
  travel_document: "the holder, country, document number (last 4 only) and dates",
  contract: "the title, lessor, term and rent",
  vehicle_renewal: "the OR or policy number, new expiry date and amount",
  fleet_card: "the last 4 digits, card holder, vehicle plate, provider and fuel type",
  corporate_card: "the bank, last 4 digits, expiry and card holder",
  vehicle: "the plate, make, series, year model, color, body type, owner and registration expiry",
};

/**
 * Upload panel at the top of a form: the user drops the document, the server reads it,
 * and `onRead` receives the proposed values. The file is kept so it can be attached on save.
 */
export function DocumentReader({ kind, file, onFile, onRead, discard = false }: { kind: ScanKind; file: File | null; onFile: (f: File | null) => void; onRead: (r: ScanResult | null) => void; discard?: boolean }) {
  const input = useRef<HTMLInputElement>(null);
  const camera = useRef<HTMLInputElement>(null);
  const [state, setState] = useState<"idle" | "reading" | "done" | "error">(file ? "done" : "idle");
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string>();
  const [over, setOver] = useState(false);

  async function read(f: File) {
    onFile(f);
    setState("reading");
    setError(undefined);
    const fd = new FormData();
    fd.set("kind", kind);
    fd.set("file", f);
    try {
      const r = await api<ScanResult>("/api/v1/scan", { method: "POST", body: fd });
      setResult(r);
      setState("done");
      onRead(r);
    } catch (e) {
      setError((e as ApiError).message);
      setState("error");
      onRead(null);
    }
  }

  function clear() {
    onFile(null);
    onRead(null);
    setResult(null);
    setState("idle");
    if (input.current) input.current.value = "";
  }

  const count = result ? Object.keys(result.fields).length : 0;
  const toVerify = result ? Object.values(result.fields).filter((f) => f.confidence < VERIFY_BELOW).length : 0;
  const notes = result ? Object.values(result.matched).map((m) => m) : [];

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        const f = e.dataTransfer.files?.[0];
        if (f) void read(f);
      }}
      className={cn("mb-5 rounded-[var(--radius-panel)] border border-dashed p-4 transition-colors", over ? "border-ink bg-hover" : "border-edge bg-canvas", state === "done" && "border-solid border-line bg-sheet")}
    >
      <input ref={input} type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" className="sr-only" aria-label="Document file" onChange={(e) => e.target.files?.[0] && read(e.target.files[0])} />
      <input ref={camera} type="file" accept="image/*" capture="environment" className="sr-only" tabIndex={-1} aria-label="Photograph the document" onChange={(e) => e.target.files?.[0] && read(e.target.files[0])} />
      {state === "idle" || state === "error" ? (
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <ScanText className="size-6 shrink-0 text-ink-2" strokeWidth={1.6} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-[14.5px] font-bold">{discard ? "Upload a photo of the card" : "Upload the document"}</p>
            <p className="text-[13px] leading-snug text-ink-3">The system reads {WHAT[kind]}. You review them before saving.{" "}
              {discard ? "The photo is read, then discarded: card images are never stored." : "PDF or photo, up to 10 MB."}
            </p>
            {error && (
              <p role="alert" className="mt-1.5 flex items-center gap-1.5 text-[13px] text-danger">
                <TriangleAlert className="size-4 shrink-0" strokeWidth={1.75} aria-hidden="true" /> {error}
              </p>
            )}
          </div>
          <span className="flex shrink-0 flex-wrap gap-2 self-start sm:self-center">
            <Button variant="primary" icon={Camera} onClick={() => camera.current?.click()} className="md:hidden">
              Take photo
            </Button>
            <Button variant="primary" icon={Upload} onClick={() => input.current?.click()} className="max-md:hidden">
              Choose file
            </Button>
            <Button variant="ghost" icon={Upload} onClick={() => input.current?.click()} className="md:hidden">
              Choose file
            </Button>
          </span>
        </div>
      ) : state === "reading" ? (
        <p className="flex items-center gap-3 text-[14px]" role="status">
          <LoaderCircle className="size-5 shrink-0 animate-spin text-ink-2" strokeWidth={2} aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate">
            Reading <span className="font-medium">{file?.name}</span>… This takes a few seconds.
          </span>
        </p>
      ) : (
        <div className="flex items-start gap-3">
          <FileCheck2 className="mt-0.5 size-5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[14px] font-medium">{file?.name}</p>
            <p className="text-[13px] leading-snug text-ink-2" role="status">
              {!result
                ? discard
                  ? "Read and discarded."
                  : "Attached. It will be saved with the record."
                : count === 0
                  ? discard
                    ? "No details could be read from this photo. Enter them below."
                    : "No details could be read from this file. Enter them below; the file is still attached."
                  : `${count} detail${count === 1 ? "" : "s"} read from the ${discard ? "photo" : "document"}.${toVerify ? ` Check the ${toVerify} marked “Verify”.` : " Review them before saving."}`}
            </p>
            {notes.map((m) => (
              <p key={m.label} className="text-[12.5px] text-ink-3">
                {m.company
                  ? `Issued to ${m.label} (${m.company})`
                  : m.matched === false
                    ? kind === "fleet_card"
                      ? `Plate ${m.label} is not in the vehicle registry. Choose the vehicle below.`
                      : `Lessor “${m.label}” is not in your lessor list yet. Add it under Lessors, or choose one below.`
                    : m.matched
                      ? `Plate ${m.label} matched to a registered vehicle.`
                      : `Name on the ${discard ? "card" : "document"}: ${m.label}`}
              </p>
            ))}
          </div>
          <span className="flex shrink-0 gap-1">
            <Button size="sm" variant="ghost" onClick={() => input.current?.click()}>
              Replace
            </Button>
            <Button size="sm" variant="ghost" icon={X} aria-label="Remove file" onClick={clear} />
          </span>
        </div>
      )}
    </div>
  );
}

export function ReadBadge({ verify }: { verify: boolean }) {
  return verify ? (
    <span className="shrink-0 rounded-full border border-ink px-2 text-[11.5px] font-bold leading-5">Verify</span>
  ) : (
    <span className="shrink-0 text-[11.5px] font-medium text-ink-3">Read from document</span>
  );
}
