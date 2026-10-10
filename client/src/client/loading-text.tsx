export function LoadingText({ text, active = true }: { text: string; active?: boolean }) {
  return <span className={`loading-text ${active ? "is-loading" : ""}`} data-loading-text>
    <span data-loading-base>{text}</span>
    {active && <span className="loading-text-glow" aria-hidden="true">{text}</span>}
  </span>;
}
