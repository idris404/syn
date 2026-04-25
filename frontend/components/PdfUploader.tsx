"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api";

export function PdfUploader() {
  const [file, setFile] = useState<File | null>(null);
  const [vision, setVision] = useState(false);
  const [progress, setProgress] = useState(0);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const modeLabel = useMemo(() => (vision ? "Vision AI" : "Extraction texte"), [vision]);

  async function onUpload() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setProgress(5);

    const timer = setInterval(() => {
      setProgress((prev) => (prev < 90 ? prev + 8 : prev));
    }, 500);

    try {
      const data = await api.uploadPdf(file, vision);
      setResult(data);
      setProgress(100);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur upload");
      setProgress(0);
    } finally {
      clearInterval(timer);
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload PDF</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-dashed border-[var(--syn-border)] p-5">
          <input
            type="file"
            accept="application/pdf"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
            className="block w-full text-sm text-[var(--syn-muted)]"
          />
          <p className="mt-2 text-xs text-[var(--syn-muted)]">
            Mode actuel: {modeLabel}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button variant={vision ? "secondary" : "default"} onClick={() => setVision(false)}>
            Extraction texte
          </Button>
          <Button variant={vision ? "default" : "secondary"} onClick={() => setVision(true)}>
            Vision AI (figures)
          </Button>
        </div>

        {loading ? (
          <div>
            <div className="h-2 w-full overflow-hidden rounded bg-[#1a1d2a]">
              <div className="h-full bg-[var(--syn-accent)] transition-all" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-xs text-[var(--syn-muted)]">Upload en cours... {progress}%</p>
          </div>
        ) : null}

        <Button disabled={!file || loading} onClick={onUpload}>
          Démarrer l&apos;upload
        </Button>

        {error ? <p className="text-sm text-red-400">{error}</p> : null}

        {result ? (
          <>
            <Separator />
            <pre className="overflow-x-auto rounded-md bg-[#0d0f16] p-3 text-xs text-[var(--syn-muted)]">
              {JSON.stringify(result, null, 2)}
            </pre>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
