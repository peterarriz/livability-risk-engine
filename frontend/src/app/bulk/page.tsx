"use client";

// Bulk CSV scoring page - /bulk
// Uploads one CSV file to the protected batch CSV endpoint and downloads the
// backend-generated scored CSV. API keys are kept only in component state.

import { useCallback, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, KeyboardEvent } from "react";
import { Card, Container } from "@/components/shell";

type PageState = "idle" | "uploading" | "success" | "error";

type ResultSummary = {
  totalRows: number;
  scoredRows: number;
  errorRows: number;
};

const MAX_BATCH_ROWS = 200;
const OUTPUT_FILENAME = "livability_scores.csv";
const SAMPLE_FILENAME = "livability_sample_addresses.csv";
const SAMPLE_CSV = [
  "address",
  "\"1600 W Chicago Ave, Chicago, IL\"",
  "\"350 5th Ave, New York, NY\"",
  "\"1600 Pennsylvania Ave NW, Washington, DC\"",
].join("\n");

function splitCSVLine(line: string): string[] {
  const result: string[] = [];
  let current = "";
  let inQuote = false;

  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === "\"") {
      if (inQuote && line[i + 1] === "\"") {
        current += "\"";
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

function normalizeCsvCell(cell: string): string {
  return cell.trim().replace(/^\uFEFF/, "").replace(/^["']|["']$/g, "");
}

function downloadCSV(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function preflightCsv(text: string): { rowCount: number; error: string | null } {
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length === 0) {
    return { rowCount: 0, error: "The CSV file is empty." };
  }

  const header = splitCSVLine(lines[0]).map((cell) => normalizeCsvCell(cell).toLowerCase());
  if (header[0] !== "address" && !header.includes("address")) {
    return {
      rowCount: 0,
      error: "Invalid CSV: include an address column as the first row.",
    };
  }

  const rowCount = Math.max(0, lines.length - 1);
  if (rowCount === 0) {
    return { rowCount, error: "Invalid CSV: add at least one address row." };
  }

  if (rowCount > MAX_BATCH_ROWS) {
    return {
      rowCount,
      error: `This CSV has ${rowCount} address rows. Bulk scoring supports a maximum of ${MAX_BATCH_ROWS} addresses per request.`,
    };
  }

  return { rowCount, error: null };
}

function summarizeResultsCsv(csvText: string): ResultSummary | null {
  const lines = csvText.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) return null;

  const headers = splitCSVLine(lines[0]).map((cell) => normalizeCsvCell(cell).toLowerCase());
  const errorIndex = headers.indexOf("error");
  const scoreIndexes = ["livability_score", "disruption_score"]
    .map((field) => headers.indexOf(field))
    .filter((index) => index >= 0);

  let scoredRows = 0;
  let errorRows = 0;

  for (const line of lines.slice(1)) {
    const cells = splitCSVLine(line);
    const rowError = errorIndex >= 0 ? normalizeCsvCell(cells[errorIndex] ?? "") : "";
    const hasScore = scoreIndexes.some((index) => normalizeCsvCell(cells[index] ?? "") !== "");

    if (rowError) {
      errorRows++;
    } else if (hasScore) {
      scoredRows++;
    }
  }

  return {
    totalRows: lines.length - 1,
    scoredRows,
    errorRows,
  };
}

function formatBackendDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => formatBackendDetail(item)).filter(Boolean).join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "";
}

async function readBackendError(response: Response): Promise<string> {
  if (response.status === 401 || response.status === 403) {
    return "The pilot API key was not accepted. Check the key and try again, or request access if you do not have one.";
  }

  let detail = "";
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const data = await response.json().catch(() => null) as { detail?: unknown; message?: unknown } | null;
    detail = formatBackendDetail(data?.detail ?? data?.message);
  } else {
    detail = await response.text().catch(() => "");
  }

  if (response.status === 400 || response.status === 422) {
    return detail || "The CSV could not be processed. Make sure it has an address column and no more than 200 rows.";
  }

  return detail
    ? `Bulk scoring failed: ${detail}`
    : "Bulk scoring is temporarily unavailable. Please try again.";
}

export default function BulkPage() {
  const [apiKey, setApiKey] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [rowCount, setRowCount] = useState<number | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [pageState, setPageState] = useState<PageState>("idle");
  const [resultCsv, setResultCsv] = useState<string | null>(null);
  const [resultSummary, setResultSummary] = useState<ResultSummary | null>(null);
  const [downloadedAutomatically, setDownloadedAutomatically] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const isUploading = pageState === "uploading";
  const hasUsableFile = selectedFile !== null && csvError === null;

  const summaryText = useMemo(() => {
    if (!resultSummary) return "Results CSV is ready.";
    return `${resultSummary.scoredRows} scored, ${resultSummary.errorRows} with row errors, ${resultSummary.totalRows} rows returned.`;
  }, [resultSummary]);

  const handleFile = useCallback(async (file: File) => {
    setSelectedFile(file);
    setFileName(file.name);
    setRowCount(null);
    setCsvError(null);
    setFormError(null);
    setPageState("idle");
    setResultCsv(null);
    setResultSummary(null);
    setDownloadedAutomatically(false);

    try {
      const text = await file.text();
      const preflight = preflightCsv(text);
      setRowCount(preflight.rowCount);
      setCsvError(preflight.error);
      if (preflight.error) setPageState("error");
    } catch {
      setCsvError("Invalid CSV: the file could not be read. Choose a plain CSV file and try again.");
      setPageState("error");
    }
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragOver(false);
      const file = event.dataTransfer.files[0];
      if (file && !isUploading) {
        void handleFile(file);
      }
    },
    [handleFile, isUploading],
  );

  const handleFileInputChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      const file = event.target.files?.[0];
      if (file) {
        void handleFile(file);
      }
    },
    [handleFile],
  );

  const handleUpload = useCallback(async () => {
    setFormError(null);

    const trimmedApiKey = apiKey.trim();
    if (!trimmedApiKey) {
      setPageState("error");
      setFormError("Enter your pilot API key before uploading a CSV.");
      return;
    }

    if (!selectedFile) {
      setPageState("error");
      setFormError("Choose a CSV file before starting bulk scoring.");
      return;
    }

    if (csvError) {
      setPageState("error");
      setFormError(csvError);
      return;
    }

    setPageState("uploading");
    setResultCsv(null);
    setResultSummary(null);
    setDownloadedAutomatically(false);

    try {
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch("/api/backend/score/batch/csv", {
        method: "POST",
        headers: {
          "X-API-Key": trimmedApiKey,
        },
        body: formData,
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(await readBackendError(response));
      }

      const csvText = await response.text();
      if (!csvText.trim()) {
        throw new Error("Bulk scoring finished, but the backend returned an empty CSV.");
      }

      setResultCsv(csvText);
      setResultSummary(summarizeResultsCsv(csvText));
      setPageState("success");
      downloadCSV(csvText, OUTPUT_FILENAME);
      setDownloadedAutomatically(true);
    } catch (error) {
      setPageState("error");
      setFormError(error instanceof Error ? error.message : "Bulk scoring failed. Please try again.");
    }
  }, [apiKey, csvError, selectedFile]);

  function handleSampleDownload() {
    downloadCSV(SAMPLE_CSV, SAMPLE_FILENAME);
  }

  function handleResultsDownload() {
    if (resultCsv) {
      downloadCSV(resultCsv, OUTPUT_FILENAME);
    }
  }

  return (
    <main className="bulk-page">
      <Container>
        <div className="bulk-back">
          <a href="/" className="bulk-back-link">&larr; Back to address scoring</a>
        </div>

        <div className="bulk-page-header">
          <div className="bulk-title-row">
            <span className="bulk-pro-badge">Pilot API</span>
            <h1 className="bulk-page-title">Bulk CSV scoring</h1>
          </div>
          <p className="bulk-page-desc">
            Upload addresses and download scored results. Bulk CSV scoring is available for pilot API users.
          </p>
        </div>

        <div className="bulk-layout">
          <div className="bulk-inputs">
            <Card className="bulk-input-card">
              <div className="bulk-input-card__header">
                <span className="bulk-input-card__label">Workflow</span>
              </div>
              <div className="bulk-input-card__body">
                <ol className="bulk-field-hint" style={{ margin: 0, paddingLeft: 18 }}>
                  <li>Upload a CSV with an <code className="bulk-code">address</code> column.</li>
                  <li>We score each address with the batch scoring endpoint.</li>
                  <li>Download the returned results CSV.</li>
                </ol>
                <p className="bulk-field-hint">
                  Max {MAX_BATCH_ROWS} addresses per request. A pilot API key is required.
                </p>
              </div>
            </Card>

            <Card className="bulk-input-card">
              <div className="bulk-input-card__header">
                <span className="bulk-input-card__label">API key</span>
              </div>
              <div className="bulk-input-card__body">
                <input
                  type="password"
                  className="bulk-api-input"
                  placeholder="Paste pilot API key"
                  value={apiKey}
                  onChange={(event: ChangeEvent<HTMLInputElement>) => setApiKey(event.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={isUploading}
                />
                <p className="bulk-field-hint">
                  The key is sent as <code className="bulk-code">X-API-Key</code> and is not saved by this page.{" "}
                  <a href="/api-access" className="bulk-link">Request access</a>
                </p>
              </div>
            </Card>

            <Card className="bulk-input-card">
              <div className="bulk-input-card__header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                <span className="bulk-input-card__label">CSV file</span>
                <button type="button" className="bulk-export-btn" onClick={handleSampleDownload}>
                  Download sample CSV
                </button>
              </div>
              <div className="bulk-input-card__body">
                <div
                  className={[
                    "bulk-drop-zone",
                    dragOver ? "bulk-drop-zone--active" : "",
                    isUploading ? "bulk-drop-zone--disabled" : "",
                  ].filter(Boolean).join(" ")}
                  onDragOver={(event: DragEvent<HTMLDivElement>) => {
                    event.preventDefault();
                    if (!isUploading) setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={isUploading ? undefined : handleDrop}
                  onClick={() => !isUploading && fileInputRef.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
                    if (event.key === "Enter" && !isUploading) {
                      fileInputRef.current?.click();
                    }
                  }}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,text/csv"
                    style={{ display: "none" }}
                    onChange={handleFileInputChange}
                  />
                  {fileName ? (
                    <div className="bulk-drop-zone__content">
                      <span className="bulk-drop-zone__filename">{fileName}</span>
                      <span className="bulk-drop-zone__count">
                        {rowCount !== null
                          ? `${rowCount} address row${rowCount === 1 ? "" : "s"} detected`
                          : "Checking CSV..."}
                      </span>
                    </div>
                  ) : (
                    <div className="bulk-drop-zone__content">
                      <span className="bulk-drop-zone__icon" aria-hidden="true">CSV</span>
                      <span className="bulk-drop-zone__hint">
                        Drop CSV here or <span className="bulk-link">click to browse</span>
                      </span>
                    </div>
                  )}
                </div>

                {csvError && <p className="bulk-parse-error" role="alert">{csvError}</p>}

                <p className="bulk-field-hint">
                  Accepted input starts with <code className="bulk-code">address</code>. Quoted addresses are safest;
                  unquoted rows with commas are also supported where possible by the backend parser.
                </p>
              </div>
            </Card>

            <div className="bulk-actions">
              <button
                type="button"
                className="bulk-process-btn"
                disabled={isUploading}
                onClick={() => void handleUpload()}
              >
                {isUploading
                  ? "Scoring CSV..."
                  : hasUsableFile
                    ? `Score ${rowCount ?? ""} address${rowCount === 1 ? "" : "es"}`
                    : "Score CSV"}
              </button>
            </div>

            <div className="bulk-format-hint">
              <p className="bulk-field-hint" style={{ marginBottom: 6 }}>
                Accepted input example:
              </p>
              <pre className="bulk-format-pre">
{`address
"1600 W Chicago Ave, Chicago, IL"
"350 5th Ave, New York, NY"`}
              </pre>
            </div>
          </div>

          <div className="bulk-results-col">
            {(formError || csvError) && pageState === "error" && (
              <div className="bulk-parse-error" role="alert">
                {formError ?? csvError}
              </div>
            )}

            {isUploading && (
              <div className="bulk-progress-card" aria-live="polite">
                <div className="bulk-progress-header">
                  <span className="bulk-progress-label">
                    Uploading CSV to the batch scorer...
                  </span>
                  <span className="bulk-progress-pct">Working</span>
                </div>
                <div className="bulk-progress-track">
                  <div className="bulk-progress-fill" style={{ width: "70%" }} />
                </div>
              </div>
            )}

            {pageState === "success" && resultCsv && (
              <Card className="bulk-results-card">
                <div className="bulk-results-card__header">
                  <span className="bulk-results-card__title">Results ready</span>
                  <button type="button" className="bulk-export-btn" onClick={handleResultsDownload}>
                    Download results CSV
                  </button>
                </div>
                <div style={{ padding: "18px 20px" }}>
                  <p className="bulk-field-hint" style={{ color: "var(--text-soft)", marginBottom: 10 }}>
                    {summaryText}
                  </p>
                  <p className="bulk-field-hint">
                    {downloadedAutomatically
                      ? `A download named ${OUTPUT_FILENAME} was started automatically.`
                      : `Use the button above to download ${OUTPUT_FILENAME}.`}
                    {" "}Rows that cannot be found stay in the CSV with blank score fields and an error value such as <code className="bulk-code">address_not_found</code>.
                  </p>
                </div>
              </Card>
            )}

            {pageState === "idle" && !resultCsv && (
              <div className="bulk-idle-hint">
                <p>Upload a CSV and enter your pilot API key.</p>
                <p className="bulk-field-hint" style={{ marginTop: 8 }}>
                  The returned CSV includes livability_score, disruption_score, confidence, severity fields, top risks, and row-level errors.
                </p>
              </div>
            )}
          </div>
        </div>
      </Container>
    </main>
  );
}
