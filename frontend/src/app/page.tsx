"use client";

import React, { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  CommuteChecker,
  ExplanationPanel,
  getConfidenceReasons,
  getMeaningInsights,
  ImpactWindow,
  MobileScoreView,
  NeighborhoodContextCard,
  ScoreHero,
  ScoreSparkline,
  SeverityMeters,
  SignalTimeline,
  TopRiskGrid,
  WatchlistForm,
} from "@/components/score-experience";
import { MapView } from "@/components/map-view";
import { Card, Container, Header, Section } from "@/components/shell";
import { track } from "@vercel/analytics";
import { SignedIn, SignedOut, SignInButton, UserButton, useUser } from "@clerk/nextjs";
import { fetchAddressDashboard, fetchAddressSuggestions, fetchHistory, fetchLiveSignals, fetchScore, geocodeForMap, getExportUrl, saveReport, ApiError, AddressSuggestion, LiveSignal, ScoreHistoryEntry, ScoreResponse, ScoreSource } from "@/lib/api";
import { headlineScore, impactTypeLabel } from "@/lib/score-utils";
import { getLookupUsage, recordLookup, isDemoAddress } from "@/lib/lookup-quota";
import { OnboardingModal, FeatureTour, useOnboardingState } from "@/components/onboarding";
import type { SelectedAddress } from "@/lib/address-types";

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";


const EXAMPLE_ADDRESSES = [
  "1600 W Chicago Ave, Chicago, IL",
  "700 W Grand Ave, Chicago, IL",
  "233 S Wacker Dr, Chicago, IL",
];

type SuggestionAddressParts = {
  street: string;
  city: string;
  state: string;
  zip: string;
};

function getSuggestionAddressParts(suggestion: AddressSuggestion): SuggestionAddressParts {
  const raw = suggestion.display_address ?? "";
  const parts = raw.split(",").map((part) => part.trim()).filter(Boolean);
  const street = parts[0] ?? raw;
  const city = suggestion.city ?? parts[1] ?? "";
  const stateZipRaw = parts[2] ?? "";
  const state = suggestion.state ?? (stateZipRaw.match(/\b([A-Za-z]{2})\b/)?.[1]?.toUpperCase() ?? "");
  const zip = suggestion.zip ?? (stateZipRaw.match(/\b(\d{5})\b/)?.[1] ?? "");
  return { street, city, state, zip };
}

function highlightMatch(text: string, query: string): React.ReactNode {
  const q = query.trim().toLowerCase();
  if (!q) return text;
  const normalizedQuery = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const matchIndex = text.toLowerCase().indexOf(q);
  if (matchIndex >= 0) {
    return (
      <>
        {text.slice(0, matchIndex)}
        <mark className="suggestion-highlight">{text.slice(matchIndex, matchIndex + q.length)}</mark>
        {text.slice(matchIndex + q.length)}
      </>
    );
  }
  const queryTokens = normalizedQuery.split(/\s+/).filter((token) => token.length >= 2);
  if (queryTokens.length === 0) return text;
  const tokenRegex = new RegExp(`(${queryTokens.join("|")})`, "ig");
  const chunks = text.split(tokenRegex);
  return chunks.map((chunk, index) => (
    queryTokens.includes(chunk.toLowerCase())
      ? <mark key={`${chunk}-${index}`} className="suggestion-highlight">{chunk}</mark>
      : <React.Fragment key={`${chunk}-${index}`}>{chunk}</React.Fragment>
  ));
}

function _relativeTime(dateStr: string): string {
  const d = new Date(dateStr);
  const now = Date.now();
  const diffMs = now - d.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 1) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return `${Math.floor(diffDays / 30)}mo ago`;
}

function debugSearchFlow(stage: string, payload: Record<string, unknown>) {
  if (typeof window === "undefined") return;
  const enabled =
    process.env.NEXT_PUBLIC_DEBUG_SEARCH_FLOW === "1" ||
    window.localStorage.getItem("lre_debug_search_flow") === "1";
  if (!enabled) return;
  console.info(`[DBG:${stage}]`, payload);
}

export default function HomePage() {
  const [address, setAddress] = useState("");
  const [result, setResult] = useState<ScoreResponse | null>(null);
  const [scoreSource, setScoreSource] = useState<ScoreSource>("live");
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [selectedAddress, setSelectedAddress] = useState<SelectedAddress | null>(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [mapCoords, setMapCoords] = useState<{ lat: number; lon: number } | null>(null);
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveEmail, setSaveEmail] = useState("");
  const [saveReportId, setSaveReportId] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [addressHistory, setAddressHistory] = useState<string[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [scoreHistory, setScoreHistory] = useState<ScoreHistoryEntry[]>([]);
  const [dashboardUnavailableReason, setDashboardUnavailableReason] = useState<string | null>(null);
  const [dashboardHydrationStatus, setDashboardHydrationStatus] = useState<"full" | "partial" | "unsupported" | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  // Debug mode: visible only when ?debug=true is in the URL. Never shown to users.
  const [isDebugMode, setIsDebugMode] = useState(false);
  // Live signals feed for landing page
  const [liveSignals, setLiveSignals] = useState<LiveSignal[]>([]);
  // Free-tier lookup gating
  const { user, isSignedIn } = useUser();
  const isPro = (user?.publicMetadata as Record<string, unknown>)?.subscription_tier === "pro";
  const [lookupUsage, setLookupUsage] = useState({ count: 0, limit: 10, remaining: 10, isGated: false });
  const [showGate, setShowGate] = useState(false);
  const [scoredAt, setScoredAt] = useState<Date | null>(null);
  // Onboarding
  const showOnboarding = useOnboardingState();
  const [onboardingVisible, setOnboardingVisible] = useState(false);
  const [showTour, setShowTour] = useState(false);
  useEffect(() => { setOnboardingVisible(showOnboarding); }, [showOnboarding]);
  // Mobile simplified view — reset to false on each new result so users always
  // land on the mobile summary first. Set to true when "Switch to full report" is tapped.
  const [mobileShowFull, setMobileShowFull] = useState(false);
  const searchShellRef = useRef<HTMLDivElement>(null);
  const historyShellRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const skipSuggestRef = useRef(false);
  const suggestRequestIdRef = useRef(0);
  const hydrationRequestIdRef = useRef(0);
  // Only fetch suggestions after the user has actually typed — prevents the
  // dropdown firing on mount or when an address is set programmatically.
  const hasUserTyped = useRef(false);
  const workspaceMode = isLoading || result !== null;
  const confidenceReasons = result ? getConfidenceReasons(result) : [];
  const meaningInsights = result ? getMeaningInsights(result) : [];
  const loadingSteps = [
    "Checking live availability",
    "Evaluating nearby permits and closures",
    "Building the disruption brief",
  ];
  const resultMode = result?.mode ?? scoreSource;
  const isDemoResult = resultMode === "demo";
  const statusHeadline = isDemoResult ? "Limited data coverage" : "Live score";
  const statusBadgeTooltip = isDemoResult
    ? "Live permit data may not be available for this address. Score is estimated from nearby signals."
    : undefined;
  const statusMessage = isDemoResult
    ? (statusNote ?? "Live permit data may not be available for this address. Score is estimated from nearby signals.")
    : "Live backend scoring is active for this address lookup.";
  const hasSuggestions = showSuggestions && suggestions.length > 0;
  const hasSuggestionPanel = showSuggestions;
  const activeSuggestionId = activeSuggestionIndex >= 0 ? `address-suggestion-${activeSuggestionIndex}` : undefined;

  type DetailItem = { label: string; value: string; isConfidence?: boolean };
  const supportingDetails = useMemo((): DetailItem[] => {
    if (!result) return [];
    const timeStr = scoredAt
      ? new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(scoredAt)
      : null;
    return [
      { label: "Data mode", value: isDemoResult ? "Limited data coverage" : "Live Chicago feed" },
      { label: "Confidence", value: result.confidence, isConfidence: true },
      { label: "Active signals detected", value: String(result.top_risks.length) },
      { label: "Sources", value: (() => {
        const IMPACT_LABELS: Record<string, string> = {
          closure_full: "Full street closure",
          closure_multi_lane: "Multi-lane closure",
          closure_single_lane: "Lane closure",
          demolition: "Demolition permit",
          construction: "Construction permit",
          light_permit: "Minor permit",
        };
        const signals = result.nearby_signals ?? [];
        const details = result.top_risk_details ?? [];
        const types = new Set<string>();
        for (const s of signals) if (s.impact_type) types.add(s.impact_type);
        for (const d of details) if (d.impact_type) types.add(d.impact_type);
        if (types.size === 0) return "Chicago permits • Street closures";
        return [...types].map(t => IMPACT_LABELS[t] ?? t).join(" • ");
      })() },
      ...(timeStr ? [{ label: "Scored at", value: timeStr }] : []),
    ];
  }, [isDemoResult, result, scoredAt]);
  const scoreTrend = useMemo<number | null>(() => {
    if (scoreHistory.length < 2) return null;
    const latest = scoreHistory[0] ? headlineScore(scoreHistory[0]) : undefined;
    const oldest = scoreHistory[scoreHistory.length - 1] ? headlineScore(scoreHistory[scoreHistory.length - 1]) : undefined;
    if (typeof latest !== "number" || typeof oldest !== "number") return null;
    return latest - oldest;
  }, [scoreHistory]);
  const amenities = useMemo(
    () => result?.amenities ?? result?.neighborhood_context?.amenities ?? {},
    [result],
  );

  // Hydrate address history from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem("lre_address_history");
      if (stored) setAddressHistory(JSON.parse(stored));
    } catch {
      // ignore parse errors
    }
  }, []);

  // Persist address history to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem("lre_address_history", JSON.stringify(addressHistory));
    } catch {
      // ignore storage quota errors
    }
  }, [addressHistory]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (searchShellRef.current && !searchShellRef.current.contains(event.target as Node)) {
        setShowSuggestions(false);
        setActiveSuggestionIndex(-1);
      }
      if (historyShellRef.current && !historyShellRef.current.contains(event.target as Node)) {
        setShowHistory(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Dev guard: warn if livability_score and disruption_score differ, which
  // means two components could render different numbers on the same page.
  // All score displays must use headlineScore() — never read fields directly.
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") return;
    if (!result) return;
    if (
      result.livability_score != null &&
      result.livability_score !== result.disruption_score
    ) {
      console.warn(
        `[ScoreConsistency] livability_score (${result.livability_score}) ≠ disruption_score (${result.disruption_score}). ` +
          `Headline renders ${headlineScore(result)}. ` +
          `All score displays must call headlineScore(result) — never reference disruption_score or livability_score directly for display.`
      );
    }
  }, [result]);

  // Read ?debug=true from URL after mount (client-side only).
  useEffect(() => {
    setIsDebugMode(new URLSearchParams(window.location.search).get("debug") === "true");
    // Load lookup usage from localStorage
    setLookupUsage(getLookupUsage(!!isSignedIn, isPro));
  }, [isSignedIn, isPro]);

  // Fetch live signals for landing page feed
  useEffect(() => {
    fetchLiveSignals().then(setLiveSignals);
  }, []);

  // Global keyboard shortcuts: Escape closes modal/history, "/" focuses input
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowSaveModal(false);
        setShowHistory(false);
      }
      if (
        event.key === "/" &&
        !["INPUT", "TEXTAREA", "SELECT"].includes((document.activeElement as HTMLElement)?.tagName ?? "")
      ) {
        event.preventDefault();
        inputRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Fetch autocomplete suggestions as the user types (debounced 300 ms).
  // Only runs when hasUserTyped is true — prevents the dropdown from opening
  // on mount or when an address is set programmatically (suggestion selection).
  // skipSuggestRef suppresses a single effect run after programmatic selection.
  useEffect(() => {
    if (!hasUserTyped.current) return;
    if (skipSuggestRef.current) {
      skipSuggestRef.current = false;
      return;
    }
    if (address.trim().length === 0) {
      setSuggestions([]);
      setShowSuggestions(false);
      setActiveSuggestionIndex(-1);
      return;
    }
    // For 1-2 chars show popular suggestions immediately (no wait) so the
    // dropdown never goes blank while the user starts typing.
    if (address.trim().length < 3) {
      const requestId = ++suggestRequestIdRef.current;
      setSuggestionsLoading(true);
      fetchAddressSuggestions("", { popular: true, limit: 5 }).then((results) => {
        if (requestId !== suggestRequestIdRef.current) return;
        if (isFocused && results.length > 0) {
          setSuggestions(results);
          setShowSuggestions(true);
          setActiveSuggestionIndex(-1);
        }
        setSuggestionsLoading(false);
      });
      return;
    }
    const timer = setTimeout(async () => {
      const requestId = ++suggestRequestIdRef.current;
      const queryAtRequest = address.trim();
      debugSearchFlow("SEARCH_INPUT", {
        typed_query: address,
        debounced_query: queryAtRequest,
        request_fired: true,
        request_id: requestId,
      });
      setSuggestionsLoading(true);
      setSuggestionsError(null);
      const results = await fetchAddressSuggestions(address, { limit: 8 });
      if (requestId !== suggestRequestIdRef.current || queryAtRequest !== address.trim()) {
        debugSearchFlow("SEARCH_RESPONSE", {
          source: "frontend.fetchAddressSuggestions",
          dropped: true,
          reason: "stale_response",
          request_id: requestId,
        });
        return;
      }
      // Only update if the input is still focused when results arrive.
      if (isFocused) {
        setSuggestions(results);
        setShowSuggestions(true);
        setActiveSuggestionIndex(-1);
      }
      if (results.length === 0) {
        setSuggestionsError(null);
      }
      setSuggestionsLoading(false);
    }, 150);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address]);

  useEffect(() => {
    document.title = result
      ? `${result.address} — Livability Intelligence`
      : "Livability Intelligence";
  }, [result]);

  useEffect(() => {
    if (!result) {
      setMapCoords(null);
      return;
    }
    if (result.latitude != null && result.longitude != null) {
      setMapCoords({ lat: result.latitude, lon: result.longitude });
      return;
    }
    geocodeForMap(result.address).then((coords) => {
      if (coords) setMapCoords(coords);
    });
  }, [result]);

  // data-025: fetch score history whenever a new result loads.
  useEffect(() => {
    if (!result) { setScoreHistory([]); return; }
    if (selectedAddress?.id) {
      const hydrationId = ++hydrationRequestIdRef.current;
      fetchAddressDashboard(selectedAddress.id, 30, {
        lat: selectedAddress.lat,
        lon: selectedAddress.lon,
        address: selectedAddress.label,
      }).then((payload) => {
        if (!payload) {
          if (hydrationId !== hydrationRequestIdRef.current) return;
          setScoreHistory([]);
          setDashboardHydrationStatus("partial");
          setDashboardUnavailableReason("Could not load address dashboard data.");
          return;
        }
        if (hydrationId !== hydrationRequestIdRef.current) return;
        const status = payload.status ?? (payload.available ? "full" : "partial");
        setDashboardHydrationStatus(status);
        if (status === "unsupported") {
          setScoreHistory([]);
          setDashboardUnavailableReason("This address is currently unsupported for dashboard hydration.");
          return;
        }
        if (!payload.available) {
          // Silently degrade — omit history section, no error shown to users.
          // Debug info only visible via ?debug=true URL param.
          setScoreHistory([]);
          setDashboardUnavailableReason(
            `reason=${payload.reason ?? "unknown"}`
            + (payload.modules_unavailable?.length ? ` modules=[${payload.modules_unavailable.join(",")}]` : ""),
          );
          return;
        }
        setDashboardUnavailableReason(null);
        setScoreHistory(
          payload.history.map((h) => ({
            disruption_score: h.disruption_score,
            livability_score: h.livability_score,
            confidence: h.confidence,
            mode: h.mode as import("../lib/api").ScoreMode,
            created_at: h.scored_at,
          })),
        );
      });
      return;
    }

    setDashboardHydrationStatus(null);
    fetchHistory(result.address, 30).then((r) =>
      setScoreHistory(
        r
          ? r.history.map((h) => ({
              disruption_score: h.disruption_score,
              livability_score: h.livability_score,
              confidence: h.confidence,
              mode: h.mode as import("../lib/api").ScoreMode,
              created_at: h.scored_at,
            }))
          : [],
      ),
    );
  }, [result, selectedAddress]);

  useEffect(() => {
    debugSearchFlow("FINAL_RENDER", {
      dashboard_status: dashboardHydrationStatus,
      has_result: Boolean(result),
      history_count: scoreHistory.length,
      dashboard_unavailable: Boolean(dashboardUnavailableReason),
    });
  }, [dashboardHydrationStatus, dashboardUnavailableReason, result, scoreHistory.length]);

  useEffect(() => {
    debugSearchFlow("DROPDOWN_RENDER", {
      input: address,
      show_suggestions: showSuggestions,
      suggestion_count: suggestions.length,
      loading: suggestionsLoading,
      error: suggestionsError,
      has_panel: hasSuggestionPanel,
      has_suggestions: hasSuggestions,
    });
  }, [address, hasSuggestionPanel, hasSuggestions, showSuggestions, suggestions.length, suggestionsError, suggestionsLoading]);

  function toManualSuggestion(displayAddress: string): AddressSuggestion {
    return {
      canonical_id: null,
      display_address: displayAddress,
      lat: null,
      lon: null,
    };
  }

  function handleSuggestionSelect(suggestion: AddressSuggestion, options: { submit?: boolean } = { submit: true }) {
    const parts = getSuggestionAddressParts(suggestion);
    const selected: SelectedAddress = {
      id: suggestion.canonical_id ?? null,
      label: suggestion.display_address,
      lat: suggestion.lat ?? null,
      lon: suggestion.lon ?? null,
      city: parts.city,
      state: parts.state,
      zip: parts.zip || undefined,
    };
    debugSearchFlow("SELECTION", { ...selected, raw: suggestion });
    track("suggestion_selected", { address: suggestion.display_address, canonical_id: suggestion.canonical_id });
    skipSuggestRef.current = true;
    hasUserTyped.current = false;   // treat the fill as programmatic
    setSelectedAddress(selected);
    setError(null);
    setSuggestionsError(null);
    setDashboardUnavailableReason(null);
    setDashboardHydrationStatus(null);
    setAddress(suggestion.display_address);
    setSuggestions([]);
    setShowSuggestions(false);
    setActiveSuggestionIndex(-1);
    inputRef.current?.focus();
    if (options.submit !== false) {
      void submitAddress(suggestion.display_address);
    }
  }

  function handleInputKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!hasSuggestions) {
      if (event.key === "ArrowDown" && suggestions.length > 0) {
        setShowSuggestions(true);
        setActiveSuggestionIndex(0);
        event.preventDefault();
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current + 1) % suggestions.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
    } else if (event.key === "Enter" && activeSuggestionIndex >= 0) {
      event.preventDefault();
      handleSuggestionSelect(suggestions[activeSuggestionIndex]);
    } else if (event.key === "Escape") {
      setShowSuggestions(false);
      setActiveSuggestionIndex(-1);
    }
  }

  async function submitAddress(addr: string) {
    // Free-tier gate: check quota before making the request.
    // Demo addresses are never gated.
    if (!isDemoAddress(addr)) {
      const usage = getLookupUsage(!!isSignedIn, isPro);
      if (usage.isGated) {
        setShowGate(true);
        return;
      }
    }

    debugSearchFlow("SEARCH_REQUEST", {
      request_fired: true,
      identifier_type: selectedAddress?.id ? "canonical_id" : "address_text",
      identifier: selectedAddress?.id ?? addr,
      display_address: selectedAddress?.label ?? addr,
    });
    track("address_analyzed", { address: addr });
    setIsLoading(true);
    setError(null);
    setDashboardUnavailableReason(null);
    setDashboardHydrationStatus(null);
    setMobileShowFull(false);
    try {
      const scoreResult = await fetchScore(addr, {
        canonicalId: selectedAddress?.id ?? null,
        lat: typeof selectedAddress?.lat === "number" ? selectedAddress.lat : undefined,
        lon: typeof selectedAddress?.lon === "number" ? selectedAddress.lon : undefined,
        lat: selectedAddress?.lat ?? null,
        lon: selectedAddress?.lon ?? null,
      });
      setResult(scoreResult.score);
      setScoredAt(new Date());
      setScoreSource(scoreResult.source);
      if ("note" in scoreResult && scoreResult.note) {
        setStatusNote(scoreResult.note);
      } else {
        setStatusNote(null);
      }
      // Track address history (last 5, deduplicated)
      setAddressHistory((prev: string[]) => {
        const deduped = [addr, ...prev.filter((a: string) => a !== addr)];
        return deduped.slice(0, 5);
      });
      // Record lookup for quota tracking (demo addresses exempt)
      if (!isDemoAddress(addr)) {
        const updated = recordLookup(!!isSignedIn, isPro);
        setLookupUsage(updated);
      }
    } catch (submissionError) {
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Live data temporarily unavailable. Try again in a moment.",
      );
      setResult(null);
      setStatusNote(null);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAddress(address);
  }

  async function handleSaveReport() {
    if (!result) return;
    setIsSaving(true);
    setSaveError(null);
    setSaveReportId(null);
    try {
      const saved = await saveReport(result);
      setSaveReportId(saved.report_id);
    } catch (err) {
      setSaveError(
        err instanceof ApiError
          ? err.message
          : "Could not save report. Please try again.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  function handleCopySavedLink() {
    if (!saveReportId) return;
    const url = `${window.location.origin}/report/${saveReportId}`;
    navigator.clipboard.writeText(url).then(() => {
      setCopiedLink(true);
      setTimeout(() => setCopiedLink(false), 2000);
    });
  }

  function handleOpenSaveModal() {
    setSaveReportId(null);
    setSaveError(null);
    setShowSaveModal(true);
  }

  return (
    <main className={`page ${workspaceMode ? "page--workspace" : "page--explore"}`}>
      <a href="#address" className="skip-link">Skip to address search</a>
      <Container>
        <Header className={`topbar ${workspaceMode ? "topbar--workspace" : ""}`}>
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">
              LR
            </div>
            <div>
              <p className="brand-title">Livability Intelligence</p>
              <p className="brand-subtitle">Address intelligence for real estate and operations teams</p>
            </div>
          </div>

          <nav className={`topnav${workspaceMode ? " topnav--workspace" : ""}`} aria-label="Primary">
            {workspaceMode ? <span className="topnav-label">Viewing</span> : null}
            {workspaceMode ? (
              <a href="#" className="topnav-address" onClick={(e: React.MouseEvent) => { e.preventDefault(); window.scrollTo({ top: 0, behavior: "smooth" }); }} title="Scroll to top">
                {result?.address ?? address}
              </a>
            ) : null}
            {workspaceMode && addressHistory.length > 1 ? (
              <div className="history-dropdown-shell" ref={historyShellRef}>
                <button
                  type="button"
                  className="history-btn"
                  onClick={() => setShowHistory((v: boolean) => !v)}
                  aria-expanded={showHistory}
                  aria-label="Recent addresses"
                >
                  🕐 Recent
                </button>
                {showHistory ? (
                  <ul className="history-dropdown" role="listbox" aria-label="Recent addresses">
                    {addressHistory.slice(1).map((hist: string) => (
                      <li key={hist} role="option" aria-selected={false}>
                        <button type="button" onClick={() => { handleSuggestionSelect(toManualSuggestion(hist)); setShowHistory(false); }}>
                          {hist}
                        </button>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}
            <a href="#score-section" className="topnav-aux-link">Score</a>
            <a href="#signals-section" className="topnav-aux-link">Signals</a>
            <a href="#examples-section" className="topnav-aux-link">Examples</a>
            <a href="#pricing-section" className="topnav-pricing">Pricing</a>
            <a href="/portfolio" className="topnav-aux-link">Portfolio</a>
            <a href="/api-docs" className="topnav-aux-link">Docs</a>
            <a href="/methodology" className="topnav-aux-link">Methodology</a>
            <a href="/api-access" className="topnav-api-link">API</a>
            <SignedOut>
              <SignInButton mode="modal">
                <button type="button" className="topnav-sign-in">Sign In</button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <a href="/account" className="topnav-aux-link">Account</a>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </nav>
        </Header>

        <Section className={`hero-section ${workspaceMode ? "hero-section--workspace" : ""}`}>
          <Card tone="highlighted" className="hero-card">
            <div className={`hero-copy ${workspaceMode ? "hero-copy--workspace" : ""}`}>
              <p className="eyebrow">Address Intelligence Platform</p>
              <h1>
                {workspaceMode
                  ? "A decision-ready livability brief for the current address."
                  : "Address intelligence for teams that need to know before they move."}
              </h1>
              <p className="lede">
                {workspaceMode
                  ? "Run another lookup below. Score, reasoning, and spatial context update automatically."
                  : "Livability scores powered by 20+ live data sources \u2014 construction permits, crime trends, school ratings, transit, and environmental risk. Updated daily across 50+ US cities."}
              </p>
              {!workspaceMode && (
                <a href="mailto:enterprise@livabilityrisks.com" className="enterprise-cta">
                  Request enterprise demo →
                </a>
              )}
            </div>

            <form className={`lookup-form ${workspaceMode ? "lookup-form--workspace" : ""}`} onSubmit={handleSubmit}>
              <label htmlFor="address" className="input-label">
                {workspaceMode ? "Search another address" : "Enter any US address"}
              </label>
              <div ref={searchShellRef} className={`search-shell ${workspaceMode ? "search-shell--workspace" : ""}`}>
                <div className="search-input-stack">
                  <input
                    ref={inputRef}
                    id="address"
                    name="address"
                    type="text"
                    value={address}
                    onChange={(event) => {
                      hasUserTyped.current = true;
                      setSelectedAddress(null);
                      setError(null);
                      setDashboardUnavailableReason(null);
                      setDashboardHydrationStatus(null);
                      debugSearchFlow("SEARCH_INPUT", {
                        typed_query: event.target.value,
                        debounced_query: null,
                        request_fired: false,
                      });
                      setAddress(event.target.value);
                    }}
                    onFocus={() => {
                      setIsFocused(true);
                      if (address.trim().length < 3) {
                        setSuggestionsLoading(true);
                        setSuggestionsError(null);
                        fetchAddressSuggestions("", { popular: true, limit: 5 })
                          .then((results) => {
                            setSuggestions(results);
                            setShowSuggestions(true);
                            setActiveSuggestionIndex(-1);
                          })
                          .catch(() => {
                            setSuggestionsError("Could not load suggestions.");
                          })
                          .finally(() => setSuggestionsLoading(false));
                      }
                    }}
                    onBlur={() => {
                      setIsFocused(false);
                      setTimeout(() => setShowSuggestions(false), 150);
                    }}
                    onKeyDown={handleInputKeyDown}
                    placeholder="Search any US address"
                    autoComplete="off"
                    role="combobox"
                    aria-expanded={hasSuggestionPanel}
                    aria-controls="address-suggestions"
                    aria-activedescendant={activeSuggestionId}
                    aria-autocomplete="list"
                    required
                    style={address.length > 0 && !isLoading ? { paddingRight: "44px" } : undefined}
                  />
                  {address.length > 0 && !isLoading && (
                    <button
                      type="button"
                      className="input-clear-btn"
                      aria-label="Clear address"
                      onClick={() => {
                        setAddress("");
                        setSuggestions([]);
                        setShowSuggestions(false);
                        setError(null);
                        setDashboardUnavailableReason(null);
                        setDashboardHydrationStatus(null);
                        hasUserTyped.current = false;
                        inputRef.current?.focus();
                      }}
                    >
                      ×
                    </button>
                  )}
                  {showSuggestions ? (
                    <ul id="address-suggestions" className="suggestion-list" role="listbox" aria-label="Address suggestions">
                      {suggestionsLoading ? (
                        <li className="suggestion-item suggestion-item--status" role="option" aria-disabled="true">
                          <span className="suggestion-loading-dot" aria-hidden="true" />
                          <span className="suggestion-item-label">Finding best matches…</span>
                          <span className="suggestion-item-meta">Searching trusted backend addresses</span>
                        </li>
                      ) : suggestionsError ? (
                        <li className="suggestion-item suggestion-item--status" role="option" aria-disabled="true">
                          <span className="suggestion-item-label">{suggestionsError}</span>
                          <span className="suggestion-item-meta">Try again or continue with full address + ZIP</span>
                        </li>
                      ) : suggestions.length === 0 ? (
                        <li className="suggestion-item suggestion-item--status" role="option" aria-disabled="true">
                          <span className="suggestion-item-label">
                            {address.trim().length < 3 ? "Start typing to search addresses" : "No trusted matches found yet"}
                          </span>
                          <span className="suggestion-item-meta">
                            {address.trim().length < 3
                              ? "Use street number + street name (for example: 1600 W Chicago Ave)"
                              : `Try adding city/state or ZIP for “${address.trim()}”`}
                          </span>
                        </li>
                      ) : suggestions.map((suggestion, index) => (
                        (() => {
                          const addr = getSuggestionAddressParts(suggestion);
                          const locality = [addr.city, addr.state, addr.zip].filter(Boolean).join(", ").replace(", ,", ",");
                          const isActive = index === activeSuggestionIndex;
                          const isSelected = Boolean(selectedAddress?.id) && selectedAddress?.id === suggestion.canonical_id;
                          return (
                        <li
                          key={suggestion.canonical_id ?? `${suggestion.display_address}-${index}`}
                          id={`address-suggestion-${index}`}
                          role="option"
                          aria-selected={isActive}
                          className={`suggestion-item ${isActive ? "suggestion-item--active" : ""} ${isSelected ? "suggestion-item--selected" : ""}`}
                          onMouseDown={() => handleSuggestionSelect(suggestion)}
                          onMouseEnter={() => setActiveSuggestionIndex(index)}
                        >
                          <span className="suggestion-item-label">{highlightMatch(addr.street, address)}</span>
                          <span className="suggestion-item-subline">{highlightMatch(locality || suggestion.display_address, address)}</span>
                          <span className="suggestion-item-meta">{isSelected ? "Selected" : "Indexed address"}</span>
                        </li>
                        );
                        })()
                      ))}
                    </ul>
                  ) : null}
                </div>
                <button type="submit" disabled={isLoading}>
                  {isLoading ? "Analyzing…" : "Analyze address"}
                </button>
              </div>
              <div className={`hero-support ${workspaceMode ? "hero-support--workspace" : ""}`}>
                <p className="form-hint">
                  Returns a livability score, severity read, strongest drivers, interpretation, and map context for any address.
                </p>
                <p className="form-disclaimer">
                  Live data active for select cities. Coverage expanding daily.
                </p>

                <div className="example-row">
                  <span className="example-label">Quick example</span>
                  <div className="example-chip-group">
                    {EXAMPLE_ADDRESSES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        className="example-chip"
                        onClick={() => handleSuggestionSelect(toManualSuggestion(example), { submit: true })}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </form>

            {/* Free-tier usage indicator — only shown for non-Pro users */}
            {!isPro && lookupUsage.count > 0 && (
              <p className="lookup-usage-indicator">
                {lookupUsage.count}/{lookupUsage.limit} free lookups used this month
              </p>
            )}

            {/* Gate overlay — shown when free-tier limit is reached */}
            {showGate && (
              <div className="gate-overlay" role="alert">
                <div className="gate-overlay-card">
                  <p className="gate-overlay-icon">🔒</p>
                  <h3>
                    {isSignedIn
                      ? `You\u2019ve used your ${lookupUsage.limit} free lookups this month.`
                      : `Sign up to get ${10} free lookups per month.`}
                  </h3>
                  <p>
                    {isSignedIn
                      ? "Upgrade to Pro for unlimited address lookups, batch analysis, and PDF exports."
                      : `You\u2019ve used ${lookupUsage.count} of ${lookupUsage.limit} free lookups. Create a free account to get more, or upgrade to Pro for unlimited access.`}
                  </p>
                  <div className="gate-overlay-actions">
                    {isSignedIn ? (
                      <a href="#pricing-section" className="gate-btn gate-btn--primary" onClick={() => setShowGate(false)}>
                        See Pro plan
                      </a>
                    ) : (
                      <SignInButton mode="modal">
                        <button type="button" className="gate-btn gate-btn--primary">
                          Sign up free
                        </button>
                      </SignInButton>
                    )}
                    <button type="button" className="gate-btn gate-btn--secondary" onClick={() => setShowGate(false)}>
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(result || statusNote) ? (
              <div className={`status-banner ${isDemoResult ? "status-banner--demo" : "status-banner--live"}`} role="status">
                <span className="status-badge" title={statusBadgeTooltip}>{statusHeadline}</span>
                <div className="status-copy">
                  <strong>{statusMessage}</strong>
                  {" "}
                  <span>{isDemoResult ? "" : "Sources: Chicago permits • Street closures"}</span>
                </div>
              </div>
            ) : null}

            {error ? (
              <div className="feedback-banner" role="alert">
                <p className="feedback-title">
                  {error.toLowerCase().includes("not found") || error.toLowerCase().includes("couldn't find")
                    ? "Address not found"
                    : "Lookup unavailable"}
                </p>
                <p>
                  {error.toLowerCase().includes("not found") || error.toLowerCase().includes("couldn't find")
                    ? "We couldn't find that address in Illinois. Try including a ZIP code."
                    : error.toLowerCase().includes("not configured") || error.toLowerCase().includes("next_public")
                      ? "Scoring service is currently unavailable. Please try again later."
                      : error}
                </p>
              </div>
            ) : null}

            {/* Dashboard hydration failures degrade silently — history section is
                simply omitted when unavailable. Debug info requires both
                ?debug=true URL param AND signed-in user. */}
            <SignedIn>
              {isDebugMode && dashboardUnavailableReason && (
                <details style={{ marginTop: "0.75rem", fontSize: "0.75rem", opacity: 0.7 }}>
                  <summary style={{ cursor: "pointer", userSelect: "none" }}>
                    [debug] dashboard hydration: {dashboardHydrationStatus ?? "unknown"}
                  </summary>
                  <pre style={{ margin: "6px 0 0", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {JSON.stringify({ status: dashboardHydrationStatus, reason: dashboardUnavailableReason, history_count: scoreHistory.length }, null, 2)}
                  </pre>
                </details>
              )}
            </SignedIn>
          </Card>
        </Section>

        {/* ── How it works — only shown on the explore (pre-search) hero ── */}
        {!workspaceMode && (
          <Section
            eyebrow="How it works"
            title="From address to livability brief in seconds"
            description="Three steps. No account required."
            className="how-it-works-section"
          >
            <div className="how-it-works-grid">
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">01</div>
                <h3 className="hiw-step-title">Enter any address</h3>
                <p className="hiw-step-body">
                  Type a street address in any of our 12 supported US cities. We geocode it instantly and anchor every data source to the exact location.
                </p>
              </div>
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">02</div>
                <h3 className="hiw-step-title">We analyze 20+ live data sources</h3>
                <p className="hiw-step-body">
                  Construction permits, street closures, crime trends, school ratings, flood zones, census demographics — all queried in real time and scored within a 500-meter radius.
                </p>
              </div>
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">03</div>
                <h3 className="hiw-step-title">Get a decision-ready livability brief</h3>
                <p className="hiw-step-body">
                  A 0–100 livability score, severity read across noise, traffic, and construction, the strongest nearby signals, and a plain-English explanation — ready to share or export.
                </p>
              </div>
            </div>
          </Section>
        )}

        {/* ── Value proposition tiles — only shown on explore (pre-search) ── */}
        {!workspaceMode && (
          <section className="value-prop-section">
            <div className="value-prop-grid">
              <div className="value-prop-tile">
                <span className="value-prop-icon" aria-hidden="true">🏠</span>
                <h3>Real estate due diligence</h3>
                <p>Score any address before a lease signing, purchase, or investment. Surface construction, crime, school, and environmental risks that aren't in the listing.</p>
              </div>
              <div className="value-prop-tile">
                <span className="value-prop-icon" aria-hidden="true">📊</span>
                <h3>Portfolio risk monitoring</h3>
                <p>Track livability scores across your entire portfolio. Get alerted when new construction permits, crime trends, or infrastructure changes affect your properties.</p>
              </div>
              <div className="value-prop-tile">
                <span className="value-prop-icon" aria-hidden="true">🚛</span>
                <h3>Logistics &amp; operations planning</h3>
                <p>Assess access disruptions before routing, scheduling deliveries, or planning site visits. Know about lane closures and construction before your team arrives.</p>
              </div>
            </div>
          </section>
        )}

        {/* ── Live signals feed — landing page only ───────────── */}
        {!workspaceMode && liveSignals.length > 0 && (
          <section className="live-signals-section">
            <p className="live-signals-eyebrow">
              <span className="live-dot" aria-hidden="true" />
              Live across 50+ cities
            </p>
            <div className="live-signals-feed">
              {liveSignals.slice(0, 8).map((sig, i) => (
                <div key={`${sig.address}-${i}`} className="live-signal-item">
                  <span className="live-dot live-dot--small" aria-hidden="true" />
                  <div className="live-signal-body">
                    <span className="live-signal-city">{sig.city}</span>
                    <span className="live-signal-type">{impactTypeLabel(sig.impact_type)}</span>
                    <span className="live-signal-addr">{sig.title || sig.address}</span>
                    {sig.start_date && (
                      <span className="live-signal-time">
                        {_relativeTime(sig.start_date)}
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        <Section
          className={workspaceMode ? "workspace-section workspace-section--score" : undefined}
          eyebrow="Score"
          title={workspaceMode ? "Decision brief" : "What the score returns"}
          description={
            workspaceMode
              ? "Read the headline score first, then move directly into interpretation, strongest drivers, and supporting context."
              : "A single lookup returns the headline score, why it matters, and the supporting context behind it."
          }
          headerAction={workspaceMode && result ? (
            <a
              href="#pricing-section"
              className="icon-btn"
              title="PDF export is available on the Pro plan"
            >
              ↓ Export PDF
            </a>
          ) : undefined}
        >
          <div id="score-section" className="anchor-target" />
          <div aria-live="polite" aria-atomic="false">
          {isLoading ? (
            <section className="results results--loading">
              <Card className="score-card skeleton-card loading-card">
                <p className="loading-kicker">Building disruption brief</p>
                <div className="loading-step-list" aria-live="polite">
                  {loadingSteps.map((step, index) => (
                    <div key={step} className="loading-step">
                      <span className="loading-step-index">0{index + 1}</span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
                <p className="loading-support">Checking live availability first, then assembling a concise address-level brief.</p>
                <div className="skeleton skeleton-score" />
                <div className="skeleton skeleton-meta" />
              </Card>

              <div className="detail-grid">
                <Card className="detail-card skeleton-card">
                  <div className="skeleton skeleton-title" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line short" />
                </Card>

                <Card className="detail-card skeleton-card">
                  <div className="skeleton skeleton-title" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line" />
                  <div className="skeleton skeleton-line short" />
                </Card>
              </div>
            </section>
          ) : result ? (
            <section className="results results--loaded workspace-flow">
              {/* ── Mobile simplified view (CSS-hidden on desktop ≥ 768px) ── */}
              {!mobileShowFull && (
                <div className="mobile-view">
                  <MobileScoreView
                    result={result}
                    onShowFull={() => setMobileShowFull(true)}
                  />
                </div>
              )}

              {/* ── Full desktop results (CSS-hidden on mobile unless mobileShowFull) ── */}
              <div className={`desktop-view${!mobileShowFull ? " desktop-view--mobile-hidden" : ""}`}>
              {headlineScore(result) >= 61 && (
                <div className="pro-badge-bar">
                  <span className="pro-badge-icon">⚠</span>
                  <span>
                    <strong>High-risk address detected.</strong> Pro users get 30-day forecasts and permit detail exports.{" "}
                    <a href="#pricing-section" className="pro-badge-link">See Pro plan →</a>
                  </span>
                </div>
              )}

              <div className="workspace-top-grid">
                <Card className="score-card">
                  <ScoreHero result={result} />
                  {scoreHistory.length >= 1 && (
                    <ScoreSparkline history={scoreHistory} currentScore={headlineScore(result)} />
                  )}
                  <div className="score-actions">
                    <button type="button" className="action-btn" onClick={handleOpenSaveModal}>
                      Save report
                    </button>
                    <a
                      href="#"
                      className="compare-link"
                      onClick={(e) => {
                        e.preventDefault();
                        inputRef.current?.focus();
                        inputRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                      }}
                    >
                      Compare with another address →
                    </a>
                  </div>
                </Card>
                <Card className="detail-card detail-card--summary">
                  <h2>Why this score</h2>
                  <ExplanationPanel explanation={result.explanation} meaning={meaningInsights} />
                </Card>
              </div>

              {/* ── Monitor this address — shown for score >= 50 ─────────── */}
              {headlineScore(result) >= 50 && (
                <WatchlistForm address={result.address} score={headlineScore(result)} />
              )}

              {/* ── Check my commute ─────────────────────────────────────── */}
              <CommuteChecker homeAddress={result.address} />

              <div className="detail-grid detail-grid--balanced">
                <Card className="detail-card">
                  <h2>Confidence and severity</h2>
                  <SeverityMeters severity={result.severity} confidence={result.confidence} confidenceReasons={confidenceReasons} />
                </Card>
                <Card className="detail-card supporting-card">
                  <p className="supporting-kicker">Quick read</p>
                  <ul className="supporting-list supporting-list--compact">
                    {supportingDetails.map((item) => (
                      <li key={item.label}>
                        <span>{item.label}</span>
                        {"isConfidence" in item && item.isConfidence ? (
                          <strong className="confidence-value">
                            <span className={`confidence-dot confidence-dot--${item.value.toLowerCase()}`} aria-hidden="true" />
                            {item.value}
                          </strong>
                        ) : (
                          <strong>{item.value}</strong>
                        )}
                      </li>
                    ))}
                  </ul>
                </Card>
              </div>

              {/* ── Neighborhood context ─────────────────────────────────── */}
              <Card className="detail-card">
                <NeighborhoodContextCard
                  result={result}
                  scoreHistory={scoreHistory}
                  lat={mapCoords?.lat ?? result.latitude}
                  lon={mapCoords?.lon ?? result.longitude}
                />
              </Card>

              {/* ── Full-width map panel, pinned below the headline score ── */}
              <Card className="detail-card map-card">
                <div className="map-card-head">
                  <div>
                    <p className="map-kicker">Spatial context</p>
                    <h2>Address and nearby area</h2>
                  </div>
                  <span className="map-badge">CARTO Dark</span>
                </div>
                {mapCoords ? (
                  <MapView
                    latitude={mapCoords.lat}
                    longitude={mapCoords.lon}
                    address={result.address}
                    disruptionScore={headlineScore(result)}
                    signals={result.nearby_signals ?? []}
                    schools={result.nearby_schools ?? []}
                    amenities={amenities}
                    topRiskDetails={result.top_risk_details ?? []}
                    nearbySchools={result.nearby_schools ?? []}
                    floodRisk={result.neighborhood_context?.flood_risk ?? null}
                    femaZone={result.neighborhood_context?.fema_flood_zone ?? null}
                    isPro={false}
                  />
                ) : (
                  <div className="map-placeholder" aria-label="Locating address on map…">
                    <div className="map-grid" />
                    <div className="map-pin map-pin--primary" />
                  </div>
                )}
                <p className="map-copy">
                  Toggle between signal circles (click for source, date range, and impact type) and the disruption heatmap.
                  Pro plan unlocks the 30-day forecast animation.
                </p>
              </Card>

              <div id="signals-section" className="anchor-target" />
              <Section
                eyebrow="Signals"
                title="Strongest supporting drivers"
                description="These are the clearest nearby signals behind the score, along with timeline context that helps interpret them."
                className="workspace-subsection"
              >
                <Card className="detail-card drivers-card">
                  <TopRiskGrid result={result} />
                </Card>
                {(result.top_risk_details ?? []).length > 0 && (
                  <Card className="detail-card">
                    <SignalTimeline details={result.top_risk_details ?? []} />
                  </Card>
                )}
              </Section>

              <div className="detail-grid detail-grid--balanced">
                <Card className="detail-card">
                  <ImpactWindow result={result} />
                </Card>
                <Card className="detail-card supporting-card">
                  <p className="supporting-kicker">Review notes</p>
                  <ul className="supporting-list">
                    <li>
                      <span>Interpretation</span>
                      <strong>This score reflects near-term conditions, not long-term neighborhood quality.</strong>
                    </li>
                    <li>
                      <span>Best use</span>
                      <strong>Helpful for screening addresses before site visits, planning, or stakeholder review.</strong>
                    </li>
                  </ul>
                </Card>
              </div>
              </div>{/* end desktop-view */}
            </section>
          ) : (
            <section className="results">
              <Card className="empty-state">
                <p className="empty-kicker">Ready for analysis</p>
                <h3>Enter an Illinois address above to get an instant disruption score.</h3>
                <p>
                  The score is powered by live city permit and street closure data. Results return in under 10 seconds.
                </p>
              </Card>
            </section>
          )}
          </div>
        </Section>

        <Section
          id="pricing-section"
          eyebrow="Pricing"
          title="Choose the right plan"
          description="Start free. Upgrade when you need more lookups, team access, or API integration."
          className="pricing-section"
        >
          <div className="pricing-grid pricing-grid--four">
            <Card className="detail-card pricing-card">
              <p className="supporting-kicker">Free</p>
              <h2>$0 / month</h2>
              <p className="pricing-roi">For exploring and occasional lookups</p>
              <ul className="pricing-features">
                <li>10 address lookups / month</li>
                <li>Real-time livability score</li>
                <li>Signal cards and confidence read</li>
                <li>Spatial map context</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--secondary">Get started free</button>
            </Card>
            <Card className="detail-card pricing-card pricing-card--pro">
              <p className="supporting-kicker">Pro</p>
              <h2>$49 / month</h2>
              <p className="pricing-roi">Typical agent runs 50+ lookups/month</p>
              <ul className="pricing-features">
                <li>Unlimited address lookups</li>
                <li>30-day disruption forecasts</li>
                <li>PDF and CSV report exports</li>
                <li>Permit detail drill-down</li>
                <li>Address comparison tool</li>
                <li>Alert monitoring (email)</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--primary">Start Pro trial</button>
            </Card>
            <Card className="detail-card pricing-card pricing-card--teams">
              <p className="supporting-kicker">Teams</p>
              <h2>$199 / month</h2>
              <p className="pricing-roi">For brokerages and property managers</p>
              <ul className="pricing-features">
                <li>Everything in Pro</li>
                <li>Up to 5 team seats</li>
                <li>CSV bulk import (500 addresses)</li>
                <li>REST API access</li>
                <li>Team dashboard</li>
                <li>Priority support</li>
              </ul>
              <button type="button" className="pricing-cta pricing-cta--primary">Start Teams trial</button>
            </Card>
            <Card className="detail-card pricing-card pricing-card--enterprise">
              <p className="supporting-kicker">Enterprise</p>
              <h2>From $999 / month</h2>
              <p className="pricing-roi">Custom pricing for large teams</p>
              <ul className="pricing-features">
                <li>Everything in Teams</li>
                <li>Unlimited seats</li>
                <li>Batch API (10,000+ addresses/mo)</li>
                <li>Webhook alerts</li>
                <li>SLA guarantee</li>
                <li>White-label reports</li>
                <li>Dedicated account manager</li>
              </ul>
              <a
                href="mailto:enterprise@livabilityrisks.com?subject=Enterprise%20inquiry"
                className="pricing-cta pricing-cta--enterprise"
              >
                Talk to us
              </a>
            </Card>
          </div>

          {/* Feature comparison table */}
          <div className="pricing-comparison">
            <table className="pricing-table">
              <thead>
                <tr>
                  <th>Feature</th>
                  <th>Free</th>
                  <th>Pro</th>
                  <th>Teams</th>
                  <th>Enterprise</th>
                </tr>
              </thead>
              <tbody>
                <tr><td>Lookups / month</td><td>10</td><td>Unlimited</td><td>Unlimited</td><td>Unlimited</td></tr>
                <tr><td>Bulk CSV upload</td><td>&mdash;</td><td>&mdash;</td><td>500 addresses</td><td>10,000+</td></tr>
                <tr><td>API access</td><td>&mdash;</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>Team seats</td><td>1</td><td>1</td><td>Up to 5</td><td>Unlimited</td></tr>
                <tr><td>PDF exports</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>Alert monitoring</td><td>&mdash;</td><td>Email</td><td>Email</td><td>Email + Webhook</td></tr>
                <tr><td>30-day forecasts</td><td>&mdash;</td><td>&#10003;</td><td>&#10003;</td><td>&#10003;</td></tr>
                <tr><td>SLA</td><td>&mdash;</td><td>&mdash;</td><td>&mdash;</td><td>99.9%</td></tr>
                <tr><td>Support</td><td>Community</td><td>Email</td><td>Priority</td><td>Dedicated</td></tr>
              </tbody>
            </table>
          </div>
        </Section>

        <Section
          id="examples-section"
          eyebrow="Examples"
          title="Fallback and review examples"
          description="Examples stay available for walkthroughs and fallback validation, but they stay below the primary scoring workflow."
          className="demo-section"
        >
          <div className="demo-grid demo-grid--compressed">
            <Card className="detail-card demo-card">
              <p className="supporting-kicker">Example addresses</p>
              <h2>Load a known address quickly</h2>
              <div className="example-chip-group example-chip-group--demo">
                {EXAMPLE_ADDRESSES.map((example) => (
                  <button
                    key={`demo-${example}`}
                    type="button"
                    className="example-chip"
                    onClick={() => {
                      handleSuggestionSelect(toManualSuggestion(example));
                      inputRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
                    }}
                  >
                    {example}
                  </button>
                ))}
              </div>
            </Card>

            <Card className="detail-card demo-card">
              <p className="supporting-kicker">Mode behavior</p>
              <ul className="supporting-list">
                <li>
                  <span>Live state</span>
                  <strong>Clearly labeled and presented as the default decision-ready experience.</strong>
                </li>
                <li>
                  <span>Limited data coverage</span>
                  <strong>Shown when live permit data is unavailable. Score is estimated from nearby signals.</strong>
                </li>
              </ul>
            </Card>
          </div>
        </Section>
      </Container>

      {/* ── Onboarding flow ─────────────────────────────────── */}
      {onboardingVisible && (
        <OnboardingModal
          onComplete={(exampleAddr) => {
            setOnboardingVisible(false);
            if (exampleAddr) {
              setAddress(exampleAddr);
              submitAddress(exampleAddr);
              // Show tour after results load
              setTimeout(() => setShowTour(true), 3000);
            }
          }}
        />
      )}

      {showTour && result && (
        <FeatureTour onDismiss={() => setShowTour(false)} />
      )}

      {showSaveModal && (
        <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Save report" onClick={() => { setShowSaveModal(false); setSaveReportId(null); setSaveError(null); }}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <button type="button" className="modal-close" aria-label="Close" onClick={() => { setShowSaveModal(false); setSaveReportId(null); setSaveError(null); }}>×</button>
            <p className="supporting-kicker">Save report</p>
            <h3>Create a free account to save and share this report.</h3>
            <p className="modal-copy">Your disruption brief for {result?.address} will be saved to your account and shareable via link.</p>
            <input
              type="email"
              placeholder="your@email.com"
              value={saveEmail}
              onChange={(e) => setSaveEmail(e.target.value)}
              aria-label="Email address"
            />
            <button
              type="button"
              className="modal-cta"
              disabled={!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(saveEmail)}
            >
              Create free account
            </button>
            <p className="modal-fine-print">No credit card required. Free plan includes unlimited lookups.</p>
          </div>
        </div>
      )}
    </main>
  );
}
