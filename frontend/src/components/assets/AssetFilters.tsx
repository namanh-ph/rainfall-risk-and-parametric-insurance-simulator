import { INDUSTRY_FILTER_OPTIONS, RISK_BANDS } from "../../utils/constants";

export interface AssetFilterState {
  industry: string | null;
  riskBand: string | null;
  triggeredOnly: boolean;
}

interface Props {
  value: AssetFilterState;
  onChange: (next: AssetFilterState) => void;
}

export function AssetFilters({ value, onChange }: Props): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-3">
      <label className="text-sm">
        <span className="block text-xs font-semibold uppercase text-slate-500">
          Industry
        </span>
        <select
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          value={value.industry ?? ""}
          onChange={(e) =>
            onChange({ ...value, industry: e.target.value || null })
          }
        >
          <option value="">All industries</option>
          {INDUSTRY_FILTER_OPTIONS.map((industry) => (
            <option key={industry} value={industry}>
              {industry}
            </option>
          ))}
        </select>
      </label>

      <label className="text-sm">
        <span className="block text-xs font-semibold uppercase text-slate-500">
          Risk band
        </span>
        <select
          className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
          value={value.riskBand ?? ""}
          onChange={(e) =>
            onChange({ ...value, riskBand: e.target.value || null })
          }
        >
          <option value="">All risk bands</option>
          {RISK_BANDS.map((band) => (
            <option key={band} value={band}>
              {band}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-centre gap-2 text-sm">
        <input
          type="checkbox"
          className="h-4 w-4 rounded border-slate-300"
          checked={value.triggeredOnly}
          onChange={(e) =>
            onChange({ ...value, triggeredOnly: e.target.checked })
          }
        />
        <span className="text-sm">Show only triggered assets</span>
      </label>
    </div>
  );
}
