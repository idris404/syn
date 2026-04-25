"use client";

import { X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { WsMessage } from "@/lib/types";

interface Props {
  message: WsMessage | null;
  onClose: () => void;
}

export function AlertBanner({ message, onClose }: Props) {
  if (!message || message.type !== "run_complete") return null;

  return (
    <Card className="mb-6 border-[var(--syn-accent)]/50 bg-[rgb(0_180_216_/_0.08)]">
      <CardContent className="flex items-start justify-between gap-4 pt-5">
        <div>
          <p className="text-sm font-semibold text-[var(--syn-accent)]">Run terminé</p>
          <p className="mt-1 text-lg font-medium">{message.title || "Nouveau rapport généré"}</p>
          <p className="mt-1 text-sm text-[var(--syn-muted)]">{message.summary || "Le rapport est prêt."}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={onClose} aria-label="Fermer l'alerte">
          <X size={14} />
        </Button>
      </CardContent>
    </Card>
  );
}
