"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type { ChangeEvent, DragEvent, KeyboardEvent } from "react";
import { Card, Container } from "@/components/shell";
import { SignedIn, SignInButton, UserButton, useAuth, useUser } from "@/lib/clerk-client";
import { getBulkAccessTier } from "@/lib/bulk-access";

type PageState = "idle" | "uploading" | "success" | "error";

type ResultSummary = {
  totalRows: number;
  scoredRows: number;
  errorRows: number;
};

const MAX_BATCH_ROWS = 200;
const OUTPUT_FILENAME = "livability_scores.csv";
const SAMPLE_FILENAME = "livability_sample_addresses.csv";
const CLERK_CONFIGURED = process.env.NEXT_PUBLIC_CLERK_CONFIGURED === "true";
const SAMPLE_CSV = [
  "property_id,street_address,city,state,zip",
  "demo-1,1600 W Chicago Ave,Chicago,IL,60622",
  "demo-2,350 5th Ave,New York,NY,10118",
  "demo-3,1600 Pennsylvania Ave NW,Washington,DC,20500",
].join("\n");

const ADDRESS_HEADERS = new Set(["address", "addresses", "fulladdress"]);
const STREET_HEADERS = new Set(["streetaddress", "street", "addressline1", "propertyaddress"]);
const CITY_HEADERS = new Set(["city"]);
const STATE_HEADERS = new Set(["state", "statecode"]);

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

function normalizeCsvHeader(cell: string): string {
  return normalizeCsvCell(cell).toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function hasAnyHeader(headers: string[], accepted: Set<string>): boolean {
  return headers.some((header) => accepted.has(header));
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

  const header = splitCSVLine(lines[0]).map((cell) => normalizeCsvHeader(cell));
  const hasAddressColumn = hasAnyHeader(header, ADDRESS_HEADERS);
  const hasStructuredColumns = (
    hasAnyHeader(header, STREET_HEADERS)
    && hasAnyHeader(header, CITY_HEADERS)
    && hasAnyHeader(header, STATE_HEADERS)
  );
  if (!hasAddressColumn && !hasStructuredColumns) {
    return {
      rowCount: 0,
      error: "Invalid CSV: include street_address, city, state, and optional zip columns, or include an address column.",
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

function formatRouteDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => formatRouteDetail(item)).filter(Boolean).join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "";
}

async function readBulkRouteError(response: Response): Promise<string> {
  let detail = "";
  const contentType = response.headers.get("content-type") ?? "";

  if (contentType.includes("application/json")) {
    const data = await response.json().catch(() => null) as { detail?: unknown; message?: unknown } | null;
    detail = formatRouteDetail(data?.detail ?? data?.message);
  } else {
    detail = await response.text().catch(() => "");
  }

  if (response.status === 401) {
    return detail || "Sign in to upload CSV.";
  }

  if (response.status === 403) {
    return detail || "Bulk CSV scoring is available for pilot users. Request pilot access to upload CSV files.";
  }

  if (response.status === 400 || response.status === 422) {
    return detail || "The CSV could not be processed. Make sure it has an address column and no more than 200 rows.";
  }

  return detail
    ? `Bulk scoring failed: ${detail}`
    : "Bulk scoring is temporarily unavailable. Please try again.";
}

export default function BulkPage() {
  const { user, isLoaded, isSignedIn } = useUser();
  const authState = useAuth();
  const bulkTier = getBulkAccessTier(authState.sessionClaims, user?.publicMetadata);
  const hasBulkAccess = bulkTier !== null;

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

      const response = await fetch("/api/bulk/score-csv", {
        method: "POST",
        body: formData,
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(await readBulkRouteError(response));
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
  }, [csvError, selectedFile]);

  function handleSampleDownload() {
    downloadCSV(SAMPLE_CSV, SAMPLE_FILENAME);
  }

  function handleResultsDownload() {
    if (resultCsv) {
      downloadCSV(resultCsv, OUTPUT_FILENAME);
    }
  }

  function renderSignInAction() {
    if (CLERK_CONFIGURED) {
      return (
        <SignInButton mode="modal">
          <button type="button" className="gate-btn gate-btn--primary">
            Sign in to upload CSV
          </button>
        </SignInButton>
      );
    }

    return (
      <a href="/sign-in" className="gate-btn gate-btn--primary">
        Sign in to upload CSV
      </a>
    );
  }

  return (
    <main className="bulk-page">
      <Container>
        <div className="bulk-back">
          <a href="/" className="bulk-back-link">&larr; Back to address scoring</a>
        </div>

        <div className="bulk-page-header">
          <div className="bulk-title-row">
            <span className="bulk-pro-badge">Pilot account</span>
            <h1 className="bulk-page-title">Bulk CSV scoring</h1>
          </div>
          <p className="bulk-page-desc">
            Upload addresses and download scored results. Bulk CSV scoring is available for signed-in pilot and internal accounts during design-partner pilots.
          </p>
        </div>

        {!isLoaded && (
          <Card className="bulk-input-card">
            <div className="bulk-input-card__header">
              <span className="bulk-input-card__label">Account access</span>
            </div>
            <div className="bulk-input-card__body">
              <p className="bulk-field-hint">Checking account access...</p>
            </div>
          </Card>
        )}

        {isLoaded && !isSignedIn && (
          <Card className="bulk-input-card">
            <div className="bulk-input-card__header">
              <span className="bulk-input-card__label">Account access</span>
            </div>
            <div className="bulk-input-card__body">
              <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Sign in to upload CSV</h2>
              <p className="bulk-field-hint">
                Public single-address scoring still works without sign-in. Bulk CSV scoring is reserved for pilot users and internal accounts.
              </p>
              <div className="bulk-actions">
                {renderSignInAction()}
                <a href="/app" className="gate-btn gate-btn--secondary">
                  Open public scoring
                </a>
              </div>
            </div>
          </Card>
        )}

        {isLoaded && isSignedIn && !hasBulkAccess && (
          <Card className="bulk-input-card">
            <div className="bulk-input-card__header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
              <span className="bulk-input-card__label">Pilot access</span>
              <SignedIn>
                <UserButton afterSignOutUrl="/" />
              </SignedIn>
            </div>
            <div className="bulk-input-card__body">
              <h2 style={{ margin: 0, fontSize: "1.1rem" }}>Bulk CSV scoring is available for pilot users</h2>
              <p className="bulk-field-hint">
                Your signed-in account is not currently enabled for bulk CSV scoring. Request pilot access and we will review the workflow with your team.
              </p>
              <div className="bulk-actions">
                <a href="/api-access#pilot-bulk-access" className="gate-btn gate-btn--primary">
                  Request pilot access
                </a>
                <a href="/app" className="gate-btn gate-btn--secondary">
                  Open public scoring
                </a>
              </div>
            </div>
          </Card>
        )}

        {isLoaded && isSignedIn && hasBulkAccess && (
          <div className="bulk-layout">
            <div className="bulk-inputs">
              <Card className="bulk-input-card">
                <div className="bulk-input-card__header" style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center" }}>
                  <span className="bulk-input-card__label">Account access</span>
                  <SignedIn>
                    <UserButton afterSignOutUrl="/" />
                  </SignedIn>
                </div>
                <div className="bulk-input-card__body">
                  <p className="bulk-field-hint">
                    Bulk upload is enabled for this pilot account. Public single-address scoring remains available without sign-in.
                  </p>
                </div>
              </Card>

              <Card className="bulk-input-card">
                <div className="bulk-input-card__header">
                  <span className="bulk-input-card__label">Workflow</span>
                </div>
                <div className="bulk-input-card__body">
                  <ol className="bulk-field-hint" style={{ margin: 0, paddingLeft: 18 }}>
                    <li>Upload a CSV with <code className="bulk-code">street_address</code>, <code className="bulk-code">city</code>, <code className="bulk-code">state</code>, and optional <code className="bulk-code">zip</code> columns.</li>
                    <li>We score each address through the pilot bulk scorer.</li>
                    <li>Download the returned results CSV with your original columns preserved.</li>
                  </ol>
                  <p className="bulk-field-hint">
                    Also accepted: a single <code className="bulk-code">address</code> column. Max {MAX_BATCH_ROWS} rows per request. Pilot account access is checked before upload.
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
                      disabled={isUploading}
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
                    Recommended columns: <code className="bulk-code">street_address</code>, <code className="bulk-code">city</code>, <code className="bulk-code">state</code>, <code className="bulk-code">zip</code>. ZIP is optional but helpful; state should be a two-letter code where possible.
                    {" "}Single-column <code className="bulk-code">address</code> CSVs are still accepted.
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
{`property_id,street_address,city,state,zip
demo-1,1600 W Chicago Ave,Chicago,IL,60622
demo-2,350 5th Ave,New York,NY,10118`}
                </pre>
                <p className="bulk-field-hint" style={{ marginTop: 8 }}>
                  Existing one-column files with <code className="bulk-code">address</code> also work. Quoted full addresses are safest, and common unquoted comma-address rows are supported where possible.
                </p>
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
                      Uploading CSV to the pilot bulk scorer...
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
                      {" "}Original columns are preserved where possible. Rows that cannot be found stay in the CSV with blank score fields and an error value such as <code className="bulk-code">address_not_found</code>.
                    </p>
                  </div>
                </Card>
              )}

              {pageState === "idle" && !resultCsv && (
                <div className="bulk-idle-hint">
                  <p>Upload a CSV to score up to {MAX_BATCH_ROWS} addresses.</p>
                  <p className="bulk-field-hint" style={{ marginTop: 8 }}>
                    The returned CSV includes your original columns, resolved_address, livability_score, disruption_score, confidence, evidence quality, severity fields, top risks, and row-level errors.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </Container>
    </main>
  );
}
