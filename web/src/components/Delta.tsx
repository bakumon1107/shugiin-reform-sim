/**
 * 増減の表示。色は向き（青＝増／赤＝減）だけを表し、必ず符号を添える。
 * 色覚特性にかかわらず符号で読めるようにするため、色だけで意味を運ばせない。
 */
export function Delta({ value, className = "" }: { value: number; className?: string }) {
  if (value === 0) {
    return (
      <span className={`tnum text-[13px] ${className}`} style={{ color: "var(--ink-muted)" }}>
        ±0
      </span>
    );
  }
  const color = value > 0 ? "var(--gain)" : "var(--loss)";
  return (
    <span className={`tnum text-[13px] font-semibold ${className}`} style={{ color }}>
      {value > 0 ? "+" : "−"}
      {Math.abs(value)}
    </span>
  );
}

/**
 * 一覧の中で使う増減チップ。
 *
 * 「減税日本・ゆうこく連合」のように長い党派名があるので、狭い画面ではチップ自体が
 * 折り返せるようにしておく（折り返さないと親からはみ出してページ全体が横に伸びる）。
 */
export function DeltaChip({ label, value }: { label: string; value: number }) {
  const color = value > 0 ? "var(--gain)" : "var(--loss)";
  return (
    <span
      className="inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px]"
      style={{ background: "var(--neutral)", color: "var(--ink-2)" }}
    >
      <span className="min-w-0 break-all">{label}</span>
      <span className="tnum shrink-0 font-semibold" style={{ color }}>
        {value > 0 ? "+" : "−"}
        {Math.abs(value)}
      </span>
    </span>
  );
}
