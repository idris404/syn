"use client";

import { Input } from "@/components/ui/input";

interface Props {
  query: string;
  onChange: (value: string) => void;
}

export function TrialSearchBar({ query, onChange }: Props) {
  return (
    <Input
      value={query}
      onChange={(e) => onChange(e.target.value)}
      placeholder="Rechercher un essai (ex: pembrolizumab, EGFR, melanoma...)"
    />
  );
}
