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
import { fetchAddressDashboard, fetchAddressSuggestions, fetchHistory, fetchScore, geocodeForMap, getExportUrl, saveReport, ApiError, AddressSuggestion, ScoreHistoryEntry, ScoreResponse, ScoreSource } from "@/lib/api";
import { headlineScore } from "@/lib/score-utils";
import { getLookupUsage, recordLookup, isDemoAddress } from "@/lib/lookup-quota";
import { OnboardingModal, FeatureTour, useOnboardingState } from "@/components/onboarding";
import type { SelectedAddress } from "@/lib/address-types";

const DEFAULT_ADDRESS = "1600 W Chicago Ave, Chicago, IL";
const POSITIONING = "Helps brokers spot disruption risk before tenant tours and lease commitments.";


type SuggestionAddressParts = {
  street: string;
  city: string;
  state: string;
  zip: string;
};

type QaCompareRow = {
  address: string;
  score: number | null;
  confidence: string | null;
  status: "ok" | "error";
  flagged: boolean;
  note: string;
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
  const [scoreHistory, setScoreHistory] = useState<ScoreHistoryEntry[]>([]);
  const [dashboardUnavailableReason, setDashboardUnavailableReason] = useState<string | null>(null);
  const [dashboardHydrationStatus, setDashboardHydrationStatus] = useState<"full" | "partial" | "unsupported" | null>(null);
  const [isFocused, setIsFocused] = useState(false);
  // Debug mode: visible only when ?debug=true is in the URL. Never shown to users.
  const [isDebugMode, setIsDebugMode] = useState(false);
  // Commute feature flag: visible only when ?features=commute is in the URL.
  const [showCommute, setShowCommute] = useState(false);
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
  const [revealPhase, setRevealPhase] = useState<0 | 1 | 2 | 3>(0);
  const [qaAddresses, setQaAddresses] = useState("");
  const [qaLoading, setQaLoading] = useState(false);
  const [qaRows, setQaRows] = useState<QaCompareRow[]>([]);
  const [showRawSignals, setShowRawSignals] = useState(false);
  const [showScoringBreakdown, setShowScoringBreakdown] = useState(false);
  useEffect(() => { setOnboardingVisible(showOnboarding); }, [showOnboarding]);
  // Mobile simplified view — reset to false on each new result so users always
  // land on the mobile summary first. Set to true when "Switch to full report" is tapped.
  const [mobileShowFull, setMobileShowFull] = useState(false);
  const searchShellRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const skipSuggestRef = useRef(false);
  const suggestRequestIdRef = useRef(0);
  const hydrationRequestIdRef = useRef(0);
  const popularSuggestionsRef = useRef<AddressSuggestion[]>([]);
  const searchStartedAtRef = useRef<number | null>(null);
  const hasSubmittedSearchRef = useRef(false);
  const dropoffTrackedRef = useRef(false);
  // Only fetch suggestions after the user has actually typed — prevents the
  // dropdown firing on mount or when an address is set programmatically.
  const hasUserTyped = useRef(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const incomingAddress = params.get("address")?.trim();
    if (!incomingAddress) return;
    setAddress(incomingAddress);
    setSelectedAddress(null);
    void submitAddress(incomingAddress);
  }, []);

  useEffect(() => {
    const reportDropoff = () => {
      if (dropoffTrackedRef.current) return;
      if (hasSubmittedSearchRef.current) return;
      if (!hasUserTyped.current) return;
      if (!address.trim()) return;
      if (result || isLoading) return;
      dropoffTrackedRef.current = true;
      track("search_dropoff_before_submit", {
        address_length: address.trim().length,
        had_suggestions: suggestions.length > 0,
      });
    };
    window.addEventListener("beforeunload", reportDropoff);
    return () => {
      reportDropoff();
      window.removeEventListener("beforeunload", reportDropoff);
    };
  }, [address, isLoading, result, suggestions.length]);

  useEffect(() => {
    fetchAddressSuggestions("", { popular: true, limit: 5 })
      .then((results) => { popularSuggestionsRef.current = results; })
      .catch(() => { popularSuggestionsRef.current = []; });
  }, []);

  const workspaceMode = isLoading || result !== null;
  const isDevEnv = process.env.NODE_ENV !== "production";
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
    const evidenceLabel: Record<string, string> = {
      strong: "Strong", moderate: "Moderate",
      contextual_only: "Limited", insufficient: "Insufficient",
    };
    const timeStr = scoredAt
      ? new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" }).format(scoredAt)
      : null;
    return [
      { label: "Evidence strength", value: evidenceLabel[result.evidence_quality ?? ""] ?? "Unknown" },
      { label: "Active signals", value: String(result.strong_signal_count ?? 0) },
      { label: "Confidence", value: result.confidence, isConfidence: true },
      ...(timeStr ? [{ label: "Scored at", value: timeStr }] : []),
    ];
  }, [result, scoredAt]);
  const quickExplanation = useMemo(() => {
    if (!result) return "";
    const score = headlineScore(result);
    const band = score <= 30 ? "low" : score <= 60 ? "moderate" : "high";
    const firstRisk = result.top_risks?.[0];
    const firstDetail = result.top_risk_details?.[0];
    const timing = (() => {
      const fmtDate = (iso: string | null | undefined) => {
        if (!iso) return null;
        const date = new Date(iso);
        if (Number.isNaN(date.getTime())) return null;
        return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
      };
      const start = fmtDate(firstDetail?.start_date);
      const end = fmtDate(firstDetail?.end_date);
      if (start && end) return `${start} to ${end}`;
      if (start) return `starting ${start}`;
      if (end) return `through ${end}`;
      return "in the current reporting window";
    })();
    const distance = typeof firstDetail?.distance_m === "number" && Number.isFinite(firstDetail.distance_m)
      ? `${Math.round(firstDetail.distance_m).toLocaleString()} meters`
      : "the immediate area";
    const higherThanPct = Math.max(5, Math.min(95, Math.round(score)));
    const rangeClause = score > 40 ? "above typical range" : score < 20 ? "below typical range" : "within typical range";

    const sentenceOne = `This address has ${band} near-term disruption risk with a score of ${score}/100, higher than ${higherThanPct}% of nearby areas and ${rangeClause}.`;
    const sentenceTwo = firstRisk
      ? `Primary pressure comes from ${firstRisk} ${distance} away, active ${timing}.`
      : "No material active signals were detected in the current reporting window.";
    return `${sentenceOne} ${sentenceTwo}`;
  }, [result]);
  const topThreeRisks = useMemo(
    () => (result?.top_risks ?? []).slice(0, 3),
    [result],
  );
  const topRiskSummaries = useMemo(() => {
    if (!result) return [];
    const details = result.top_risk_details ?? [];
    const fmtDate = (iso: string | null | undefined) => {
      if (!iso) return null;
      const date = new Date(iso);
      if (Number.isNaN(date.getTime())) return null;
      return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" }).format(date);
    };
    const timingText = (start: string | null | undefined, end: string | null | undefined) => {
      const startLabel = fmtDate(start);
      const endLabel = fmtDate(end);
      if (startLabel && endLabel) return `${startLabel} → ${endLabel}`;
      if (startLabel) return `Starts ${startLabel}`;
      if (endLabel) return `Through ${endLabel}`;
      return "Timing not provided";
    };
    return (result.top_risks ?? []).slice(0, 3).map((risk, idx) => {
      const detail = details[idx];
      const meters = detail?.distance_m;
      const distanceLabel = typeof meters === "number" && Number.isFinite(meters)
        ? `${Math.round(meters).toLocaleString()} m`
        : "Distance not provided";
      const severityLabel = detail
        ? (detail.weighted_score >= 15
          ? "high severity"
          : detail.weighted_score >= 7
            ? "moderate severity"
            : "low severity")
        : "severity not provided";
      return {
        risk,
        distanceLabel,
        timingLabel: timingText(detail?.start_date, detail?.end_date),
        severityLabel,
      };
    });
  }, [result]);
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
    const params = new URLSearchParams(window.location.search);
    setIsDebugMode(params.get("debug") === "true");
    setShowCommute(params.get("features")?.includes("commute") ?? false);
    // Load lookup usage from localStorage
    setLookupUsage(getLookupUsage(!!isSignedIn, isPro));
  }, [isSignedIn, isPro]);

  // Global keyboard shortcuts: Escape closes modal/history, "/" focuses input
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setShowSaveModal(false);
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
      if (popularSuggestionsRef.current.length > 0) {
        if (isFocused) {
          setSuggestions(popularSuggestionsRef.current);
          setShowSuggestions(true);
          setActiveSuggestionIndex(-1);
        }
        setSuggestionsLoading(false);
        return;
      }
      const requestId = ++suggestRequestIdRef.current;
      setSuggestionsLoading(true);
      fetchAddressSuggestions("", { popular: true, limit: 5 }).then((results) => {
        if (requestId !== suggestRequestIdRef.current) return;
        popularSuggestionsRef.current = results;
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
    }, 80);
    return () => clearTimeout(timer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [address]);

  useEffect(() => {
    document.title = result
      ? `${result.address} — Livability Risk Engine`
      : "Livability Risk Engine";
  }, [result]);

  useEffect(() => {
    document.body.dataset.resultsVisible = result ? "1" : "0";
    return () => {
      delete document.body.dataset.resultsVisible;
    };
  }, [result]);

  useEffect(() => {
    if (!result) {
      setRevealPhase(0);
      return;
    }
    setRevealPhase(1); // 1) score
    const explanationTimer = setTimeout(() => setRevealPhase(2), 120); // 2) explanation
    const detailsTimer = setTimeout(() => setRevealPhase(3), 280); // 3) details
    return () => {
      clearTimeout(explanationTimer);
      clearTimeout(detailsTimer);
    };
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
    hasSubmittedSearchRef.current = true;
    searchStartedAtRef.current = typeof performance !== "undefined" ? performance.now() : Date.now();
    track("search_started", {
      address_length: addr.length,
      used_selected_address: Boolean(selectedAddress?.id),
      from_query_handoff: typeof window !== "undefined" ? new URLSearchParams(window.location.search).has("address") : false,
    });
    track("address_analyzed", { address: addr });
    setIsLoading(true);
    setRevealPhase(0);
    setError(null);
    setDashboardUnavailableReason(null);
    setDashboardHydrationStatus(null);
    setMobileShowFull(false);
    try {
      const scoreResult = await fetchScore(addr, {
        canonicalId: selectedAddress?.id ?? null,
        lat: typeof selectedAddress?.lat === "number" ? selectedAddress.lat : undefined,
        lon: typeof selectedAddress?.lon === "number" ? selectedAddress.lon : undefined,
      });
      setResult(scoreResult.score);
      const finishedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
      const durationMs = searchStartedAtRef.current ? Math.round(finishedAt - searchStartedAtRef.current) : null;
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
      track("search_result_loaded", {
        duration_ms: durationMs,
        confidence: scoreResult.score.confidence,
        score: headlineScore(scoreResult.score),
      });
    } catch (submissionError) {
      const finishedAt = typeof performance !== "undefined" ? performance.now() : Date.now();
      const durationMs = searchStartedAtRef.current ? Math.round(finishedAt - searchStartedAtRef.current) : null;
      setError(
        submissionError instanceof Error
          ? submissionError.message
          : "Live data temporarily unavailable. Try again in a moment.",
      );
      setResult(null);
      setStatusNote(null);
      track("search_result_failed", {
        duration_ms: durationMs,
        message:
          submissionError instanceof Error
            ? submissionError.message
            : "unknown_error",
      });
    } finally {
      searchStartedAtRef.current = null;
      setIsLoading(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitAddress(address);
  }

  async function runQaCompare() {
    const addresses = qaAddresses
      .split(/\n|;/g)
      .map((item) => item.trim())
      .filter(Boolean)
      .slice(0, 10);
    if (addresses.length === 0) return;
    setQaLoading(true);
    try {
      const rows = await Promise.all(
        addresses.map(async (addr): Promise<QaCompareRow> => {
          try {
            const res = await fetchScore(addr);
            return {
              address: addr,
              score: headlineScore(res.score),
              confidence: res.score.confidence,
              status: "ok",
              flagged: false,
              note: "",
            };
          } catch {
            return {
              address: addr,
              score: null,
              confidence: null,
              status: "error",
              flagged: false,
              note: "",
            };
          }
        }),
      );
      setQaRows(rows);
    } finally {
      setQaLoading(false);
    }
  }

  function updateQaRow(index: number, patch: Partial<QaCompareRow>) {
    setQaRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
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
              <p className="brand-title">Livability Risk Engine</p>
              <p className="brand-subtitle">{POSITIONING}</p>
            </div>
          </div>

          <nav className={`topnav${workspaceMode ? " topnav--workspace" : ""}`} aria-label="Primary">
            <a href="/methodology" className="topnav-aux-link">Docs</a>
            <a href="/api-access" className="topnav-aux-link">API</a>
            <SignedOut>
              <SignInButton mode="modal">
                <button type="button" className="topnav-sign-in">Sign In</button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </nav>
        </Header>

        <Section className={`hero-section ${workspaceMode ? "hero-section--workspace" : ""}`}>
          <Card tone="highlighted" className="hero-card">
            <div className={`hero-copy ${workspaceMode ? "hero-copy--workspace" : ""}`}>
              <p className="eyebrow">Address disruption brief</p>
              <h1>
                {workspaceMode
                  ? "Spot disruption risk before tours and lease commitments."
                  : "Spot disruption risk before tours and lease commitments."}
              </h1>
              <p className="lede">
                {workspaceMode
                  ? "Use this brief to guide tour routing, timing conversations, and next-step recommendations."
                  : "Start with score + top drivers, then open secondary modules only when deeper diligence is needed."}
              </p>
              {!workspaceMode && (
                <a href="mailto:enterprise@livabilityrisks.com" className="enterprise-cta">
                  Request enterprise demo →
                </a>
              )}
            </div>

            <form className={`lookup-form ${workspaceMode ? "lookup-form--workspace" : ""}`} onSubmit={handleSubmit}>
              <label htmlFor="address" className="input-label">
                {workspaceMode ? "Search another property address" : "Enter a Chicago property address"}
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
                        if (popularSuggestionsRef.current.length > 0) {
                          setSuggestions(popularSuggestionsRef.current);
                          setShowSuggestions(true);
                          setActiveSuggestionIndex(-1);
                        } else {
                          setSuggestionsLoading(true);
                          setSuggestionsError(null);
                          fetchAddressSuggestions("", { popular: true, limit: 5 })
                            .then((results) => {
                              popularSuggestionsRef.current = results;
                              setSuggestions(results);
                              setShowSuggestions(true);
                              setActiveSuggestionIndex(-1);
                            })
                            .catch(() => {
                              setSuggestionsError("Could not load suggestions.");
                            })
                            .finally(() => setSuggestionsLoading(false));
                        }
                      }
                    }}
                    onBlur={() => {
                      setIsFocused(false);
                      setTimeout(() => setShowSuggestions(false), 150);
                    }}
                    onKeyDown={handleInputKeyDown}
                    placeholder="Search a Chicago address"
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
                          <span className="suggestion-item-label">Finding closest matches…</span>
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
                  Uses Chicago permit and planned street-closure records from city sources.
                </p>

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
                      <a href="/pricing" className="gate-btn gate-btn--primary" onClick={() => setShowGate(false)}>
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

            {isDevEnv && result && (
              <details style={{ marginTop: "0.75rem", fontSize: "0.8rem", opacity: 0.9 }}>
                <summary style={{ cursor: "pointer", userSelect: "none" }}>
                  Dev tools: raw signals + scoring breakdown
                </summary>
                <div style={{ marginTop: "8px", display: "grid", gap: "8px" }}>
                  <label>
                    <input
                      type="checkbox"
                      checked={showRawSignals}
                      onChange={(e) => setShowRawSignals(e.target.checked)}
                    />{" "}
                    Show raw signals
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={showScoringBreakdown}
                      onChange={(e) => setShowScoringBreakdown(e.target.checked)}
                    />{" "}
                    Show scoring breakdown
                  </label>
                  {showRawSignals && (
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {JSON.stringify(result.nearby_signals ?? [], null, 2)}
                    </pre>
                  )}
                  {showScoringBreakdown && (
                    <pre style={{ margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {JSON.stringify({
                        disruption_score: result.disruption_score,
                        livability_score: result.livability_score,
                        confidence: result.confidence,
                        severity: result.severity,
                        top_risk_details: result.top_risk_details ?? [],
                        livability_breakdown: result.livability_breakdown ?? null,
                      }, null, 2)}
                    </pre>
                  )}
                </div>
              </details>
            )}
          </Card>
        </Section>

        {!workspaceMode && (
          <Section
            eyebrow="Broker workflow"
            title="Use this before tours, proposals, and LOIs"
            description="Prioritize near-term deal friction first, then pull supporting detail when needed."
            className="how-it-works-section"
          >
            <div className="how-it-works-grid">
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">01</div>
                <h3 className="hiw-step-title">Search the listing address</h3>
                <p className="hiw-step-body">
                  Start with the exact property address you are marketing or underwriting.
                </p>
              </div>
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">02</div>
                <h3 className="hiw-step-title">Read score + top drivers first</h3>
                <p className="hiw-step-body">
                  The workspace foregrounds access, closure, and construction signals that can impact tour quality and leasing velocity.
                </p>
              </div>
              <div className="hiw-step">
                <div className="hiw-step-number" aria-hidden="true">03</div>
                <h3 className="hiw-step-title">Open secondary detail on demand</h3>
                <p className="hiw-step-body">
                  Neighborhood, commute, and timeline modules remain available below the core brief when deeper diligence is required.
                </p>
              </div>
            </div>
          </Section>
        )}

        <Section
          className={workspaceMode ? "workspace-section workspace-section--score" : undefined}
          eyebrow="Broker brief"
          title={workspaceMode ? "Leasing impact snapshot" : "What this broker brief returns"}
          description={
            workspaceMode
              ? "Read the score and top drivers first. Expand full diligence modules only when you need deeper context."
              : "Each lookup returns a broker-facing score brief, prioritized risk drivers, and expandable supporting modules."
          }
          headerAction={workspaceMode && result ? (
            <a
              href="/pricing"
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

              <Card className="detail-card skeleton-card">
                <div className="skeleton skeleton-title" />
                <div className="skeleton skeleton-line" />
                <div className="skeleton skeleton-line short" />
              </Card>
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
              {revealPhase < 3 && (
                <div className="supporting-kicker" style={{ marginBottom: "4px" }}>
                  Building brief…
                </div>
              )}
              {headlineScore(result) >= 61 && (
                <div className="pro-badge-bar">
                  <span className="pro-badge-icon">⚠</span>
                  <span>
                    <strong>High-risk address detected.</strong> Pro users get 30-day forecasts and permit detail exports.{" "}
                    <a href="/pricing" className="pro-badge-link">See Pro plan →</a>
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
                {revealPhase >= 2 ? (
                  <Card className="detail-card detail-card--summary">
                    <h2>Quick explanation</h2>
                    <p className="score-hero-summary">
                      {quickExplanation || "Nearby disruption signals drive this score for the selected address."}
                    </p>
                    {topThreeRisks.length > 0 ? (
                      <>
                        <p className="supporting-kicker" style={{ marginTop: "10px" }}>Top 3 risks</p>
                        <ul className="supporting-list supporting-list--compact">
                          {topRiskSummaries.map((risk, idx) => (
                            <li key={`${risk.risk}-${idx}`}>
                              <span>Rank {idx + 1} • {risk.severityLabel}</span>
                              <strong>{risk.risk}</strong>
                              <small style={{ display: "block", opacity: 0.85 }}>
                                {risk.distanceLabel} • {risk.timingLabel}
                              </small>
                            </li>
                          ))}
                        </ul>
                      </>
                    ) : null}
                  </Card>
                ) : (
                  <Card className="detail-card skeleton-card">
                    <div className="skeleton skeleton-title" />
                    <div className="skeleton skeleton-line" />
                    <div className="skeleton skeleton-line short" />
                  </Card>
                )}
              </div>

              {revealPhase >= 3 && (
                <details id="secondary-details" className="secondary-details">
                  <summary>Open full analysis</summary>
                  <div className="secondary-details-body">
                  <div id="signals-section" className="anchor-target" />
                  <Section
                    eyebrow="Signal analysis"
                    title="Primary deal-impact signals"
                    description="Top cards and timeline are grouped together so you can read what matters first."
                    className="workspace-subsection"
                  >
                    {result.signal_summary && (
                      <p style={{ fontSize: "0.82rem", color: "var(--color-text-secondary, #94a3b8)", margin: "0 0 0.75rem" }}>
                        {result.signal_summary}
                      </p>
                    )}
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
                      <details>
                        <summary style={{ cursor: "pointer", fontSize: "0.82rem", fontWeight: 600, color: "var(--color-text-secondary, #94a3b8)" }}>
                          Severity breakdown
                        </summary>
                        <div style={{ marginTop: "0.5rem" }}>
                          <SeverityMeters severity={result.severity} confidence={result.confidence} confidenceReasons={confidenceReasons} />
                          <ImpactWindow result={result} />
                        </div>
                      </details>
                    </Card>
                    <Card className="detail-card supporting-card">
                      <p className="supporting-kicker">Quick facts</p>
                      <ul className="supporting-list supporting-list--compact">
                        {supportingDetails.map((item) => (
                          <li key={item.label}>
                            <span>{item.label}</span>
                            {"isConfidence" in item && item.isConfidence ? (
                              <>
                                <strong className="confidence-value">
                                  <span className={`confidence-dot confidence-dot--${item.value.toLowerCase()}`} aria-hidden="true" />
                                  {item.value}
                                </strong>
                                {result?.confidence_reason && (
                                  <span style={{ display: "block", fontSize: "0.72rem", color: "var(--color-text-secondary, #94a3b8)", marginTop: "2px", lineHeight: 1.4 }}>
                                    {result.confidence_reason}
                                  </span>
                                )}
                              </>
                            ) : (
                              <strong>{item.value}</strong>
                            )}
                          </li>
                        ))}
                      </ul>
                    </Card>
                  </div>

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

                  <Card className="detail-card">
                    <NeighborhoodContextCard
                      result={result}
                      scoreHistory={scoreHistory}
                      lat={mapCoords?.lat ?? result.latitude}
                      lon={mapCoords?.lon ?? result.longitude}
                      hideEstimates={!isDebugMode}
                    />
                  </Card>

                  {/* ── Monitor this address — moved below map & signals ─────── */}
                  {headlineScore(result) >= 50 && (
                    <WatchlistForm address={result.address} score={headlineScore(result)} />
                  )}

                  {/* ── Commute checker — hidden unless ?features=commute ────── */}
                  {showCommute && (
                    <CommuteChecker homeAddress={result.address} />
                  )}

                  {/* ── Internal QA panel — hidden unless ?debug=true ────────── */}
                  {isDebugMode && (
                  <Card className="detail-card">
                    <p className="supporting-kicker">Internal QA panel</p>
                    <h2>Compare addresses + flag incorrect scores</h2>
                    <p className="modal-copy">Enter one address per line (up to 10), run compare, then flag rows that look incorrect.</p>
                    <textarea
                      className="search-input"
                      style={{ minHeight: "110px", marginTop: "8px" }}
                      value={qaAddresses}
                      onChange={(e) => setQaAddresses(e.target.value)}
                      placeholder={"1600 W Chicago Ave, Chicago, IL\n3150 N Southport Ave, Chicago, IL"}
                    />
                    <div className="score-actions" style={{ marginTop: "10px" }}>
                      <button type="button" className="action-btn" onClick={runQaCompare} disabled={qaLoading}>
                        {qaLoading ? "Running compare…" : "Compare results"}
                      </button>
                    </div>
                    {qaRows.length > 0 && (
                      <div style={{ marginTop: "12px", display: "grid", gap: "8px" }}>
                        {qaRows.map((row, idx) => (
                          <div key={`${row.address}-${idx}`} className="detail-card" style={{ padding: "10px" }}>
                            <strong>{row.address}</strong>
                            <p className="modal-copy" style={{ marginTop: "4px" }}>
                              {row.status === "ok"
                                ? `Score ${row.score} • Confidence ${row.confidence}`
                                : "Score fetch failed"}
                            </p>
                            <label style={{ display: "block", marginTop: "6px" }}>
                              <input
                                type="checkbox"
                                checked={row.flagged}
                                onChange={(e) => updateQaRow(idx, { flagged: e.target.checked })}
                              />{" "}
                              Flag incorrect score
                            </label>
                            {row.flagged && (
                              <input
                                className="search-input"
                                style={{ marginTop: "6px" }}
                                placeholder="Why is this score incorrect?"
                                value={row.note}
                                onChange={(e) => updateQaRow(idx, { note: e.target.value })}
                              />
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </Card>
                  )}
                  </div>
                </details>
              )}
              </div>{/* end desktop-view */}
            </section>
          ) : (
            <section className="results">
              <Card className="empty-state">
                <p className="empty-kicker">Ready for analysis</p>
                <h3>Enter an Illinois address above to get an address-level disruption score.</h3>
                <p>
                  The score uses city permit and planned street-closure records, with severity, top drivers, and map context in one response.
                </p>
              </Card>
            </section>
          )}
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
