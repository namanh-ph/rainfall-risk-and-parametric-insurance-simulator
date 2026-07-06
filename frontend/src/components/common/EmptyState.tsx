interface Props {
  title?: string;
  message?: string;
  className?: string;
}

export function EmptyState({
  title = "No data",
  message = "There is nothing to display for the current filters.",
  className,
}: Props): JSX.Element {
  return (
    <div
      className={`rounded-md border border-dashed border-slate-300 bg-slate-50 p-6 text-centre text-sm text-slate-600 ${className ?? ""}`}
    >
      <p className="font-semibold text-slate-700">{title}</p>
      <p className="mt-1">{message}</p>
    </div>
  );
}
