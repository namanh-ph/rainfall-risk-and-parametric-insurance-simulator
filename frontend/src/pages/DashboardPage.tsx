import { useMemo, useState } from "react";
import { AssetDrawer } from "../components/assets/AssetDrawer";
import {
  AssetFilters,
  type AssetFilterState,
} from "../components/assets/AssetFilters";
import { EmptyState } from "../components/common/EmptyState";
import { ErrorState } from "../components/common/ErrorState";
import { LoadingState } from "../components/common/LoadingState";
import { RiskMap } from "../components/map/RiskMap";
import { PortfolioSummaryCards } from "../components/portfolio/PortfolioSummaryCards";
import {
  useMapAssets,
  useMapLgas,
  useMapStations,
} from "../hooks/useMapLayers";
import { usePortfolioSummary } from "../hooks/usePortfolio";
import {
  DEFAULT_AS_OF_DATE,
  DEFAULT_MODEL_NAME,
  DEFAULT_MODEL_VERSION,
  DEFAULT_SIMULATION_ID,
} from "../utils/constants";

export function DashboardPage(): JSX.Element {
  const [filters, setFilters] = useState<AssetFilterState>({
    industry: null,
    riskBand: null,
    triggeredOnly: false,
  });
  const [showLgas, setShowLgas] = useState(true);
  const [showStations, setShowStations] = useState(false);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const summaryQuery = usePortfolioSummary({
    as_of_date: DEFAULT_AS_OF_DATE,
    simulation_id: DEFAULT_SIMULATION_ID,
    model_name: DEFAULT_MODEL_NAME,
    model_version: DEFAULT_MODEL_VERSION,
  });

  const mapParams = useMemo(
    () => ({
      limit: 5000,
      as_of_date: DEFAULT_AS_OF_DATE,
      simulation_id: DEFAULT_SIMULATION_ID,
      model_name: DEFAULT_MODEL_NAME,
      model_version: DEFAULT_MODEL_VERSION,
      industry: filters.industry ?? undefined,
      risk_band: filters.riskBand ?? undefined,
    }),
    [filters.industry, filters.riskBand],
  );

  const mapAssetsQuery = useMapAssets(mapParams);
  const mapLgasQuery = useMapLgas({ with_aggregates: true });
  const mapStationsQuery = useMapStations({ with_aggregates: true });

  const filteredAssets = useMemo(() => {
    const fc = mapAssetsQuery.data;
    if (!fc) return undefined;
    if (!filters.triggeredOnly) return fc;
    return {
      ...fc,
      features: fc.features.filter(
        (f) => f.properties.trigger_status === "triggered",
      ),
    };
  }, [filters.triggeredOnly, mapAssetsQuery.data]);

  return (
    <div className="space-y-4">
      <section aria-label="Portfolio summary">
        {summaryQuery.isLoading ? (
          <LoadingState label="Loading portfolio summary…" />
        ) : null}
        {summaryQuery.error ? (
          <ErrorState
            error={summaryQuery.error}
            title="Could not load portfolio summary"
          />
        ) : null}
        {summaryQuery.data ? (
          <PortfolioSummaryCards summary={summaryQuery.data} />
        ) : null}
      </section>

      <AssetFilters value={filters} onChange={setFilters} />

      <div className="flex flex-wrap items-centre gap-4 text-sm">
        <label className="flex items-centre gap-2">
          <input
            type="checkbox"
            checked={showLgas}
            onChange={(e) => setShowLgas(e.target.checked)}
          />
          LGA overlay
        </label>
        <label className="flex items-centre gap-2">
          <input
            type="checkbox"
            checked={showStations}
            onChange={(e) => setShowStations(e.target.checked)}
          />
          Rainfall stations
        </label>
      </div>

      <section aria-label="Asset risk map">
        {mapAssetsQuery.isLoading ? <LoadingState label="Loading map…" /> : null}
        {mapAssetsQuery.error ? (
          <ErrorState error={mapAssetsQuery.error} title="Could not load map data" />
        ) : null}
        {mapAssetsQuery.data && mapAssetsQuery.data.features.length === 0 ? (
          <EmptyState
            title="No assets in current filters"
            message="Try widening the industry, risk-band, or triggered filters."
          />
        ) : null}
        {filteredAssets ? (
          <RiskMap
            assets={filteredAssets}
            lgas={mapLgasQuery.data}
            stations={mapStationsQuery.data}
            showLgas={showLgas}
            showStations={showStations}
            onSelectAsset={setSelectedAssetId}
          />
        ) : null}
      </section>

      <AssetDrawer
        assetId={selectedAssetId}
        onClose={() => setSelectedAssetId(null)}
      />
    </div>
  );
}
