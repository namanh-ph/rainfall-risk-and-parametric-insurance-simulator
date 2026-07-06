import type { PortfolioRiskRankingItem } from "../../types/api";
import { formatCurrency, formatMm } from "../../utils/formatters";
import { RiskBandBadge } from "../common/Badge";

interface Props {
  items: PortfolioRiskRankingItem[];
}

export function TopPayoutAssetsTable({ items }: Props): JSX.Element {
  return (
    <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-200 px-4 py-2">
        <h3 className="text-sm font-semibold text-slate-700">Top payout assets</h3>
        <p className="text-xs text-slate-500">
          Sorted by estimated payout (desc), then rainfall 3-day mm, then asset_id.
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
            <th className="px-3 py-2 text-right">Rainfall 3d</th>
            <th className="px-3 py-2">Trigger</th>
            <th className="px-3 py-2 text-right">Estimated payout</th>
            <th className="px-3 py-2">Band</th>
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
                {formatMm(row.rainfall_3d_mm ?? null)}
              </td>
              <td className="px-3 py-2">{row.trigger_status ?? "â€”"}</td>
              <td className="px-3 py-2 text-right">
                {formatCurrency(row.estimated_payout ?? null)}
              </td>
              <td className="px-3 py-2">
                <RiskBandBadge band={row.risk_band ?? null} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
