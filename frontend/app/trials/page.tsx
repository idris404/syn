"use client";

import { useEffect, useMemo, useState } from "react";

import { TrialCard } from "@/components/TrialCard";
import { TrialSearchBar } from "@/components/TrialSearchBar";
import { Card, CardContent } from "@/components/ui/card";
import { api } from "@/lib/api";
import { TrialSearchResult } from "@/lib/types";

function useDebounce<T>(value: T, delay = 400) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function TrialsPage() {
  const [query, setQuery] = useState("");
  const [phase, setPhase] = useState("");
  const [status, setStatus] = useState("");
  const [results, setResults] = useState<TrialSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const debouncedQuery = useDebounce(query, 400);

  useEffect(() => {
    if (!debouncedQuery) {
      setResults([]);
      return;
    }
    setLoading(true);
    api.searchTrials(debouncedQuery, phase || undefined, status || undefined)
      .then((res) => setResults(res.results || []))
      .finally(() => setLoading(false));
  }, [debouncedQuery, phase, status]);

  const phases = useMemo(() => ["", "PHASE1", "PHASE2", "PHASE3", "PHASE4"], []);
  const statuses = useMemo(
    () => ["", "RECRUITING", "COMPLETED", "ACTIVE_NOT_RECRUITING", "NOT_YET_RECRUITING"],
    []
  );

  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Recherche d&apos;essais</h1>
      <Card>
        <CardContent className="space-y-3 pt-5">
          <TrialSearchBar query={query} onChange={setQuery} />
          <div className="grid gap-3 sm:grid-cols-2">
            <select
              value={phase}
              onChange={(e) => setPhase(e.target.value)}
              className="h-10 rounded-md border border-[var(--syn-border)] bg-[#0f1018] px-3 text-sm"
            >
              {phases.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "Toutes les phases"}
                </option>
              ))}
            </select>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="h-10 rounded-md border border-[var(--syn-border)] bg-[#0f1018] px-3 text-sm"
            >
              {statuses.map((value) => (
                <option key={value || "all"} value={value}>
                  {value || "Tous les statuts"}
                </option>
              ))}
            </select>
          </div>
        </CardContent>
      </Card>

      {loading ? <p className="text-sm text-[var(--syn-muted)]">Recherche en cours...</p> : null}
      {!loading && debouncedQuery && !results.length ? (
        <p className="text-sm text-[var(--syn-muted)]">Aucun résultat.</p>
      ) : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {results.map((trial) => (
          <TrialCard key={trial.nct_id} trial={trial} />
        ))}
      </section>
    </main>
  );
}
