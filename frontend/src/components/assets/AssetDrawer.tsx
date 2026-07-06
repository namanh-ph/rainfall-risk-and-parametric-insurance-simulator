import { X } from "lucide-react";
import {
  useAssetDetail,
  useAssetRainfall,
  useAssetRisk,
  useAssetStation,
} from "../../hooks/useAssets";
import { useModelPredictionDetail } from "../../hooks/useModel";
import {
  formatCurrency,
  formatDistanceKm,
  formatMm,
  formatPercent,
  formatRiskScore,
} from "../../utils/formatters";
import { RiskBandBadge } from "../common/Badge";
import { EmptyState } from "../common/EmptyState";
import { ErrorState } from "../common/ErrorState";
import { LoadingState } from "../common/LoadingState";

interface Props {
  assetId: string | null;
  onClose: () => void;
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold uppercase text-slate-500">{title}</h3>
      <div className="space-y-1 text-sm">{children}</div>
    </section>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value ?? "â€”"}</span>
    </div>
  );
}

export function AssetDrawer({ assetId, onClose }: Props): JSX.Element | null {
  const detailQuery = useAssetDetail(assetId);
  const riskQuery = useAssetRisk(assetId);
  const rainfallQuery = useAssetRainfall(assetId);
  const stationQuery = useAssetStation(assetId);
  const predictionQuery = useModelPredictionDetail(assetId);

  if (!assetId) return null;
  const detail = detailQuery.data;

  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-label="Asset details"
      className="fixed inset-y-0 right-0 z-[500] flex w-full flex-col border-l border-slate-200 bg-white shadow-xl md:w-[420px]"
    >
      <header className="flex items-centre justify-between border-b border-slate-200 px-4 py-3">
        <div>
          <p className="text-xs uppercase text-slate-500">Asset</p>
          <h2 className="text-lg font-semibold text-brand">{assetId}</h2>
        </div>
        <button
          type="button"
          aria-label="Close asset drawer"
          onClick={onClose}
          className="rounded-md p-2 text-slate-500 hover:bg-slate-100"
        >
          <X className="h-4 w-4" />
        </button>
      </header>

      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {detailQuery.isLoading ? <LoadingState label="Loading asset detailsâ€¦" /> : null}
        {detailQuery.error ? (
          <ErrorState error={detailQuery.error} title="Could not load asset" />
        ) : null}

        {detail ? (
          <>
            <Section title="Profile">
              <Field label="Postcode" value={detail.postcode} />
              <Field label="Industry" value={detail.industry} />
              <Field label="Business type" value={detail.business_type} />
              <Field label="LGA" value={detail.lga_name ?? detail.lga_code ?? "â€”"} />
              <Field label="Asset value" value={formatCurrency(detail.asset_value)} />
              <Field
                label="Coverage limit"
                value={formatCurrency(detail.coverage_limit)}
              />
            </Section>

            <Section title="Risk">
              {riskQuery.isLoading ? <LoadingState /> : null}
              {riskQuery.data ? (
                <>
                  <Field
                    label="Score"
                    value={
                      <span className="flex items-centre gap-2">
                        {formatRiskScore(riskQuery.data.risk_score)}
                        <RiskBandBadge band={riskQuery.data.risk_band} />
                      </span>
                    }
                  />
                  <Field
                    label="Raw score"
                    value={formatRiskScore(riskQuery.data.raw_score)}
                  />
                  <Field
                    label="Exposure weight"
                    value={formatRiskScore(riskQuery.data.exposure_weight)}
                  />
                  <Field
                    label="Vulnerability weight"
                    value={formatRiskScore(riskQuery.data.vulnerability_weight)}
                  />
                </>
              ) : null}
              {!riskQuery.isLoading && !riskQuery.data ? (
                <EmptyState
                  title="No risk score"
                  message="No persisted risk score for this asset and as-of date."
                />
              ) : null}
            </Section>

            <Section title="Rainfall">
              {rainfallQuery.isLoading ? <LoadingState /> : null}
              {rainfallQuery.data ? (
                <>
                  <Field
                    label="3-day rainfall"
                    value={formatMm(rainfallQuery.data.rainfall_3d_mm)}
                  />
                  <Field
                    label="7-day rainfall"
                    value={formatMm(rainfallQuery.data.rainfall_7d_mm)}
                  />
                  <Field
                    label="Percentile"
                    value={formatPercent(
                      rainfallQuery.data.rainfall_percentile ?? null,
                      2,
                    )}
                  />
                  <Field
                    label="Extreme flag"
                    value={rainfallQuery.data.extreme_rainfall_flag ? "Yes" : "No"}
                  />
                </>
              ) : null}
              {!rainfallQuery.isLoading && !rainfallQuery.data ? (
                <EmptyState
                  title="No rainfall features"
                  message="No persisted rainfall feature row for this asset."
                />
              ) : null}
            </Section>

            <Section title="Station">
              {stationQuery.isLoading ? <LoadingState /> : null}
              {stationQuery.data ? (
                <>
                  <Field label="Station" value={stationQuery.data.station_name} />
                  <Field
                    label="Distance"
                    value={formatDistanceKm(stationQuery.data.station_distance_km)}
                  />
                  <Field
                    label="Confidence"
                    value={formatRiskScore(
                      stationQuery.data.station_confidence_weight,
                    )}
                  />
                </>
              ) : null}
              {!stationQuery.isLoading && !stationQuery.data ? (
                <EmptyState
                  title="No station mapping"
                  message="No nearest-station record for this asset."
                />
              ) : null}
            </Section>

            <Section title="ML prediction">
              {predictionQuery.isLoading ? <LoadingState /> : null}
              {predictionQuery.data ? (
                <>
                  <Field
                    label="Probability"
                    value={formatPercent(
                      predictionQuery.data.ml_risk_probability,
                      2,
                    )}
                  />
                  <Field
                    label="Rank"
                    value={predictionQuery.data.ml_risk_rank ?? "â€”"}
                  />
                  <Field
                    label="Top driver"
                    value={predictionQuery.data.top_risk_driver ?? "â€”"}
                  />
                </>
              ) : null}
              {!predictionQuery.isLoading && !predictionQuery.data ? (
                <EmptyState
                  title="No ML prediction"
                  message="No persisted prediction row for this asset."
                />
              ) : null}
            </Section>
          </>
        ) : null}
      </div>
    </aside>
  );
}
