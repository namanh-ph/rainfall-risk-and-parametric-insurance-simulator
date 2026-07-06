import type { ModelMetadataResponse } from "../../types/api";
import { formatNumber, formatPercent } from "../../utils/formatters";
import { EmptyState } from "../common/EmptyState";

interface Props {
  metadata: ModelMetadataResponse | undefined;
}

function Row({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-baseline justify-between border-b border-slate-100 py-1 last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value ?? "-"}</span>
    </div>
  );
}

function num(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return formatNumber(value, value % 1 === 0 ? 0 : 4);
}

export function ModelMetadataPanel({ metadata }: Props): JSX.Element {
  if (!metadata) {
    return (
      <EmptyState
        title="Model metadata"
        message="Model metadata endpoint returned no payload."
      />
    );
  }

  const metrics = metadata.metrics ?? {};
  const artefactWarning =
    !metadata.metrics && metadata.prediction_count === 0
      ? "No artefact files or persisted predictions detected; train the model and run batch prediction first."
      : null;

  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h3 className="text-sm font-semibold text-slate-700">Model metadata</h3>
        <p className="text-xs text-slate-500">
          Read-only from <code>backend/artifacts/models/</code> and
          <code> model_predictions</code>.
        </p>
      </div>

      {artefactWarning ? (
        <p
          role="status"
          className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          {artefactWarning}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <div>
          <Row label="Model name" value={metadata.model_name} />
          <Row label="Model version" value={metadata.model_version} />
          <Row label="Feature version" value={metadata.feature_version ?? "-"} />
          <Row label="Target name" value={metadata.target_name ?? "-"} />
          <Row label="Feature count" value={num(metadata.feature_count)} />
          <Row label="Train rows" value={num(metadata.train_row_count)} />
          <Row label="Test rows" value={num(metadata.test_row_count)} />
          <Row
            label="Positive rate"
            value={formatPercent(metadata.positive_rate ?? null, 2)}
          />
          <Row label="Predictions" value={num(metadata.prediction_count)} />
          <Row label="MLflow run" value={metadata.mlflow_run_id ?? "-"} />
        </div>
        <div>
          <h4 className="text-xs font-semibold uppercase text-slate-500">
            Metrics
          </h4>
          <Row label="roc_auc" value={num(metrics["roc_auc"])} />
          <Row label="pr_auc" value={num(metrics["pr_auc"])} />
          <Row label="accuracy" value={num(metrics["accuracy"])} />
          <Row label="precision" value={num(metrics["precision"])} />
          <Row label="recall" value={num(metrics["recall"])} />
          <Row label="f1" value={num(metrics["f1"])} />
          <Row
            label="precision@10%"
            value={num(metrics["precision_at_top_10_pct"])}
          />
          <Row
            label="recall@10%"
            value={num(metrics["recall_at_top_10_pct"])}
          />
          <Row
            label="lift@10%"
            value={num(metrics["lift_at_top_10_pct"])}
          />
        </div>
      </div>
    </div>
  );
}
