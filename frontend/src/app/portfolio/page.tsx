"use client";

/**
 * /portfolio — Multi-address workspace
 * task: data-014 (app lane exception — connects to /score API)
 *
 * Demo workspace: up to 10 addresses, persisted in localStorage.
 * Pilot access: higher-volume workflows by request.
 *
 * Table columns : Address · Score · Band · Top Risk · Updated · Actions
 * Features       : add, remove, per-row refresh, refresh-all, sort, CSV export.
 */

import React, {
  FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useUser } from "@clerk/nextjs";
import { Card, Container, Header } from "@/components/shell";
import { fetchScore, fetchSuggestions, ScoreResponse } from "@/lib/api";

// ── Constants ───────────────────────────────────────────────────────────────

const FREE_LIMIT = 10;
const FREE_BATCH_LIMIT = 5;
const PRO_BATCH_LIMIT = 500;
const CSV_TEMPLATE = "address\n1600 W Chicago Ave, Chicago, IL\n700 W Grand Ave, Chicago, IL\n233 S Wacker Dr, Chicago, IL\n";
const STORAGE_KEY = "lre_portfolio_v1";

// ── Types ───────────────────────────────────────────────────────────────────

type ScoreBand = "Minimal" | "Low" | "Moderate" | "High" | "Severe";
type SortCol = "address" | "score" | "band" | "updated";
type SortDir = "asc" | "desc";

type PortfolioItem = {
  id: string;
  address: string;
  disruption_score: number | null;
  score_band: ScoreBand | null;
  top_risk: string;
  confidence: string;
  mode: string;
  last_updated: string | null;
  is_loading: boolean;
  error: string | null;
};

// ── Helpers ─────────────────────────────────────────────────────────────────

const BAND_ORDER: Record<ScoreBand, number> = {
  Minimal: 0, Low: 1, Moderate: 2, High: 3, Severe: 4,
};

function scoreBand(score: number): ScoreBand {
  if (score <= 20) return "Minimal";
  if (score <= 40) return "Low";
  if (score <= 60) return "Moderate";
  if (score <= 80) return "High";
  return "Severe";
}

function bandColor(band: ScoreBand | null): string {
  switch (band) {
    case "Minimal":  return "#10b981";
    case "Low":      return "#3ce5b3";
    case "Moderate": return "#f59e0b";
    case "High":     return "#ef4444";
    case "Severe":   return "#7c3aed";
    default:         return "var(--text-muted, #64748b)";
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return "var(--text-muted, #64748b)";
  if (score >= 81) return "#7c3aed";
  if (score >= 61) return "#ef4444";
  if (score >= 41) return "#f59e0b";
  if (score >= 21) return "#3ce5b3";
  return "#10b981";
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function makeItem(address: string): PortfolioItem {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    address,
    disruption_score: null,
    score_band: null,
    top_risk: "",
    confidence: "",
    mode: "",
    last_updated: null,
    is_loading: true,
    error: null,
  };
}

function applyScore(item: PortfolioItem, score: ScoreResponse): PortfolioItem {
  return {
    ...item,
    disruption_score: score.disruption_score,
    score_band: scoreBand(score.disruption_score),
    top_risk: score.top_risks[0] ?? "",
    confidence: score.confidence,
    mode: score.mode ?? "live",
    last_updated: new Date().toISOString(),
    is_loading: false,
    error: null,
  };
}

// ── localStorage ─────────────────────────────────────────────────────────────

function loadStorage(): PortfolioItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as PortfolioItem[];
    // Reset any stale loading state from a previous session
    return parsed.map((item) => ({ ...item, is_loading: false }));
  } catch {
    return [];
  }
}

function saveStorage(items: PortfolioItem[]) {
  try {
    // Don't persist transient loading state
    const toStore = items.map((item) => ({ ...item, is_loading: false }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(toStore));
  } catch {
    // quota exceeded — ignore
  }
}

// ── CSV export ───────────────────────────────────────────────────────────────

function portfolioToCSV(items: PortfolioItem[]): string {
  const header = [
    "address", "disruption_score", "score_band",
    "top_risk", "confidence", "mode", "last_updated",
  ];
  const esc = (s: string) => `"${s.replace(/"/g, '""')}"`;
  const lines = [header.join(",")];
  for (const item of items) {
    lines.push([
      esc(item.address),
      item.disruption_score ?? "",
      item.score_band ?? "",
      esc(item.top_risk ?? ""),
      item.confidence ?? "",
      item.mode ?? "",
      item.last_updated ?? "",
    ].join(","));
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

// ── Component ────────────────────────────────────────────────────────────────

export default function PortfolioPage() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [hydrated, setHydrated] = useState(false);

  // Add-address input state
  const [inputAddr, setInputAddr] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggIdx, setActiveSuggIdx] = useState(-1);
  const [addError, setAddError] = useState<string | null>(null);
  const [isFocused, setIsFocused] = useState(false);

  const [sortCol, setSortCol] = useState<SortCol>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [isRefreshingAll, setIsRefreshingAll] = useState(false);
  const [riskFilter, setRiskFilter] = useState<"all" | "low" | "moderate" | "high">("all");
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number } | null>(null);

  // Tier detection
  const { user } = useUser();
  const tier = (user?.publicMetadata as Record<string, unknown>)?.subscription_tier as string | undefined;
  const isPro = tier === "pro" || tier === "teams" || tier === "enterprise";
  const batchLimit = isPro ? PRO_BATCH_LIMIT : FREE_BATCH_LIMIT;
  const csvUploadRef = useRef<HTMLInputElement>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const skipSuggestRef = useRef(false);
  const hasUserTyped = useRef(false);
  const abortRefreshRef = useRef(false);

  // ── Hydrate from localStorage ─────────────────────────────────────────────

  useEffect(() => {
    setItems(loadStorage());
    setHydrated(true);
  }, []);

  // ── Persist to localStorage whenever items change ─────────────────────────

  useEffect(() => {
    if (!hydrated) return;
    saveStorage(items);
  }, [items, hydrated]);

  // ── Autocomplete ─────────────────────────────────────────────────────────

  useEffect(() => {
    if (!hasUserTyped.current) return;
    if (skipSuggestRef.current) { skipSuggestRef.current = false; return; }
    if (inputAddr.trim().length < 3) {
      setSuggestions([]);
      setShowSuggestions(false);
      setActiveSuggIdx(-1);
      return;
    }
    const timer = setTimeout(async () => {
      const results = await fetchSuggestions(inputAddr);
      if (isFocused) {
        setSuggestions(results);
        setShowSuggestions(results.length > 0);
        setActiveSuggIdx(-1);
      }
    }, 300);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputAddr]);

  // ── Score a single item by id ─────────────────────────────────────────────

  const scoreItem = useCallback(async (id: string, address: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, is_loading: true, error: null } : item,
      ),
    );
    try {
      const result = await fetchScore(address);
      setItems((prev) =>
        prev.map((item) =>
          item.id === id ? applyScore(item, result.score) : item,
        ),
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Lookup failed.";
      setItems((prev) =>
        prev.map((item) =>
          item.id === id
            ? { ...item, is_loading: false, error: msg }
            : item,
        ),
      );
    }
  }, []);

  // ── Add address ───────────────────────────────────────────────────────────

  const addAddress = useCallback(
    async (addr: string) => {
      const trimmed = addr.trim();
      if (!trimmed) return;

      // Duplicate check
      if (items.some((item) => item.address.toLowerCase() === trimmed.toLowerCase())) {
        setAddError("This address is already in your portfolio.");
        return;
      }

      // Free-tier limit
      if (items.length >= FREE_LIMIT) {
        setAddError(`Demo workspace is limited to ${FREE_LIMIT} addresses. Request pilot access for higher-volume workflows.`);
        return;
      }

      setAddError(null);
      const newItem = makeItem(trimmed);
      setItems((prev) => [newItem, ...prev]);

      // Clear input
      skipSuggestRef.current = true;
      hasUserTyped.current = false;
      setInputAddr("");
      setSuggestions([]);
      setShowSuggestions(false);

      // Score immediately
      await scoreItem(newItem.id, trimmed);
    },
    [items, scoreItem],
  );

  // ── Remove address ────────────────────────────────────────────────────────

  const removeItem = useCallback((id: string) => {
    setItems((prev) => prev.filter((item) => item.id !== id));
  }, []);

  // ── CSV upload ────────────────────────────────────────────────────────────

  function downloadTemplate() {
    const blob = new Blob([CSV_TEMPLATE], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "portfolio_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleCSVUpload(file: File) {
    const text = await file.text();
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    // Skip header if it looks like one
    const startIdx = /^address$/i.test(lines[0] ?? "") ? 1 : 0;
    const addresses = lines.slice(startIdx).filter((l) => l.length > 5);

    if (addresses.length === 0) {
      setAddError("No valid addresses found in CSV.");
      return;
    }

    if (addresses.length > batchLimit) {
      setAddError(
        isPro
          ? `CSV contains ${addresses.length} addresses. Max ${PRO_BATCH_LIMIT} per upload.`
          : `Demo workspace allows ${FREE_BATCH_LIMIT} addresses per upload. Request pilot access for larger CSV workflows.`,
      );
      return;
    }

    setAddError(null);

    // Deduplicate against existing items
    const existing = new Set(items.map((i) => i.address.toLowerCase()));
    const newAddrs = addresses.filter((a) => !existing.has(a.toLowerCase()));
    if (newAddrs.length === 0) {
      setAddError("All addresses in this CSV are already in your portfolio.");
      return;
    }

    // Create items
    const newItems = newAddrs.map(makeItem);
    setItems((prev) => [...newItems, ...prev]);

    // Score sequentially with progress
    setBatchProgress({ current: 0, total: newItems.length });
    for (let i = 0; i < newItems.length; i++) {
      await scoreItem(newItems[i].id, newItems[i].address);
      setBatchProgress({ current: i + 1, total: newItems.length });
    }
    setBatchProgress(null);
  }

  // ── Refresh all ───────────────────────────────────────────────────────────

  const refreshAll = useCallback(async () => {
    if (isRefreshingAll || items.length === 0) return;
    abortRefreshRef.current = false;
    setIsRefreshingAll(true);
    const snapshot = [...items];
    for (const item of snapshot) {
      if (abortRefreshRef.current) break;
      await scoreItem(item.id, item.address);
    }
    setIsRefreshingAll(false);
  }, [isRefreshingAll, items, scoreItem]);

  // ── Sorting ───────────────────────────────────────────────────────────────

  function toggleSort(col: SortCol) {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortCol(col); setSortDir("desc"); }
  }

  function sortArrow(col: SortCol) {
    if (sortCol !== col) return " ↕";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  const sortedItems = useMemo(() => {
    let filtered = [...items];
    // Apply risk filter
    if (riskFilter !== "all") {
      filtered = filtered.filter((i) => {
        if (i.disruption_score === null) return false;
        if (riskFilter === "low") return i.disruption_score <= 30;
        if (riskFilter === "moderate") return i.disruption_score > 30 && i.disruption_score <= 60;
        if (riskFilter === "high") return i.disruption_score > 60;
        return true;
      });
    }
    filtered.sort((a, b) => {
      let cmp = 0;
      switch (sortCol) {
        case "address":
          cmp = a.address.localeCompare(b.address); break;
        case "score":
          cmp = (a.disruption_score ?? -1) - (b.disruption_score ?? -1); break;
        case "band":
          cmp = (BAND_ORDER[a.score_band ?? "Minimal"] ?? -1) -
                (BAND_ORDER[b.score_band ?? "Minimal"] ?? -1); break;
        case "updated":
          cmp = (a.last_updated ?? "").localeCompare(b.last_updated ?? ""); break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return filtered;
  }, [items, sortCol, sortDir, riskFilter]);

  // ── Keyboard handler for add-address input ────────────────────────────────

  function handleInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    const hasSugg = showSuggestions && suggestions.length > 0;
    if (e.key === "Escape") { setShowSuggestions(false); setActiveSuggIdx(-1); return; }
    if (!hasSugg) {
      if (e.key === "ArrowDown" && suggestions.length > 0) {
        setShowSuggestions(true); setActiveSuggIdx(0); e.preventDefault();
      }
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveSuggIdx((i) => (i + 1) % suggestions.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveSuggIdx((i) => (i <= 0 ? suggestions.length - 1 : i - 1));
    } else if (e.key === "Enter" && activeSuggIdx >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[activeSuggIdx]);
    }
  }

  function selectSuggestion(addr: string) {
    skipSuggestRef.current = true;
    hasUserTyped.current = false;
    setInputAddr(addr);
    setSuggestions([]);
    setShowSuggestions(false);
    setActiveSuggIdx(-1);
    inputRef.current?.focus();
  }

  // ── Derived stats ─────────────────────────────────────────────────────────

  const scored = items.filter((i) => i.disruption_score !== null);
  const avgScore = scored.length
    ? Math.round(scored.reduce((s, i) => s + (i.disruption_score ?? 0), 0) / scored.length)
    : null;
  const highestRisk = scored.length
    ? scored.reduce((a, b) => (b.disruption_score ?? 0) > (a.disruption_score ?? 0) ? b : a)
    : null;
  const atLimit = items.length >= FREE_LIMIT;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <main className="portfolio-page">
      <Container>
        {/* ── Top bar ────────────────────────────────────────────── */}
        <Header className="topbar">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">LR</div>
            <div>
              <p className="brand-title">Livability Intelligence</p>
              <p className="brand-subtitle">Illinois disruption intelligence</p>
            </div>
          </div>
          <nav className="topnav" aria-label="Primary">
            <a href="/" className="topnav-aux-link">← Scorer</a>
          </nav>
        </Header>

        {/* ── Page header ────────────────────────────────────────── */}
        <div className="portfolio-page-header">
          <div className="portfolio-title-row">
            <h1 className="portfolio-title">My Portfolio</h1>
            <span className="portfolio-plan-badge">Demo</span>
          </div>
          <p className="portfolio-subtitle">
            Track disruption scores across multiple addresses. Scores update on demand.
            {" "}<span className="portfolio-plan-note">Demo workspace: {items.length}/{FREE_LIMIT} addresses.</span>
          </p>
        </div>

        {/* ── Add address form ────────────────────────────────────── */}
        <Card className="portfolio-add-card">
          <form
            className="portfolio-add-form"
            onSubmit={(e: FormEvent<HTMLFormElement>) => {
              e.preventDefault();
              addAddress(inputAddr);
            }}
          >
            <label htmlFor="portfolio-addr-input" className="portfolio-add-label">
              Add address
            </label>
            <div className="portfolio-add-input-shell">
              <div className="search-input-stack portfolio-input-stack">
                <input
                  ref={inputRef}
                  id="portfolio-addr-input"
                  type="text"
                  className="portfolio-add-input"
                  placeholder="Enter a US address…"
                  value={inputAddr}
                  onChange={(e) => {
                    hasUserTyped.current = true;
                    setInputAddr(e.target.value);
                    setAddError(null);
                  }}
                  onFocus={() => setIsFocused(true)}
                  onBlur={() => {
                    setIsFocused(false);
                    setTimeout(() => setShowSuggestions(false), 150);
                  }}
                  onKeyDown={handleInputKeyDown}
                  autoComplete="off"
                  role="combobox"
                  aria-expanded={showSuggestions && suggestions.length > 0}
                  aria-controls="portfolio-suggestions"
                  aria-autocomplete="list"
                  aria-activedescendant={
                    activeSuggIdx >= 0 ? `portfolio-sugg-${activeSuggIdx}` : undefined
                  }
                  disabled={atLimit}
                />
                {showSuggestions && suggestions.length > 0 && (
                  <ul
                    id="portfolio-suggestions"
                    className="suggestion-list"
                    role="listbox"
                    aria-label="Address suggestions"
                  >
                    {suggestions.map((s, idx) => (
                      <li
                        key={s}
                        id={`portfolio-sugg-${idx}`}
                        role="option"
                        aria-selected={idx === activeSuggIdx}
                        className={`suggestion-item${idx === activeSuggIdx ? " suggestion-item--active" : ""}`}
                        onMouseDown={() => selectSuggestion(s)}
                        onMouseEnter={() => setActiveSuggIdx(idx)}
                      >
                        <span className="suggestion-item-label">{s}</span>
                        <span className="suggestion-item-meta">US address</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button
                type="submit"
                className="portfolio-add-btn"
                disabled={!inputAddr.trim() || atLimit}
              >
                Add address
              </button>
            </div>
            {addError && (
              <p className="portfolio-add-error" role="alert">{addError}</p>
            )}
            {atLimit && (
              <div className="portfolio-limit-banner">
                <span>Demo workspace limit reached ({FREE_LIMIT} addresses).</span>
                <a href="/pricing" className="portfolio-upgrade-link">
                  Request pilot access →
                </a>
              </div>
            )}
          </form>

          {/* CSV upload controls */}
          <div className="portfolio-csv-row">
            <input
              ref={csvUploadRef}
              type="file"
              accept=".csv"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleCSVUpload(file);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              className="portfolio-action-btn"
              onClick={() => csvUploadRef.current?.click()}
            >
              Upload CSV
            </button>
            <button
              type="button"
              className="portfolio-action-btn portfolio-action-btn--secondary"
              onClick={downloadTemplate}
            >
              Download template
            </button>
            <span className="portfolio-csv-hint">
              {isPro ? `Pilot: up to ${PRO_BATCH_LIMIT} addresses per upload` : `Demo: ${FREE_BATCH_LIMIT} addresses per upload`}
            </span>
          </div>

          {/* Batch progress */}
          {batchProgress && (
            <div className="portfolio-batch-progress">
              <div className="portfolio-batch-bar">
                <div
                  className="portfolio-batch-fill"
                  style={{ width: `${(batchProgress.current / batchProgress.total) * 100}%` }}
                />
              </div>
              <span className="portfolio-batch-label">
                Scoring {batchProgress.current} of {batchProgress.total} addresses...
              </span>
            </div>
          )}
        </Card>

        {/* ── Stats bar ───────────────────────────────────────────── */}
        {scored.length > 0 && (
          <div className="portfolio-stats-bar">
            <div className="portfolio-stat">
              <span className="portfolio-stat-label">Addresses</span>
              <span className="portfolio-stat-value">{items.length}</span>
            </div>
            {avgScore !== null && (
              <div className="portfolio-stat">
                <span className="portfolio-stat-label">Avg score</span>
                <span
                  className="portfolio-stat-value"
                  style={{ color: scoreColor(avgScore) }}
                >
                  {avgScore}
                </span>
              </div>
            )}
            {highestRisk && (
              <div className="portfolio-stat portfolio-stat--wide">
                <span className="portfolio-stat-label">Highest risk</span>
                <span
                  className="portfolio-stat-value portfolio-stat-value--addr"
                  style={{ color: scoreColor(highestRisk.disruption_score) }}
                >
                  {highestRisk.address}
                  <span className="portfolio-stat-score">
                    {" "}({highestRisk.disruption_score})
                  </span>
                </span>
              </div>
            )}
          </div>
        )}

        {/* ── Table ───────────────────────────────────────────────── */}
        {hydrated && items.length === 0 ? (
          <div className="portfolio-empty">
            <p className="portfolio-empty-kicker">No addresses yet</p>
            <p>Add up to {FREE_LIMIT} addresses above to start tracking disruption activity.</p>
            <p className="portfolio-empty-hint">
              Scores are fetched live from Chicago permit and street closure data.
            </p>
          </div>
        ) : (
          <Card className="portfolio-table-card">
            {/* Table toolbar */}
            <div className="portfolio-table-toolbar">
              <span className="portfolio-table-title">
                {items.length} address{items.length !== 1 ? "es" : ""}
                {scored.length < items.length && ` · ${items.length - scored.length} scoring…`}
              </span>
              <div className="portfolio-toolbar-actions">
                <select
                  className="portfolio-filter-select"
                  value={riskFilter}
                  onChange={(e) => setRiskFilter(e.target.value as typeof riskFilter)}
                >
                  <option value="all">All impact levels</option>
                  <option value="low">Low risk (0–30)</option>
                  <option value="moderate">Moderate (31–60)</option>
                  <option value="high">High risk (61+)</option>
                </select>
                <button
                  type="button"
                  className="portfolio-action-btn"
                  onClick={refreshAll}
                  disabled={isRefreshingAll || items.length === 0}
                  title="Re-score all addresses"
                >
                  {isRefreshingAll ? "Refreshing…" : "↻ Refresh all"}
                </button>
                {isRefreshingAll && (
                  <button
                    type="button"
                    className="portfolio-action-btn portfolio-action-btn--stop"
                    onClick={() => { abortRefreshRef.current = true; setIsRefreshingAll(false); }}
                  >
                    Stop
                  </button>
                )}
                <button
                  type="button"
                  className="portfolio-action-btn portfolio-action-btn--export"
                  onClick={() =>
                    downloadCSV(
                      portfolioToCSV(sortedItems),
                      `portfolio_${new Date().toISOString().slice(0, 10)}.csv`,
                    )
                  }
                  disabled={scored.length === 0}
                >
                  ↓ Export CSV
                </button>
              </div>
            </div>

            {/* Table */}
            <div className="portfolio-table-scroll">
              <table className="portfolio-table">
                <thead>
                  <tr>
                    <th
                      className="portfolio-th portfolio-th--sortable portfolio-th--addr"
                      onClick={() => toggleSort("address")}
                    >
                      Address{sortArrow("address")}
                    </th>
                    <th
                      className="portfolio-th portfolio-th--sortable portfolio-th--num"
                      onClick={() => toggleSort("score")}
                    >
                      Score{sortArrow("score")}
                    </th>
                    <th
                      className="portfolio-th portfolio-th--sortable"
                      onClick={() => toggleSort("band")}
                    >
                      Band{sortArrow("band")}
                    </th>
                    <th className="portfolio-th portfolio-th--wide">Top Risk</th>
                    <th
                      className="portfolio-th portfolio-th--sortable"
                      onClick={() => toggleSort("updated")}
                    >
                      Updated{sortArrow("updated")}
                    </th>
                    <th className="portfolio-th portfolio-th--actions" aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {sortedItems.map((item) => (
                    <tr key={item.id} className={`portfolio-tr${item.is_loading ? " portfolio-tr--loading" : ""}`}>
                      {/* Address */}
                      <td className="portfolio-td portfolio-td--addr">
                        <a
                          href={`/?address=${encodeURIComponent(item.address)}`}
                          className="portfolio-addr-link"
                          title="Open in scorer"
                        >
                          {item.address}
                        </a>
                      </td>

                      {/* Score */}
                      <td className="portfolio-td portfolio-td--num">
                        {item.is_loading ? (
                          <span className="portfolio-loading-dot" aria-label="Scoring…" />
                        ) : item.error ? (
                          <span className="portfolio-err-badge" title={item.error}>ERR</span>
                        ) : item.disruption_score !== null ? (
                          <strong
                            className="portfolio-score"
                            style={{ color: scoreColor(item.disruption_score) }}
                          >
                            {item.disruption_score}
                          </strong>
                        ) : (
                          <span className="portfolio-muted">—</span>
                        )}
                      </td>

                      {/* Band */}
                      <td className="portfolio-td">
                        {item.score_band && !item.is_loading ? (
                          <span
                            className="portfolio-band-pill"
                            style={{
                              background: `${bandColor(item.score_band)}22`,
                              color: bandColor(item.score_band),
                              border: `1px solid ${bandColor(item.score_band)}44`,
                            }}
                          >
                            {item.score_band}
                          </span>
                        ) : (
                          <span className="portfolio-muted">—</span>
                        )}
                      </td>

                      {/* Top Risk */}
                      <td className="portfolio-td portfolio-td--risk">
                        {item.error ? (
                          <span className="portfolio-err-text">{item.error}</span>
                        ) : (
                          <span className="portfolio-top-risk">
                            {item.top_risk || (item.is_loading ? "" : "—")}
                          </span>
                        )}
                      </td>

                      {/* Updated */}
                      <td className="portfolio-td portfolio-td--updated">
                        <span className="portfolio-muted">
                          {item.is_loading ? "Scoring…" : relativeTime(item.last_updated)}
                        </span>
                      </td>

                      {/* Actions */}
                      <td className="portfolio-td portfolio-td--actions">
                        <div className="portfolio-row-actions">
                          <button
                            type="button"
                            className="portfolio-refresh-btn"
                            onClick={() => scoreItem(item.id, item.address)}
                            disabled={item.is_loading}
                            title="Refresh score"
                            aria-label={`Refresh score for ${item.address}`}
                          >
                            ↻
                          </button>
                          <button
                            type="button"
                            className="portfolio-remove-btn"
                            onClick={() => removeItem(item.id)}
                            disabled={item.is_loading}
                            title="Remove from portfolio"
                            aria-label={`Remove ${item.address} from portfolio`}
                          >
                            ×
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pilot access prompt — below table when not at limit */}
            {!atLimit && items.length >= 6 && (
              <div className="portfolio-pro-hint">
                <span className="portfolio-pro-badge">Pilot</span>
                <span>
                  Higher-volume address lists, database sync, and webhook alerts are available by request.{" "}
                  <a href="/pricing" className="portfolio-upgrade-link">
                    Request pilot access →
                  </a>
                </span>
              </div>
            )}
          </Card>
        )}

        {/* ── Footer note ─────────────────────────────────────────── */}
        <p className="portfolio-footer-note">
          Portfolio stored locally in your browser. Scores reflect available permit, closure,
          and context data at the time of each refresh. Pilot workflows can add cloud sync and
          scheduled refresh by request.
        </p>
      </Container>
    </main>
  );
}
