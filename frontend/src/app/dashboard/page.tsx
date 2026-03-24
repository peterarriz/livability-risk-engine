"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSession } from "next-auth/react";

import { Card, Section } from "@/components/shell";
import { fetchDashboard, type DashboardResponse } from "@/lib/api";

type LocalSavedReport = {
  report_id: string;
  address: string;
  saved_livability_score: number | null;
  saved_disruption_score: number | null;
  created_at: string;
};

export default function DashboardPage() {
  const { data: session, status } = useSession();
  const [data, setData] = useState<DashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (status === "loading") return;
      if (session?.user?.backend_token) {
        const live = await fetchDashboard(session.user.backend_token);
        if (!cancelled) setData(live);
      } else {
        // Anonymous fallback: localStorage-only list of saved report IDs.
        const raw = window.localStorage.getItem("lre_saved_reports");
        const localReports: LocalSavedReport[] = raw ? JSON.parse(raw) : [];
        if (!cancelled) {
          setData({
            saved_reports: localReports.slice(0, 10),
            watchlist: [],
          });
        }
      }
      if (!cancelled) setLoading(false);
    }
    load();
    return () => { cancelled = true; };
  }, [session?.user?.backend_token, status]);

  const watchChanged = useMemo(
    () => (data?.watchlist ?? []).filter((w) => w.score_changed),
    [data?.watchlist],
  );

  if (loading) {
    return (
      <main className="page">
        <div className="shell-container">
          <Section eyebrow="Dashboard" title="Loading your livability dashboard…">
            <Card className="detail-card">
              <p>Loading…</p>
            </Card>
          </Section>
        </div>
      </main>
    );
  }

  return (
    <main className="page">
      <div className="shell-container">
        <Section
          eyebrow="Dashboard"
          title="Saved reports and watchlist"
          description="Track saved Livability Scores, active watchlist addresses, and score changes since save."
        >
          <div className="workspace-top-grid">
            <Card className="detail-card">
              <h2>Saved reports (last 10)</h2>
              {(data?.saved_reports ?? []).length === 0 ? (
                <p>No saved reports yet.</p>
              ) : (
                <ul className="supporting-list supporting-list--compact">
                  {(data?.saved_reports ?? []).map((r) => (
                    <li key={r.report_id}>
                      <span>{r.address}</span>
                      <strong>
                        {r.saved_livability_score ?? "—"}{" "}
                        <Link href={`/report/${r.report_id}`}>Open</Link>
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
            </Card>

            <Card className="detail-card">
              <h2>Watchlist (active)</h2>
              {(data?.watchlist ?? []).length === 0 ? (
                <p>No active watchlist entries.</p>
              ) : (
                <ul className="supporting-list supporting-list--compact">
                  {(data?.watchlist ?? []).map((w) => (
                    <li key={w.id}>
                      <span>{w.address}</span>
                      <strong>
                        {w.current_livability_score ?? "—"}
                        {w.score_changed && (
                          <span style={{ marginLeft: 8, color: "#f59e0b" }}>
                            Δ {w.score_diff_since_saved! > 0 ? "+" : ""}
                            {w.score_diff_since_saved}
                          </span>
                        )}
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div style={{ marginTop: "1rem" }}>
            <Card className="detail-card">
              <h2>Score changed since you saved it</h2>
              {watchChanged.length === 0 ? (
                <p>No watchlist addresses have changed since your saved baseline.</p>
              ) : (
                <ul className="supporting-list supporting-list--compact">
                  {watchChanged.map((w) => (
                    <li key={`changed-${w.id}`}>
                      <span>{w.address}</span>
                      <strong>
                        {w.score_diff_since_saved! > 0 ? "+" : ""}
                        {w.score_diff_since_saved} points
                      </strong>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </Section>
      </div>
    </main>
  );
}
