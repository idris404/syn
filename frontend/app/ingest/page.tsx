import { PdfUploader } from "@/components/PdfUploader";

export default function IngestPage() {
  return (
    <main className="space-y-4">
      <h1 className="text-2xl font-semibold">Ingestion PDF</h1>
      <p className="text-sm text-[var(--syn-muted)]">
        Chargez un document et choisissez entre extraction texte classique ou analyse Vision AI.
      </p>
      <PdfUploader />
    </main>
  );
}
