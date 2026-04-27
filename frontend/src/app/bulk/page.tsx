"use client";

// Bulk Address Scorer page — /bulk
// Accepts a CSV with an "address" column, processes each address against
// /score (with a user-supplied API key), shows live progress, and renders
// results in a sortable table with CSV export.
// Feature is gated behind API key auth — pilot users with a key can score.

import React, { useCallback, useMemo, useRef, useState } from "react";
import { useUser } from "@/lib/clerk-client";
import { fetchScoreWithKey, ScoreResponse } from "@/lib/api";
import { hasUnlimitedLookupAccess } from "@/lib/lookup-quota";
import { Card, Container } from "@/components/shell";

// ── Types ─────────────────────────────────────────────────────────────────────

type BulkRow = {
  address: string;
  disruption_score: number | null;
  severity_dominant: "LOW" | "MEDIUM" | "HIGH" | null;
  top_risk: string;
  confidence: string;
  mode: string;
  error?: string;
};

type SortCol = "address" | "score" | "severity" | "confidence";
type SortDir = "asc" | "desc";
type PageState = "idle" | "processing" | "done";

const DEMO_BATCH_LIMIT = 100;

// ── CSV helpers ───────────────────────────────────────────────────────────────

/** RFC 4180-compatible single-line CSV splitter that handles quoted fields. */
function splitCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        current += '"';
        i++;
      } else {
        inQuote = !inQuote;
      }
    } else if (ch === "," && !inQuote) {
      result.push(current);
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current);
  return result;
}

function parseCSV(text: string, maxRows: number | null = DEMO_BATCH_LIMIT): { addresses: string[]; error: string | null } {
  const lines = text.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) {
    return { addresses: [], error: "CSV is empty or missing data rows." };
  }
  const headers = splitCSVLine(lines[0]).map((h) =>
    h.trim().replace(/^["']|["']$/g, "").toLowerCase(),
  );
  const addrIdx = headers.findIndex((h) => h === "address");
  if (addrIdx === -1) {
    return {
      addresses: [],
      error: 'No "address" column found. Ensure the header row contains "address".',
    };
  }
  const addresses: string[] = [];
  for (const line of lines.slice(1)) {
    const cols = splitCSVLine(line);
    const addr = (cols[addrIdx] ?? "").trim().replace(/^["']|["']$/g, "");
    if (addr) addresses.push(addr);
  }
  if (addresses.length === 0) {
    return { addresses: [], error: "No addresses found in the CSV data rows." };
  }
  if (maxRows !== null && addresses.length > maxRows) {
    return {
      addresses: [],
      error: `CSV contains ${addresses.length} addresses — maximum is ${maxRows} per batch.`,
    };
  }
  return { addresses, error: null };
}

// ── Score helpers ─────────────────────────────────────────────────────────────

const SEV_RANK: Record<string, number> = { LOW: 1, MEDIUM: 2, HIGH: 3 };

function dominantSeverity(sev: ScoreResponse["severity"]): "LOW" | "MEDIUM" | "HIGH" {
  let best: "LOW" | "MEDIUM" | "HIGH" = "LOW";
  for (const v of [sev.noise, sev.traffic, sev.dust]) {
    if ((SEV_RANK[v] ?? 0) > (SEV_RANK[best] ?? 0)) {
      best = v as "LOW" | "MEDIUM" | "HIGH";
    }
  }
  return best;
}

function scoreColor(score: number | null): string {
  if (score === null) return "var(--text-muted)";
  if (score >= 75) return "#ef4444";
  if (score >= 50) return "#f97316";
  if (score >= 25) return "#eab308";
  return "#22c55e";
}

const SEV_COLOR: Record<string, string> = {
  HIGH: "#ef4444",
  MEDIUM: "#f97316",
  LOW: "#22c55e",
};

// ── CSV export ────────────────────────────────────────────────────────────────

function rowsToCSV(rows: BulkRow[]): string {
  const header = ["address", "disruption_score", "severity", "top_risk", "confidence", "mode", "error"];
  const lines: string[] = [header.join(",")];
  for (const r of rows) {
    lines.push(
      [
        `"${r.address.replace(/"/g, '""')}"`,
        r.disruption_score ?? "",
        r.severity_dominant ?? "",
        `"${(r.top_risk ?? "").replace(/"/g, '""')}"`,
        r.confidence,
        r.mode,
        `"${(r.error ?? "").replace(/"/g, '""')}"`,
      ].join(","),
    );
  }
  return lines.join("\n");
}

function downloadCSV(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ── Component ─────────────────────────────────────────────────────────────────

export default function BulkPage() {
  const { user } = useUser();
  const tier = (user?.publicMetadata as Record<string, unknown>)?.subscription_tier;
  const hasUnlimitedAccess = hasUnlimitedLookupAccess(tier);
  const batchLimit = hasUnlimitedAccess ? null : DEMO_BATCH_LIMIT;

  const [apiKey, setApiKey] = useState("");
  const [fileName, setFileName] = useState<string | null>(null);
  const [addresses, setAddresses] = useState<string[]>([]);
  const [parseError, setParseError] = useState<string | null>(null);
  const [rows, setRows] = useState<BulkRow[]>([]);
  const [pageState, setPageState] = useState<PageState>("idle");
  const [processed, setProcessed] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [sortCol, setSortCol] = useState<SortCol>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef(false);

  // ── File handling ──────────────────────────────────────────────────────────

  const handleFile = useCallback((file: File) => {
    setParseError(null);
    setFileName(file.name);
    setAddresses([]);
    setRows([]);
    setPageState("idle");
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = (e.target?.result as string) ?? "";
      const { addresses: addrs, error } = parseCSV(text, batchLimit);
      if (error) setParseError(error);
      else setAddresses(addrs);
    };
    reader.readAsText(file);
  }, [batchLimit]);

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) handleFile(file);
    },
    [handleFile],
  );

  // ── Bulk processing ────────────────────────────────────────────────────────

  const handleProcess = useCallback(async () => {
    if (!addresses.length) return;
    abortRef.current = false;
    setPageState("processing");
    setProcessed(0);
    setRows([]);

    const results: BulkRow[] = [];
    for (let i = 0; i < addresses.length; i++) {
      if (abortRef.current) break;
      const addr = addresses[i];
      try {
        const score = await fetchScoreWithKey(addr, apiKey.trim());
        results.push({
          address: addr,
          disruption_score: score.disruption_score,
          severity_dominant: dominantSeverity(score.severity),
          top_risk: score.top_risks[0] ?? "",
          confidence: score.confidence,
          mode: score.mode ?? "live",
        });
      } catch (err) {
        results.push({
          address: addr,
          disruption_score: null,
          severity_dominant: null,
          top_risk: "",
          confidence: "",
          mode: "",
          error: err instanceof Error ? err.message : String(err),
        });
      }
      setProcessed(i + 1);
      // Update rows progressively so table fills in during processing
      setRows([...results]);
    }
    setPageState("done");
  }, [addresses, apiKey]);

  const handleStop = useCallback(() => {
    abortRef.current = true;
  }, []);

  // ── Sorting ────────────────────────────────────────────────────────────────

  const sortedRows = useMemo(() => {
    const copy = [...rows];
    copy.sort((a, b) => {
      let cmp = 0;
      switch (sortCol) {
        case "address":
          cmp = a.address.localeCompare(b.address);
          break;
        case "score":
          cmp = (a.disruption_score ?? -1) - (b.disruption_score ?? -1);
          break;
        case "severity":
          cmp =
            (SEV_RANK[a.severity_dominant ?? ""] ?? 0) -
            (SEV_RANK[b.severity_dominant ?? ""] ?? 0);
          break;
        case "confidence":
          cmp =
            (SEV_RANK[a.confidence ?? ""] ?? 0) -
            (SEV_RANK[b.confidence ?? ""] ?? 0);
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sortCol, sortDir]);

  function toggleSort(col: SortCol) {
    if (sortCol === col) setSortDir((d: SortDir) => (d === "asc" ? "desc" : "asc"));
    else { setSortCol(col); setSortDir("desc"); }
  }

  function sortArrow(col: SortCol): string {
    if (sortCol !== col) return " ↕";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  // ── Derived state ──────────────────────────────────────────────────────────

  const progressPct =
    addresses.length > 0 ? Math.round((processed / addresses.length) * 100) : 0;
  const isProcessing = pageState === "processing";
  const isDone = pageState === "done";
  const canProcess = addresses.length > 0 && !isProcessing;
  const successCount = rows.filter((r: BulkRow) => !r.error).length;
  const addrCount = addresses.length;

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <main className="bulk-page">
      <Container>
        {/* Back link */}
        <div className="bulk-back">
          <a href="/" className="bulk-back-link">← Back to scorer</a>
        </div>

        {/* Page header */}
        <div className="bulk-page-header">
          <div className="bulk-title-row">
            <span className="bulk-pro-badge">API KEY</span>
            <h1 className="bulk-page-title">Bulk Address Scorer</h1>
          </div>
          <p className="bulk-page-desc">
            Upload a CSV with an <code className="bulk-code">address</code> column.{" "}
            {hasUnlimitedAccess
              ? "Pilot demo access allows larger files. An API key is required."
              : `Score up to ${DEMO_BATCH_LIMIT} US addresses at once. An API key is required.`}
          </p>
        </div>

        <div className="bulk-layout">
          {/* ── Left column: inputs ─────────────────────────────────────── */}
          <div className="bulk-inputs">
            {/* API key */}
            <Card className="bulk-input-card">
              <div className="bulk-input-card__header">
                <span className="bulk-input-card__label">API Key</span>
              </div>
              <div className="bulk-input-card__body">
                <input
                  type="password"
                  className="bulk-api-input"
                  placeholder="lre_xxxxxxxx…"
                  value={apiKey}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                    setApiKey(e.target.value)
                  }
                  autoComplete="off"
                  spellCheck={false}
                  disabled={isProcessing}
                />
                <p className="bulk-field-hint">
                  Don&apos;t have a key?{" "}
                  <a href="/api-access" className="bulk-link">Request access →</a>
                </p>
              </div>
            </Card>

            {/* CSV upload */}
            <Card className="bulk-input-card">
              <div className="bulk-input-card__header">
                <span className="bulk-input-card__label">CSV File</span>
              </div>
              <div className="bulk-input-card__body">
                <div
                  className={[
                    "bulk-drop-zone",
                    dragOver ? "bulk-drop-zone--active" : "",
                    isProcessing ? "bulk-drop-zone--disabled" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onDragOver={(e: React.DragEvent<HTMLDivElement>) => {
                    e.preventDefault();
                    if (!isProcessing) setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={isProcessing ? undefined : handleDrop}
                  onClick={() => !isProcessing && fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e: React.KeyboardEvent<HTMLDivElement>) =>
                    e.key === "Enter" && !isProcessing && fileInputRef.current?.click()
                  }
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv"
                    style={{ display: "none" }}
                    onChange={handleFileInputChange}
                  />
                  {fileName && addrCount > 0 ? (
                    <div className="bulk-drop-zone__content">
                      <span className="bulk-drop-zone__filename">{fileName}</span>
                      <span className="bulk-drop-zone__count">
                        {addrCount} address{addrCount !== 1 ? "es" : ""} found
                      </span>
                    </div>
                  ) : (
                    <div className="bulk-drop-zone__content">
                      <span className="bulk-drop-zone__icon">⬆</span>
                      <span className="bulk-drop-zone__hint">
                        Drop CSV here or{" "}
                        <span className="bulk-link">click to browse</span>
                      </span>
                    </div>
                  )}
                </div>
                {parseError && (
                  <p className="bulk-parse-error">{parseError}</p>
                )}
                <p className="bulk-field-hint">
                  Required column:{" "}
                  <code className="bulk-code">address</code>.
                  {hasUnlimitedAccess ? " Pilot demo access allows larger files." : ` Max ${DEMO_BATCH_LIMIT} rows per batch.`}
                </p>
              </div>
            </Card>

            {/* Action buttons */}
            <div className="bulk-actions">
              <button
                className="bulk-process-btn"
                disabled={!canProcess}
                onClick={handleProcess}
              >
                {isProcessing
                  ? `Scoring ${processed} / ${addrCount}…`
                  : `Score ${addrCount > 0 ? addrCount + " " : ""}Address${addrCount !== 1 ? "es" : ""}`}
              </button>
              {isProcessing && (
                <button className="bulk-stop-btn" onClick={handleStop}>
                  Stop
                </button>
              )}
            </div>

            {/* Example format hint */}
            {pageState === "idle" && addrCount === 0 && !parseError && (
              <div className="bulk-format-hint">
                <p className="bulk-field-hint" style={{ marginBottom: 6 }}>
                  Example CSV:
                </p>
                <pre className="bulk-format-pre">
{`address
1600 W Chicago Ave, Chicago, IL
700 W Grand Ave, Chicago, IL
233 S Wacker Dr, Chicago, IL`}
                </pre>
              </div>
            )}
          </div>

          {/* ── Right column: progress + results ────────────────────────── */}
          <div className="bulk-results-col">
            {/* Progress bar */}
            {(isProcessing || isDone) && rows.length + processed > 0 && (
              <div className="bulk-progress-card">
                <div className="bulk-progress-header">
                  <span className="bulk-progress-label">
                    {isDone
                      ? `Complete — ${successCount} of ${rows.length} scored successfully`
                      : `Processing… ${processed} / ${addrCount}`}
                  </span>
                  <span className="bulk-progress-pct">{progressPct}%</span>
                </div>
                <div className="bulk-progress-track">
                  <div
                    className="bulk-progress-fill"
                    style={{
                      width: `${progressPct}%`,
                      background: isDone ? "var(--mint)" : "var(--brand)",
                    }}
                  />
                </div>
              </div>
            )}

            {/* Results table */}
            {rows.length > 0 && (
              <Card className="bulk-results-card">
                <div className="bulk-results-card__header">
                  <span className="bulk-results-card__title">
                    Results{isProcessing ? ` (${rows.length} so far)` : ""}
                  </span>
                  {isDone && (
                    <button
                      className="bulk-export-btn"
                      onClick={() => downloadCSV(rowsToCSV(rows), "bulk_scores.csv")}
                    >
                      Export CSV
                    </button>
                  )}
                </div>
                <div className="bulk-table-scroll">
                  <table className="bulk-table">
                    <thead>
                      <tr>
                        <th
                          className="bulk-th bulk-th--sortable"
                          onClick={() => toggleSort("address")}
                        >
                          Address{sortArrow("address")}
                        </th>
                        <th
                          className="bulk-th bulk-th--sortable bulk-th--num"
                          onClick={() => toggleSort("score")}
                        >
                          Score{sortArrow("score")}
                        </th>
                        <th
                          className="bulk-th bulk-th--sortable"
                          onClick={() => toggleSort("severity")}
                        >
                          Severity{sortArrow("severity")}
                        </th>
                        <th className="bulk-th bulk-th--wide">Top Risk</th>
                        <th
                          className="bulk-th bulk-th--sortable"
                          onClick={() => toggleSort("confidence")}
                        >
                          Confidence{sortArrow("confidence")}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row: BulkRow, idx: number) => (
                        <tr key={idx} className="bulk-tr">
                          <td className="bulk-td bulk-td--address">{row.address}</td>
                          <td
                            className="bulk-td bulk-td--num"
                            style={{ color: scoreColor(row.disruption_score) }}
                          >
                            {row.error ? (
                              <span className="bulk-err-badge" title={row.error}>
                                ERR
                              </span>
                            ) : (
                              <strong>{row.disruption_score}</strong>
                            )}
                          </td>
                          <td
                            className="bulk-td"
                            style={{
                              color:
                                SEV_COLOR[row.severity_dominant ?? ""] ??
                                "var(--text-muted)",
                            }}
                          >
                            {row.severity_dominant ?? "—"}
                          </td>
                          <td className="bulk-td bulk-td--risk">
                            {row.error ? (
                              <span className="bulk-err-text">{row.error}</span>
                            ) : (
                              row.top_risk || "—"
                            )}
                          </td>
                          <td className="bulk-td">{row.confidence || "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            )}

            {/* Idle placeholder */}
            {rows.length === 0 && pageState === "idle" && (
              <div className="bulk-idle-hint">
                <p>Upload a CSV and enter your API key to get started.</p>
                <p className="bulk-field-hint" style={{ marginTop: 8 }}>
                  Results will appear here as each address is scored.
                </p>
              </div>
            )}
          </div>
        </div>
      </Container>
    </main>
  );
}
