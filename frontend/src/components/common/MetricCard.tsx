import clsx from "clsx";

interface Props {
  title: string;
  value: string;
  hint?: string;
  accent?: "brand" | "amber" | "green" | "red" | "slate";
  className?: string;
}

const ACCENTS: Record<NonNullable<Props["accent"]>, string> = {
  brand: "text-brand",
  amber: "text-amber-600",
  green: "text-green-700",
  red: "text-red-700",
  slate: "text-slate-700",
};

export function MetricCard({ title, value, hint, accent = "brand", className }: Props): JSX.Element {
  return (
    <div
      className={clsx(
        "rounded-lg border border-slate-200 bg-white p-4 shadow-sm",
        className,
      )}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <p className={clsx("mt-2 text-2xl font-semibold", ACCENTS[accent])}>{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
    </div>
  );
}
