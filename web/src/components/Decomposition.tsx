"use client";

import type { Step } from "@/lib/decompose";
import { DeltaChip } from "./Delta";

/**
 * 現行制度から案へ、変更を1つずつ積み上げて見せる。
 *
 * 自民案のように5つの要素が同時に効く案は、最終結果だけを見ても何が効いたのかが
 * 読めない。要素は互いに独立ではないので、適用の順番を変えれば各段の内訳も変わる。
 * その断りを画面にも出しておく。
 */
export function Decomposition({
  steps,
  baselineSeats,
}: {
  steps: Step[];
  /** 現行制度での党派別議席。純増減を出すために使う。 */
  baselineSeats: Record<string, number>;
}) {
  if (steps.length === 0) {
    return (
      <p className="text-[13px]" style={{ color: "var(--ink-muted)" }}>
        現行制度と同じパラメータなので、変化はありません。
      </p>
    );
  }

  // 現行制度からの純増減。ある段で増えた議席が後の段で消えることがあるので
  // （例: サンラグ式で得た議席が、比例定数の削減で消える）、各段の増減を足し
  // 合わせた結果をここで突き合わせられるようにする。
  const final = steps[steps.length - 1].seats;
  const net = [...new Set([...Object.keys(baselineSeats), ...Object.keys(final)])]
    .map((party) => [party, (final[party] ?? 0) - (baselineSeats[party] ?? 0)] as const)
    .filter(([, d]) => d !== 0)
    .sort((a, b) => b[1] - a[1]);

  // 途中の段で動いたのに、最終的には元に戻る党派
  const movedThenReverted = [
    ...new Set(steps.flatMap((s) => Object.keys(s.deltas))),
  ].filter((party) => (final[party] ?? 0) === (baselineSeats[party] ?? 0));

  return (
    <div>
      <ol className="space-y-0">
        {steps.map((step, i) => {
          const moved = Object.entries(step.deltas).sort((a, b) => b[1] - a[1]);
          return (
            <li
              key={step.id}
              className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 py-3"
              style={{ borderTop: i === 0 ? "none" : "1px solid var(--grid)" }}
            >
              <div
                className="tnum mt-0.5 flex h-6 w-6 items-center justify-center rounded-full text-[12px] font-semibold"
                style={{ background: "var(--neutral)", color: "var(--ink-2)" }}
              >
                {i + 1}
              </div>
              {/* グリッドの子は min-width:auto が既定なので、長い党派名で列がはみ出す。
                  minmax(0,1fr) と合わせて明示的に縮められるようにしておく。 */}
              <div className="min-w-0">
                <div className="text-[13px] font-medium">{step.label}</div>
                <div className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
                  {step.change}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {moved.length === 0 ? (
                    <span className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
                      この変更では議席は動かない
                    </span>
                  ) : (
                    moved.map(([party, d]) => (
                      <DeltaChip key={party} label={party} value={d} />
                    ))
                  )}
                  {step.vacancies > 0 && (
                    <span
                      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px]"
                      style={{ background: "var(--neutral)", color: "var(--ink-2)" }}
                    >
                      欠員
                      <span className="tnum font-semibold" style={{ color: "var(--critical)" }}>
                        {step.vacancies}
                      </span>
                    </span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ol>

      {/* --- 純増減 --- */}
      <div
        className="grid grid-cols-[28px_minmax(0,1fr)] gap-x-3 py-3"
        style={{ borderTop: "2px solid var(--axis)" }}
      >
        <div
          className="mt-0.5 flex h-6 w-6 items-center justify-center rounded-full text-[13px] font-semibold"
          style={{ background: "var(--neutral)", color: "var(--ink-2)" }}
        >
          =
        </div>
        <div className="min-w-0">
          <div className="text-[13px] font-medium">現行制度からの純増減</div>
          <div className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
            上の表の「増減」列と一致します
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {net.length === 0 ? (
              <span className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
                差し引きでは議席は動かない
              </span>
            ) : (
              net.map(([party, d]) => <DeltaChip key={party} label={party} value={d} />)
            )}
          </div>

          {movedThenReverted.length > 0 && (
            <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
              {movedThenReverted.join("・")}は途中の段で議席が動きますが、後の段で打ち消され、
              差し引きでは元に戻ります。
            </p>
          )}
        </div>
      </div>

      <p className="mt-1 text-[11px]" style={{ color: "var(--ink-muted)" }}>
        各要素は互いに独立ではないため、適用する順番を変えると各段の内訳も変わります。
        ここでは「配分方式 → 定数 → 得票率要件 → 惜敗率下限 → 名簿枯渇」の順に固定しています。
        差し引きの結果は順番によらず同じです。
      </p>
    </div>
  );
}
