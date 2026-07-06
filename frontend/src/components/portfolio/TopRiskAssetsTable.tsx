import type { PortfolioRiskRankingItem } from "../../types/api";
import { formatPercent, formatRiskScore } from "../../utils/formatters";
import { RiskBandBadge } from "../common/Badge";

interface Props {
  items: PortfolioRiskRankingItem[];
}

export function TopRiskAssetsTable({ items }: Props): JSX.Element {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-4 py-2">
        <h3 className="text-sm font-semibold text-slate-700">Top risk assets</h3>
        <p className="text-xs text-slate-500">
          Sorted by ML probability (desc), then risk score, then asset_id.
        </p>
      </div>
      <table className="min-w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
          <tr>
            <th className="px-3 py-2 text-right">#</th>
            <th className="px-3 py-2">Asset</th>
            <th className="px-3 py-2">Postcode</th>
            <th className="px-3 py-2">Industry</th>
            <th className="px-3 py-2">LGA</th>
            <th className="px-3 py-2 text-right">Risk score</th>
            <th className="px-3 py-2">Band</th>
            <th className="px-3 py-2 text-right">ML prob</th>
            <th className="px-3 py-2">Top driver</th>
          </tr>
        </thead>
        <tbody>
          {items.map((row) => (
            <tr key={row.asset_id} className="border-t border-slate-100">
              <td className="px-3 py-2 text-right font-mono">{row.rank}</td>
              <td className="px-3 py-2 font-mono">{row.asset_id}</td>
              <td className="px-3 py-2">{row.postcode}</td>
              <td className="px-3 py-2">{row.industry}</td>
              <td className="px-3 py-2">{row.lga_name ?? row.lga_code ?? "â€”"}</td>
              <td className="px-3 py-2 text-right">
                {formatRiskScore(row.risk_score)}
              </td>
              <td className="px-3 py-2">
                <RiskBandBadge band={row.risk_band ?? null} />
              </td>
              <td className="px-3 py-2 text-right">
                {formatPercent(row.ml_risk_probability ?? null, 2)}
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
