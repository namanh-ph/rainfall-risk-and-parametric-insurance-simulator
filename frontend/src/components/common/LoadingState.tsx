interface Props {
  label?: string;
  className?: string;
}

export function LoadingState({ label = "Loading…", className }: Props): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-centre gap-3 rounded-md border border-slate-200 bg-white p-4 text-sm text-slate-600 ${className ?? ""}`}
    >
      <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-slate-400" />
      <span>{label}</span>
    </div>
  );
}
