import type { ModelPredictionItem } from "../../types/api";
import { formatPercent, formatRiskScore } from "../../utils/formatters";
import { RiskBandBadge } from "../common/Badge";

interface Props {
  items: ModelPredictionItem[];
}

export function ModelPredictionsTable({ items }: Props): JSX.Element {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-4 py-2">
        <h3 className="text-sm font-semibold text-slate-700">Model predictions</h3>
        <p className="text-xs text-slate-500">
          Read-only from <code>model_predictions</code>. Sorted by ML rank.
        </p>
      </div>
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2 text-right">Rank</th>
            <th className="px-3 py-2">Asset</th>
            <th className="px-3 py-2">Postcode</th>
            <th className="px-3 py-2">Industry</th>
            <th className="px-3 py-2 text-right">Risk score</th>
            <th className="px-3 py-2">Band</th>
            <th className="px-3 py-2 text-right">ML probability</th>
            <th className="px-3 py-2">Top driver</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.asset_id} className="border-t border-slate-100">
              <td className="px-3 py-2 text-right font-mono">
                {row.ml_risk_rank ?? "â€”"}
              </td>
              <td className="px-3 py-2 font-mono">{row.asset_id}</td>
              <td className="px-3 py-2">{row.postcode ?? "â€”"}</td>
              <td className="px-3 py-2">{row.industry ?? "â€”"}</td>
              <td className="px-3 py-2 text-right">
                {formatRiskScore(row.risk_score)}
              </td>
              <td className="px-3 py-2">
                <RiskBandBadge band={row.risk_band ?? null} />
              </td>
              <td className="px-3 py-2 text-right">
                {formatPercent(row.ml_risk_probability, 2)}
              </td>
              <td className="px-3 py-2 text-xs text-slate-700">
                {row.top_risk_driver ?? "â€”"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
