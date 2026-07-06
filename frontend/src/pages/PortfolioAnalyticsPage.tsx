import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { ModelMetadataPanel } from "../components/model/ModelMetadataPanel";
import { ModelPredictionsTable } from "../components/model/ModelPredictionsTable";
import { IndustryRiskChart } from "../components/portfolio/IndustryRiskChart";
import { PortfolioSummaryCards } from "../components/portfolio/PortfolioSummaryCards";
import { RiskBandChart } from "../components/portfolio/RiskBandChart";
import { TopPayoutAssetsTable } from "../components/portfolio/TopPayoutAssetsTable";
import { TopRiskAssetsTable } from "../components/portfolio/TopRiskAssetsTable";
import { ReportExportPanel } from "../components/reports/ReportExportPanel";
import { PayoutSimulatorPanel } from "../components/simulation/PayoutSimulatorPanel";
import { useModelMetadata, useModelPredictions } from "../hooks/useModel";
import {
  usePortfolioRiskRanking,
  usePortfolioSummary,
} from "../hooks/usePortfolio";
import {
  DEFAULT_AS_OF_DATE,
  DEFAULT_FEATURE_VERSION,
  DEFAULT_MODEL_NAME,
  DEFAULT_MODEL_VERSION,
  DEFAULT_SIMULATION_ID,
} from "../utils/constants";

const COMMON_PARAMS = {
  as_of_date: DEFAULT_AS_OF_DATE,
  simulation_id: DEFAULT_SIMULATION_ID,
  model_name: DEFAULT_MODEL_NAME,
  model_version: DEFAULT_MODEL_VERSION,
} as const;

export function PortfolioAnalyticsPage(): JSX.Element {
  const summaryQuery = usePortfolioSummary(COMMON_PARAMS);
  const topRiskQuery = usePortfolioRiskRanking({
    ...COMMON_PARAMS,
    limit: 20,
    sort_by: "ml_risk_probability",
    sort_order: "desc",
  });
  const topPayoutQuery = usePortfolioRiskRanking({
    ...COMMON_PARAMS,
    limit: 20,
    sort_by: "estimated_payout",
    sort_order: "desc",
  });
  const modelMetadataQuery = useModelMetadata({
    as_of_date: DEFAULT_AS_OF_DATE,
    model_name: DEFAULT_MODEL_NAME,
    model_version: DEFAULT_MODEL_VERSION,
    feature_version: DEFAULT_FEATURE_VERSION,
  });
  const predictionsQuery = useModelPredictions({
    as_of_date: DEFAULT_AS_OF_DATE,
    model_name: DEFAULT_MODEL_NAME,
    model_version: DEFAULT_MODEL_VERSION,
    limit: 20,
    sort_by: "ml_risk_rank",
    sort_order: "asc",
  });

  return (
    <div className="space-y-6">
      <section aria-label="Portfolio summary">
        {summaryQuery.isLoading ? <LoadingState /> : null}
        {summaryQuery.error ? (
          <ErrorState error={summaryQuery.error} title="Could not load summary" />
        ) : null}
        {summaryQuery.data ? (
          <PortfolioSummaryCards summary={summaryQuery.data} />
        ) : null}
      </section>

      <section
        aria-label="Risk distributions"
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
      >
        {summaryQuery.data ? (
          <>
            <RiskBandChart data={summaryQuery.data.risk_band_distribution} />
            <IndustryRiskChart data={summaryQuery.data.industry_summary} />
          </>
        ) : null}
      </section>

      <section aria-label="Top risk assets" className="space-y-2">
        {topRiskQuery.isLoading ? <LoadingState /> : null}
        {topRiskQuery.error ? (
          <ErrorState error={topRiskQuery.error} title="Could not load top risk assets" />
        ) : null}
        {topRiskQuery.data && topRiskQuery.data.items.length === 0 ? (
          <EmptyState
            title="No top risk assets"
            message="The risk-ranking endpoint returned no rows."
          />
        ) : null}
        {topRiskQuery.data && topRiskQuery.data.items.length > 0 ? (
          <TopRiskAssetsTable items={topRiskQuery.data.items} />
        ) : null}
      </section>

      <section aria-label="Top payout assets" className="space-y-2">
        {topPayoutQuery.isLoading ? <LoadingState /> : null}
        {topPayoutQuery.error ? (
          <ErrorState
            error={topPayoutQuery.error}
            title="Could not load top payout assets"
          />
        ) : null}
        {topPayoutQuery.data && topPayoutQuery.data.items.length === 0 ? (
          <EmptyState
            title="No top payout assets"
            message="Re-run payout simulation to populate triggered rows."
          />
        ) : null}
        {topPayoutQuery.data && topPayoutQuery.data.items.length > 0 ? (
          <TopPayoutAssetsTable items={topPayoutQuery.data.items} />
        ) : null}
      </section>

      <section aria-label="Model metadata">
        {modelMetadataQuery.isLoading ? <LoadingState /> : null}
        {modelMetadataQuery.error ? (
          <ErrorState
            error={modelMetadataQuery.error}
            title="Could not load model metadata"
          />
        ) : null}
        {modelMetadataQuery.data ? (
          <ModelMetadataPanel metadata={modelMetadataQuery.data} />
        ) : null}
      </section>

      <section aria-label="Model predictions">
        {predictionsQuery.isLoading ? <LoadingState /> : null}
        {predictionsQuery.error ? (
          <ErrorState
            error={predictionsQuery.error}
            title="Could not load predictions"
          />
        ) : null}
        {predictionsQuery.data && predictionsQuery.data.items.length === 0 ? (
          <EmptyState
            title="No model predictions"
            message="Run make seed-predictions to populate model_predictions."
          />
        ) : null}
        {predictionsQuery.data && predictionsQuery.data.items.length > 0 ? (
          <ModelPredictionsTable items={predictionsQuery.data.items} />
        ) : null}
      </section>

      <section
        aria-label="Mutating actions"
        className="grid grid-cols-1 gap-4 lg:grid-cols-2"
      >
        <PayoutSimulatorPanel />
        <ReportExportPanel />
      </section>
    </div>
  );
}
