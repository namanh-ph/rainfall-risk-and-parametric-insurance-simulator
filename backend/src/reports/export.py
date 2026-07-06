"""HTML portfolio report data assembly, rendering, and writing.

Reads persisted analytics outputs and writes a static HTML file.
Read-only against domain tables.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.reports.methodology import get_methodology_notes
from src.schemas.api_reports import ReportExportRequest

logger = logging.getLogger(__name__)

DEFAULT_REPORT_OUTPUT_DIR = Path("backend/artifacts/reports")
LOCAL_REPORT_OUTPUT_DIR = Path("artifacts/reports")
DEFAULT_ARTIFACT_DIR_ROOT = Path("backend/artifacts/models")
LOCAL_ARTIFACT_DIR_ROOT = Path("artifacts/models")

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_TEMPLATE_FILENAME = "portfolio_report.html.j2"

_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]+\.html$")
_SAFE_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(value: str) -> str:
    """Sanitize a free-form value for use in a filename component."""
    cleaned = _SAFE_SLUG.sub("_", value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "x"


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, Decimal):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_output_root(output_dir: str | Path | None) -> Path:
    """Pick the first writable / existing report output root.

    Mirrors the pattern used in routes_model._default_artifact_dir() so
    the CLI (invoked from backend/) and the API (invoked from repo
    root) both behave correctly.
    """
    if output_dir is not None:
        return Path(output_dir).resolve()

    candidates = (
        LOCAL_REPORT_OUTPUT_DIR,
        DEFAULT_REPORT_OUTPUT_DIR,
        Path("backend/artifacts/reports"),
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    return candidates[0].resolve()


def build_report_id(
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
) -> str:
    """Deterministic, filesystem-safe report identifier."""
    return "_".join(
        [
            "portfolio_report",
            as_of_date.isoformat(),
            _slug(simulation_id),
            _slug(model_name),
            _slug(model_version),
        ]
    )


def resolve_report_output_path(
    output_filename: str | None,
    report_id: str,
    output_dir: str | Path | None = None,
) -> Path:
    """Resolve the final on-disk path for the generated report.

    Raises ``ValueError`` if the supplied ``output_filename`` would
    escape the resolved report directory (path traversal).
    """
    root = _resolve_output_root(output_dir)
    if output_filename is None or not output_filename.strip():
        filename = f"{report_id}.html"
    else:
        candidate = output_filename.strip()
        if (
            ".." in candidate
            or "/" in candidate
            or "\\" in candidate
            or os.path.isabs(candidate)
            or not _SAFE_FILENAME.match(candidate)
        ):
            raise ValueError(
                "output_filename must be a safe .html filename without path components"
            )
        filename = candidate

    candidate_path = (root / filename).resolve()
    try:
        candidate_path.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "output_filename must resolve under the report output directory"
        ) from exc
    return candidate_path


_PORTFOLIO_BASE_FROM = """
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN rainfall_features rf
    ON rf.asset_id = a.asset_id AND rf.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
LEFT JOIN model_predictions mp
    ON mp.asset_id = a.asset_id
    AND mp.as_of_date = :as_of_date
    AND mp.model_name = :model_name
    AND mp.model_version = :model_version
"""


def fetch_report_portfolio_summary(
    db: Session,
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
) -> dict[str, Any]:
    """Portfolio-level totals plus risk-band distribution."""
    params: dict[str, Any] = {
        "as_of_date": as_of_date,
        "simulation_id": simulation_id,
        "model_name": model_name,
        "model_version": model_version,
    }
    totals_sql = text(
        f"""
SELECT
    COUNT(*) AS total_assets,
    COALESCE(SUM(a.asset_value), 0) AS total_asset_value,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout,
    AVG(mp.ml_risk_probability) AS average_ml_risk_probability
{_PORTFOLIO_BASE_FROM}
"""
    )
    row = db.execute(totals_sql, params).first()
    totals = dict(row._mapping) if row else {}

    bands_sql = text(
        """
SELECT
    ars.risk_band AS risk_band,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
WHERE ars.risk_band IN ('Low','Medium','High','Severe')
GROUP BY ars.risk_band
ORDER BY
    CASE ars.risk_band
        WHEN 'Low' THEN 1
        WHEN 'Medium' THEN 2
        WHEN 'High' THEN 3
        WHEN 'Severe' THEN 4
    END
"""
    )
    bands = [
        {
            "risk_band": r._mapping["risk_band"],
            "asset_count": _coerce_int(r._mapping["asset_count"]) or 0,
            "average_risk_score": _coerce_float(r._mapping["average_risk_score"]),
            "total_coverage_limit": _coerce_float(r._mapping["total_coverage_limit"]) or 0.0,
            "total_estimated_payout": _coerce_float(r._mapping["total_estimated_payout"])
            or 0.0,
        }
        for r in db.execute(
            bands_sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]

    return {
        "total_assets": _coerce_int(totals.get("total_assets")) or 0,
        "total_asset_value": _coerce_float(totals.get("total_asset_value")) or 0.0,
        "total_coverage_limit": _coerce_float(totals.get("total_coverage_limit")) or 0.0,
        "average_risk_score": _coerce_float(totals.get("average_risk_score")),
        "high_or_severe_assets": _coerce_int(totals.get("high_or_severe_assets")) or 0,
        "triggered_assets": _coerce_int(totals.get("triggered_assets")) or 0,
        "total_estimated_payout": _coerce_float(totals.get("total_estimated_payout")) or 0.0,
        "average_ml_risk_probability": _coerce_float(
            totals.get("average_ml_risk_probability")
        ),
        "risk_band_distribution": bands,
    }


def fetch_report_top_risk_assets(
    db: Session,
    as_of_date: date,
    simulation_id: str,
    model_name: str,
    model_version: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top assets ordered by ML probability, risk score, then asset_id."""
    params: dict[str, Any] = {
        "as_of_date": as_of_date,
        "simulation_id": simulation_id,
        "model_name": model_name,
        "model_version": model_version,
        "limit": int(limit),
    }
    sql = text(
        f"""
SELECT
    a.asset_id, a.industry, a.postcode,
    a.lga_code, l.lga_name,
    ars.risk_score, ars.risk_band,
    rf.rainfall_3d_mm,
    pr.estimated_payout,
    mp.ml_risk_probability, mp.ml_risk_rank, mp.top_risk_driver
{_PORTFOLIO_BASE_FROM}
ORDER BY
    mp.ml_risk_probability DESC NULLS LAST,
    ars.risk_score DESC NULLS LAST,
    a.asset_id ASC
LIMIT :limit
"""
    )
    rows: list[dict[str, Any]] = []
    for rank, r in enumerate(db.execute(sql, params), start=1):
        m = r._mapping
        rows.append(
            {
                "rank": rank,
                "asset_id": m["asset_id"],
                "postcode": m["postcode"],
                "industry": m["industry"],
                "lga_name": m["lga_name"],
                "risk_score": _coerce_float(m["risk_score"]),
                "risk_band": m["risk_band"],
                "ml_risk_probability": _coerce_float(m["ml_risk_probability"]),
                "ml_risk_rank": _coerce_int(m["ml_risk_rank"]),
                "top_risk_driver": m["top_risk_driver"],
                "rainfall_3d_mm": _coerce_float(m["rainfall_3d_mm"]),
                "estimated_payout": _coerce_float(m["estimated_payout"]),
            }
        )
    return rows


def fetch_report_top_payout_assets(
    db: Session,
    simulation_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Top assets ordered by estimated_payout, rainfall_3d_mm, then asset_id."""
    params: dict[str, Any] = {
        "simulation_id": simulation_id,
        "limit": int(limit),
    }
    sql = text(
        """
SELECT
    a.asset_id, a.industry, a.postcode,
    a.lga_code, l.lga_name,
    pr.rainfall_3d_mm, pr.trigger_status, pr.payout_rate,
    pr.coverage_limit, pr.estimated_payout, pr.risk_band
FROM payout_results pr
JOIN assets a ON a.asset_id = pr.asset_id
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
WHERE pr.simulation_id = :simulation_id
ORDER BY
    pr.estimated_payout DESC NULLS LAST,
    pr.rainfall_3d_mm DESC NULLS LAST,
    a.asset_id ASC
LIMIT :limit
"""
    )
    rows: list[dict[str, Any]] = []
    for rank, r in enumerate(db.execute(sql, params), start=1):
        m = r._mapping
        rows.append(
            {
                "rank": rank,
                "asset_id": m["asset_id"],
                "postcode": m["postcode"],
                "industry": m["industry"],
                "lga_name": m["lga_name"],
                "rainfall_3d_mm": _coerce_float(m["rainfall_3d_mm"]),
                "trigger_status": m["trigger_status"],
                "payout_rate": _coerce_float(m["payout_rate"]),
                "coverage_limit": _coerce_float(m["coverage_limit"]),
                "estimated_payout": _coerce_float(m["estimated_payout"]),
                "risk_band": m["risk_band"],
            }
        )
    return rows


def fetch_report_risk_by_industry(
    db: Session,
    as_of_date: date,
    simulation_id: str,
) -> list[dict[str, Any]]:
    """Industry-level summary identical to /portfolio/summary semantics."""
    sql = text(
        """
SELECT
    a.industry AS industry,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
GROUP BY a.industry
ORDER BY a.industry ASC
"""
    )
    return [
        {
            "industry": r._mapping["industry"],
            "asset_count": _coerce_int(r._mapping["asset_count"]) or 0,
            "average_risk_score": _coerce_float(r._mapping["average_risk_score"]),
            "high_or_severe_assets": _coerce_int(r._mapping["high_or_severe_assets"]) or 0,
            "triggered_assets": _coerce_int(r._mapping["triggered_assets"]) or 0,
            "total_coverage_limit": _coerce_float(r._mapping["total_coverage_limit"])
            or 0.0,
            "total_estimated_payout": _coerce_float(r._mapping["total_estimated_payout"])
            or 0.0,
        }
        for r in db.execute(
            sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]


def fetch_report_risk_by_lga(
    db: Session,
    as_of_date: date,
    simulation_id: str,
) -> list[dict[str, Any]]:
    """LGA-level summary."""
    sql = text(
        """
SELECT
    a.lga_code AS lga_code,
    l.lga_name AS lga_name,
    COUNT(*) AS asset_count,
    AVG(ars.risk_score) AS average_risk_score,
    COALESCE(COUNT(*) FILTER (WHERE ars.risk_band IN ('High','Severe')), 0)
        AS high_or_severe_assets,
    COALESCE(COUNT(*) FILTER (WHERE pr.trigger_status = 'triggered'), 0)
        AS triggered_assets,
    COALESCE(SUM(a.coverage_limit), 0) AS total_coverage_limit,
    COALESCE(SUM(pr.estimated_payout), 0) AS total_estimated_payout
FROM assets a
LEFT JOIN lga_boundaries l ON l.lga_code = a.lga_code
LEFT JOIN asset_risk_scores ars
    ON ars.asset_id = a.asset_id AND ars.as_of_date = :as_of_date
LEFT JOIN payout_results pr
    ON pr.asset_id = a.asset_id AND pr.simulation_id = :simulation_id
WHERE a.lga_code IS NOT NULL
GROUP BY a.lga_code, l.lga_name
ORDER BY a.lga_code ASC
"""
    )
    return [
        {
            "lga_code": r._mapping["lga_code"],
            "lga_name": r._mapping["lga_name"],
            "asset_count": _coerce_int(r._mapping["asset_count"]) or 0,
            "average_risk_score": _coerce_float(r._mapping["average_risk_score"]),
            "high_or_severe_assets": _coerce_int(r._mapping["high_or_severe_assets"]) or 0,
            "triggered_assets": _coerce_int(r._mapping["triggered_assets"]) or 0,
            "total_coverage_limit": _coerce_float(r._mapping["total_coverage_limit"])
            or 0.0,
            "total_estimated_payout": _coerce_float(r._mapping["total_estimated_payout"])
            or 0.0,
        }
        for r in db.execute(
            sql, {"as_of_date": as_of_date, "simulation_id": simulation_id}
        )
    ]


def _resolve_artifact_dir(
    model_name: str,
    model_version: str,
    as_of_date: date,
    artifact_dir: str | Path | None,
) -> Path:
    if artifact_dir is not None:
        return Path(artifact_dir)
    name = f"{model_name}_{model_version}_{as_of_date.isoformat()}"
    candidates = (
        LOCAL_ARTIFACT_DIR_ROOT / name,
        DEFAULT_ARTIFACT_DIR_ROOT / name,
        Path("backend/artifacts/models") / name,
    )
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def fetch_report_model_metadata(
    db: Session,
    as_of_date: date,
    model_name: str,
    model_version: str,
    feature_version: str,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Load artefact metadata + prediction count.

    Missing artefact files produce a warning rather than a failure.
    """
    warnings: list[str] = []
    base = _resolve_artifact_dir(model_name, model_version, as_of_date, artifact_dir)
    metadata: dict[str, Any] = {}
    metadata_file = base / "metadata.json"
    metrics_file = base / "metrics.json"

    if metadata_file.is_file():
        try:
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.append(f"Failed to parse metadata.json: {exc}")
            metadata = {}
    else:
        warnings.append(
            f"metadata.json not found at {metadata_file}; "
            "model metadata section is degraded."
        )

    if metrics_file.is_file():
        try:
            metadata["metrics"] = json.loads(metrics_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.append(f"Failed to parse metrics.json: {exc}")
    else:
        warnings.append(
            f"metrics.json not found at {metrics_file}; metrics will be omitted."
        )

    count_sql = text(
        """
SELECT COUNT(*) FROM model_predictions
WHERE as_of_date = :as_of_date
  AND model_name = :model_name
  AND model_version = :model_version
"""
    )
    prediction_count = (
        db.execute(
            count_sql,
            {
                "as_of_date": as_of_date,
                "model_name": model_name,
                "model_version": model_version,
            },
        ).scalar()
        or 0
    )

    return {
        "model_name": metadata.get("model_name") or model_name,
        "model_version": metadata.get("model_version") or model_version,
        "feature_version": metadata.get("feature_version") or feature_version,
        "target_name": metadata.get("target_name"),
        "train_row_count": metadata.get("train_row_count"),
        "test_row_count": metadata.get("test_row_count"),
        "feature_count": metadata.get("feature_count"),
        "positive_rate": metadata.get("positive_rate"),
        "metrics": metadata.get("metrics"),
        "mlflow_run_id": metadata.get("mlflow_run_id"),
        "prediction_count": int(prediction_count),
        "artifact_path": metadata.get("artifact_path") or str(base),
        "warnings": warnings,
    }


def _build_section_status(
    section: str, rows: list[Any] | None, *, message: str | None = None
) -> dict[str, Any]:
    if rows is None:
        return {
            "section": section,
            "available": False,
            "row_count": 0,
            "message": message or f"No data available for section '{section}'.",
        }
    return {
        "section": section,
        "available": len(rows) > 0,
        "row_count": len(rows),
        "message": (
            None
            if rows
            else (message or f"Section '{section}' returned zero rows.")
        ),
    }


def assemble_report_context(
    db: Session,
    request: ReportExportRequest,
) -> dict[str, Any]:
    """Build the dictionary fed into the Jinja2 template."""
    warnings: list[str] = []
    sections: list[dict[str, Any]] = []

    report_id = build_report_id(
        request.as_of_date,
        request.simulation_id,
        request.model_name,
        request.model_version,
    )

    portfolio_summary = fetch_report_portfolio_summary(
        db,
        as_of_date=request.as_of_date,
        simulation_id=request.simulation_id,
        model_name=request.model_name,
        model_version=request.model_version,
    )
    sections.append(
        _build_section_status(
            "portfolio_summary",
            [portfolio_summary] if portfolio_summary.get("total_assets") else [],
            message=(
                "Portfolio summary is empty - no assets found for the "
                "requested as_of_date / simulation_id."
            ),
        )
    )
    if (portfolio_summary.get("total_assets") or 0) == 0:
        warnings.append(
            "Portfolio summary returned zero assets - verify ingestion has been run."
        )

    top_risk_assets: list[dict[str, Any]] = []
    top_payout_assets: list[dict[str, Any]] = []
    if request.include_top_assets:
        top_risk_assets = fetch_report_top_risk_assets(
            db,
            as_of_date=request.as_of_date,
            simulation_id=request.simulation_id,
            model_name=request.model_name,
            model_version=request.model_version,
            limit=request.top_n,
        )
        top_payout_assets = fetch_report_top_payout_assets(
            db,
            simulation_id=request.simulation_id,
            limit=request.top_n,
        )
        sections.append(_build_section_status("top_risk_assets", top_risk_assets))
        sections.append(_build_section_status("top_payout_assets", top_payout_assets))
        if not top_risk_assets:
            warnings.append(
                "Top risk assets section is empty - model predictions may be missing."
            )
        if not top_payout_assets:
            warnings.append(
                "Top payout assets section is empty - payout simulation may be missing."
            )
    else:
        sections.append(
            _build_section_status(
                "top_risk_assets", None, message="Top assets disabled by request."
            )
        )
        sections.append(
            _build_section_status(
                "top_payout_assets", None, message="Top assets disabled by request."
            )
        )

    risk_by_industry = fetch_report_risk_by_industry(
        db, as_of_date=request.as_of_date, simulation_id=request.simulation_id
    )
    sections.append(_build_section_status("risk_by_industry", risk_by_industry))

    risk_by_lga = fetch_report_risk_by_lga(
        db, as_of_date=request.as_of_date, simulation_id=request.simulation_id
    )
    sections.append(_build_section_status("risk_by_lga", risk_by_lga))
    if not risk_by_lga:
        warnings.append(
            "Risk-by-LGA section is empty - asset-to-LGA assignment may be missing."
        )

    model_metadata = fetch_report_model_metadata(
        db,
        as_of_date=request.as_of_date,
        model_name=request.model_name,
        model_version=request.model_version,
        feature_version=request.feature_version,
    )
    metadata_warnings = model_metadata.pop("warnings", [])
    warnings.extend(metadata_warnings)
    metadata_available = bool(
        model_metadata.get("metrics") or model_metadata.get("prediction_count")
    )
    sections.append(
        {
            "section": "model_metadata",
            "available": metadata_available,
            "row_count": int(model_metadata.get("prediction_count") or 0),
            "message": (
                None
                if metadata_available
                else "Model metadata artefacts and predictions are unavailable."
            ),
        }
    )

    methodology = get_methodology_notes()

    context: dict[str, Any] = {
        "report_id": report_id,
        "report_title": request.report_title,
        "as_of_date": request.as_of_date,
        "simulation_id": request.simulation_id,
        "model_name": request.model_name,
        "model_version": request.model_version,
        "feature_version": request.feature_version,
        "generated_at": datetime.now(UTC),
        "include_methodology": request.include_methodology,
        "include_top_assets": request.include_top_assets,
        "top_n": request.top_n,
        "portfolio_summary": portfolio_summary,
        "top_risk_assets": top_risk_assets,
        "top_payout_assets": top_payout_assets,
        "risk_by_industry": risk_by_industry,
        "risk_by_lga": risk_by_lga,
        "model_metadata": model_metadata,
        "methodology": methodology,
        "sections": sections,
        "warnings": warnings,
    }
    return context


def _build_environment(template_path: str | Path | None) -> tuple[Environment, str]:
    """Return a Jinja2 ``Environment`` plus the resolved template name."""
    if template_path is None:
        env = Environment(
            loader=FileSystemLoader(str(TEMPLATE_DIR)),
            autoescape=select_autoescape(("html", "htm", "xml", "j2")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        return env, DEFAULT_TEMPLATE_FILENAME

    template_path = Path(template_path)
    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=select_autoescape(("html", "htm", "xml", "j2")),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env, template_path.name


def _format_currency(value: Any) -> str:
    coerced = _coerce_float(value)
    if coerced is None:
        return "-"
    return f"${coerced:,.2f}"


def _format_number(value: Any, decimals: int = 2) -> str:
    coerced = _coerce_float(value)
    if coerced is None:
        return "-"
    return f"{coerced:,.{decimals}f}"


def _format_percent(value: Any, decimals: int = 1) -> str:
    coerced = _coerce_float(value)
    if coerced is None:
        return "-"
    return f"{coerced * 100:.{decimals}f}%"


def _format_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%SZ")
    if isinstance(value, date):
        return value.isoformat()
    return str(value) if value is not None else "-"


def render_report_html(
    context: dict[str, Any],
    template_path: str | Path | None = None,
) -> str:
    """Render the Jinja2 template with the supplied context."""
    env, template_name = _build_environment(template_path)
    env.filters["currency"] = _format_currency
    env.filters["number"] = _format_number
    env.filters["percent"] = _format_percent
    env.filters["isodate"] = _format_date
    template = env.get_template(template_name)
    return template.render(**context)


def write_report_html(html: str, output_path: str | Path) -> Path:
    """Write the rendered HTML to disk (UTF-8, parents created)."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path.resolve()


def export_portfolio_report(
    db: Session,
    request: ReportExportRequest,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Assemble + render + write the report; return response dict."""
    report_id = build_report_id(
        request.as_of_date,
        request.simulation_id,
        request.model_name,
        request.model_version,
    )
    output_path = resolve_report_output_path(
        request.output_filename, report_id, output_dir=output_dir
    )

    context = assemble_report_context(db, request)
    html = render_report_html(context)
    final_path = write_report_html(html, output_path)
    file_size = final_path.stat().st_size

    relative = _relative_path(final_path)

    return {
        "report_id": report_id,
        "report_title": request.report_title,
        "as_of_date": request.as_of_date,
        "simulation_id": request.simulation_id,
        "model_name": request.model_name,
        "model_version": request.model_version,
        "feature_version": request.feature_version,
        "output_path": str(final_path),
        "relative_output_path": relative,
        "file_size_bytes": int(file_size),
        "created_at": context["generated_at"],
        "sections": context["sections"],
        "warnings": context["warnings"],
    }


def _relative_path(path: Path) -> str:
    """Best-effort cwd-relative representation of ``path``."""
    try:
        return str(path.relative_to(Path.cwd().resolve()))
    except ValueError:
        return path.name


__all__ = [
    "assemble_report_context",
    "build_report_id",
    "export_portfolio_report",
    "fetch_report_model_metadata",
    "fetch_report_portfolio_summary",
    "fetch_report_risk_by_industry",
    "fetch_report_risk_by_lga",
    "fetch_report_top_payout_assets",
    "fetch_report_top_risk_assets",
    "render_report_html",
    "resolve_report_output_path",
    "write_report_html",
]
