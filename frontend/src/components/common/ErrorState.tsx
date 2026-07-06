import { ApiError } from "../../api/client";

interface Props {
  error: unknown;
  title?: string;
  className?: string;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return `${error.message} (status ${error.status})`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return String(error);
}

export function ErrorState({ error, title = "Something went wrong", className }: Props): JSX.Element {
  return (
    <div
      role="alert"
      className={`rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-800 ${className ?? ""}`}
    >
      <p className="font-semibold">{title}</p>
      <p className="mt-1 text-red-700">{describe(error)}</p>
    </div>
  );
}
