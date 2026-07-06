import { useState } from "react";
import { useReportExportMutation } from "../../hooks/useReportExport";
import { formatDateTime, formatFileSize } from "../../utils/formatters";
import { ErrorState } from "../common/ErrorState";

interface FormState {
  report_title: string;
  top_n: number;
  include_methodology: boolean;
  include_top_assets: boolean;
}

const INITIAL: FormState = {
  report_title: "Portfolio Risk Report",
  top_n: 20,
  include_methodology: true,
  include_top_assets: true,
};

export function ReportExportPanel(): JSX.Element {
  const [form, setForm] = useState<FormState>(INITIAL);
  const mutation = useReportExportMutation();

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h3 className="text-sm font-semibold text-slate-700">Export HTML report</h3>
        <p className="text-xs text-slate-500">
          Submits to <code>POST /api/v1/reports/export</code>. The HTML file is
          written under <code>backend/artifacts/reports/</code> on the backend
          filesystem — it is not downloaded by the browser.
        </p>
      </div>

      <form
        className="grid grid-cols-1 gap-3 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate({
            report_title: form.report_title,
            top_n: Number(form.top_n),
            include_methodology: form.include_methodology,
            include_top_assets: form.include_top_assets,
          });
        }}
      >
        <label className="text-sm md:col-span-2">
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Report title
          </span>
          <input
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={form.report_title}
            onChange={(e) =>
              setForm({ ...form, report_title: e.target.value })
            }
            required
          />
        </label>
        <label className="text-sm">
          <span className="block text-xs font-semibold uppercase text-slate-500">
            Top N (1–100)
          </span>
          <input
            type="number"
            min={1}
            max={100}
            className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            value={form.top_n}
            onChange={(e) => setForm({ ...form, top_n: Number(e.target.value) })}
          />
        </label>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.include_methodology}
              onChange={(e) =>
                setForm({ ...form, include_methodology: e.target.checked })
              }
            />
            Include methodology
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.include_top_assets}
              onChange={(e) =>
                setForm({ ...form, include_top_assets: e.target.checked })
              }
            />
            Include top assets
          </label>
        </div>
        <div className="md:col-span-2">
          <button
            type="submit"
            disabled={mutation.isPending}
            className="rounded-md bg-brand px-3 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand/90 disabled:opacity-50"
          >
            {mutation.isPending ? "Exporting…" : "Export report"}
          </button>
        </div>
      </form>

      {mutation.isError ? (
        <ErrorState error={mutation.error} title="Report export failed" />
      ) : null}

      {mutation.data ? (
        <div
          data-testid="report-export-result"
          className="space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm"
        >
          <p className="font-semibold text-slate-700">Report written successfully</p>
          <dl className="grid grid-cols-1 gap-1 text-xs text-slate-700 md:grid-cols-2">
            <div>
              <dt className="text-slate-500">Report ID</dt>
              <dd className="font-mono">{mutation.data.report_id}</dd>
            </div>
            <div>
              <dt className="text-slate-500">File size</dt>
              <dd>{formatFileSize(mutation.data.file_size_bytes)}</dd>
            </div>
            <div className="md:col-span-2">
              <dt className="text-slate-500">Output path</dt>
              <dd className="break-all font-mono">{mutation.data.output_path}</dd>
            </div>
            <div className="md:col-span-2">
              <dt className="text-slate-500">Relative path</dt>
              <dd className="break-all font-mono">
                {mutation.data.relative_output_path}
              </dd>
            </div>
            <div>
              <dt className="text-slate-500">Created at</dt>
              <dd>{formatDateTime(mutation.data.created_at)}</dd>
            </div>
          </dl>

          <div>
            <p className="text-xs font-semibold text-slate-600">Sections</p>
            <ul className="mt-1 list-disc pl-5 text-xs text-slate-700">
              {mutation.data.sections.map((section) => (
                <li key={section.section}>
                  <span className="font-mono">{section.section}</span>:{" "}
                  available={String(section.available)}, rows={section.row_count}
                </li>
              ))}
            </ul>
          </div>

          {mutation.data.warnings.length > 0 ? (
            <div>
              <p className="text-xs font-semibold text-amber-700">Warnings</p>
              <ul className="mt-1 list-disc pl-5 text-xs text-amber-700">
                {mutation.data.warnings.map((warning, idx) => (
                  <li key={idx}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
