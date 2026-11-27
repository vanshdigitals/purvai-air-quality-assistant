import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  HOUSEHOLD_STORAGE_KEY,
  type ImportDryRunResponse,
  createBackup,
  deleteAllData,
  downloadReport,
  exportData,
  fetchBackups,
  fetchHealth,
  importData,
  restoreBackup,
} from "../../lib/api";

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pendingImport, setPendingImport] = useState<unknown | null>(null);
  const [dryRunPreview, setDryRunPreview] = useState<ImportDryRunResponse | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearConfirmText, setClearConfirmText] = useState("");

  const healthQuery = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
  });

  const isDemo = healthQuery.data?.mode === "demo";

  const backupsQuery = useQuery({
    queryKey: ["db-backups"],
    queryFn: fetchBackups,
    enabled: !isDemo,
  });

  const backupMutation = useMutation({
    mutationFn: createBackup,
    onSuccess: (res) => {
      setErrorMsg(null);
      setStatusMsg(`Backup created: ${res.filename}`);
      void queryClient.invalidateQueries({ queryKey: ["db-backups"] });
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const restoreMutation = useMutation({
    mutationFn: (filename: string) => restoreBackup(filename),
    onSuccess: (res) => {
      setErrorMsg(null);
      setStatusMsg(`Restored database from ${res.restored}`);
      void queryClient.invalidateQueries();
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  const clearMutation = useMutation({
    mutationFn: deleteAllData,
    onSuccess: () => {
      setConfirmClear(false);
      setClearConfirmText("");
      localStorage.removeItem(HOUSEHOLD_STORAGE_KEY);
      setStatusMsg("All household data deleted.");
      void queryClient.invalidateQueries();
    },
    onError: (err: Error) => setErrorMsg(err.message),
  });

  async function handleReportDownload(format: "pdf" | "csv") {
    try {
      setErrorMsg(null);
      const blob = await downloadReport(format, 7);
      triggerBlobDownload(blob, `purvai-report-7d.${format}`);
      setStatusMsg(`${format.toUpperCase()} report downloaded.`);
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Download failed.");
    }
  }

  async function handleJsonExport() {
    try {
      setErrorMsg(null);
      const data = await exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      triggerBlobDownload(blob, "purvai-export.json");
      setStatusMsg("JSON export downloaded.");
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Export failed.");
    }
  }

  async function handleFileSelected(file: File | undefined) {
    if (!file) return;
    try {
      setErrorMsg(null);
      const text = await file.text();
      const parsed: unknown = JSON.parse(text);
      const preview = await importData(parsed, true);
      setPendingImport(parsed);
      setDryRunPreview(preview);
      setStatusMsg("Dry-run check passed. Review counts below to apply.");
    } catch (err) {
      setPendingImport(null);
      setDryRunPreview(null);
      setErrorMsg(err instanceof Error ? err.message : "Invalid import file.");
    }
  }

  async function handleConfirmImport() {
    if (!pendingImport) return;
    try {
      setErrorMsg(null);
      const applied = await importData(pendingImport, false);
      setPendingImport(null);
      setDryRunPreview(null);
      setStatusMsg(
        `Imported ${applied.imported.members} members, ${applied.imported.locations} locations, ${applied.imported.activities} activities.`
      );
      void queryClient.invalidateQueries();
    } catch (err) {
      setErrorMsg(err instanceof Error ? err.message : "Import failed.");
    }
  }

  return (
    <section className="max-w-[780px] space-y-6">
      <header className="space-y-1">
        <h1>Reports &amp; Data</h1>
        <p className="text-text-2">
          Export PDF/CSV reports, back up or restore your local SQLite database, or clear data.
        </p>
      </header>

      {isDemo ? (
        <div
          role="status"
          className="rounded-lg border border-amber-400 bg-amber-50 p-4 text-sm text-amber-900"
        >
          Demo mode uses temporary storage. Local SQLite backups and restores are disabled.
        </div>
      ) : null}

      {statusMsg ? (
        <p role="status" className="rounded border border-border bg-surface p-3 text-sm">
          {statusMsg}
        </p>
      ) : null}

      {errorMsg ? (
        <p
          role="alert"
          className="rounded border border-red-400 bg-red-50 p-3 text-sm text-red-700"
        >
          {errorMsg}
        </p>
      ) : null}

      <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
        <h2 className="text-base font-semibold">Export reports (7 days)</h2>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleReportDownload("pdf")}
            className="rounded bg-accent px-4 py-2 text-sm font-medium text-white"
          >
            Download PDF
          </button>
          <button
            type="button"
            onClick={() => void handleReportDownload("csv")}
            className="rounded border border-border px-4 py-2 text-sm font-medium"
          >
            Download CSV
          </button>
          <button
            type="button"
            onClick={() => void handleJsonExport()}
            className="rounded border border-border px-4 py-2 text-sm font-medium"
          >
            Export JSON
          </button>
        </div>
      </div>

      <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
        <h2 className="text-base font-semibold">Import JSON bundle</h2>
        <label className="block text-sm">
          <span className="sr-only">Choose JSON export file</span>
          <input
            aria-label="Choose JSON export file"
            type="file"
            accept="application/json,.json"
            onChange={(e) => void handleFileSelected(e.target.files?.[0])}
          />
        </label>

        {dryRunPreview ? (
          <div className="rounded border border-border bg-bg p-3 text-sm space-y-2">
            <div>
              Dry-run preview: {dryRunPreview.counts.members} member groups,{" "}
              {dryRunPreview.counts.locations} locations, {dryRunPreview.counts.activities}{" "}
              activities.
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => void handleConfirmImport()}
                className="rounded bg-accent px-3 py-1.5 text-sm font-medium text-white"
              >
                Confirm replace import
              </button>
              <button
                type="button"
                onClick={() => {
                  setPendingImport(null);
                  setDryRunPreview(null);
                }}
                className="rounded border border-border px-3 py-1.5 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}
      </div>

      {!isDemo ? (
        <div className="rounded-lg border border-border bg-surface p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">Local SQLite backups</h2>
            <button
              type="button"
              onClick={() => backupMutation.mutate()}
              disabled={backupMutation.isPending}
              className="rounded border border-border px-3 py-1.5 text-sm font-medium"
            >
              {backupMutation.isPending ? "Creating..." : "Create backup"}
            </button>
          </div>
          {(backupsQuery.data ?? []).length === 0 ? (
            <p className="text-sm text-text-2">No local backups yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {(backupsQuery.data ?? []).map((b) => (
                <li
                  key={b.filename}
                  className="flex items-center justify-between rounded border border-border px-3 py-2"
                >
                  <span>{b.filename}</span>
                  <button
                    type="button"
                    onClick={() => restoreMutation.mutate(b.filename)}
                    className="underline"
                  >
                    Restore
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      <div className="rounded-lg border border-red-300 bg-surface p-4 space-y-3">
        <h2 className="text-base font-semibold text-red-700">Clear all data</h2>
        {confirmClear ? (
          <div className="space-y-3">
            <label className="block text-sm">
              <span>Type DELETE to confirm</span>
              <input
                aria-label="Type DELETE to confirm"
                type="text"
                value={clearConfirmText}
                onChange={(e) => setClearConfirmText(e.target.value)}
                className="mt-1 block rounded border border-border bg-bg px-3 py-1.5"
              />
            </label>
            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={clearConfirmText !== "DELETE" || clearMutation.isPending}
                onClick={() => clearMutation.mutate()}
                className="purvai-btn purvai-btn-danger rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
              >
                Confirm delete all data
              </button>
              <button
                type="button"
                onClick={() => {
                  setConfirmClear(false);
                  setClearConfirmText("");
                }}
                className="rounded border border-border px-3 py-2 text-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            onClick={() => setConfirmClear(true)}
            className="rounded border border-red-400 px-4 py-2 text-sm font-medium text-red-700"
          >
            Delete all household data
          </button>
        )}
      </div>
    </section>
  );
}
