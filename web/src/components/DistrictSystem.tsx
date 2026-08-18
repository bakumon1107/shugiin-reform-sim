"use client";

import type { SmdVoting } from "@/sim/types";

/**
 * 選挙区制度の選択。
 *
 * 比例代表の設定（配分方式・定数・比例復活）とは別の軸なので、タブを分けている。
 * どちらも独立に効くので、「自民党案の比例 × 優先順位付投票」のような組み合わせも
 * そのまま選べる。
 */
type Option = {
  value: SmdVoting | "chusenkyoku";
  label: string;
  hint: string;
  /** 使えない理由。あるものは選べない。 */
  blocked?: string;
  /** 仮想ペルソナに依存するか */
  assumed?: boolean;
};

const OPTIONS: Option[] = [
  {
    value: "plurality",
    label: "小選挙区",
    hint: "現行。1人1票で最多得票者が当選する",
  },
  {
    value: "rcv",
    label: "RCV",
    hint: "優先順位付投票。候補者に順位をつけ、過半数が出るまで下位から票を移す",
    assumed: true,
  },
  {
    value: "chusenkyoku",
    label: "中選挙区連記制",
    hint: "3人区140で1人2票（国民民主党案）",
    blocked:
      "候補者の擁立が制度そのものに左右されるため、試算しても制度の評価になりません。" +
      "この案は比例代表を廃して420議席すべてを選挙区から選ぶものですが、いまの候補者名簿は" +
      "比例代表があることを前提に組まれています。第51回のチームみらいは比例で381万票を得た" +
      "一方、小選挙区には289区中6区にしか候補を立てていません（得票15万票）。比例を廃せば" +
      "各党は当然もっと多くの選挙区に候補を立てますが、どれだけ立てるかは政党の判断であって" +
      "データのどこにも書かれていません。現在の名簿をそのまま流し込めば「チームみらい11議席→0議席」" +
      "といった数字は出ますが、それは制度の効果ではなく前提のずれが生む数字です。",
  },
];

export function DistrictSystem({
  value,
  onChange,
}: {
  value: SmdVoting;
  onChange: (v: SmdVoting) => void;
}) {
  return (
    <div>
      <div id="district-system-label" className="mb-1 text-[12px]" style={{ color: "var(--ink-muted)" }}>
        選挙区制度
      </div>
      <div
        role="group"
        aria-labelledby="district-system-label"
        className="flex flex-wrap gap-2"
      >
        {OPTIONS.map((o) => {
          const active = !o.blocked && o.value === value;
          return (
            <button
              key={o.value}
              type="button"
              disabled={Boolean(o.blocked)}
              onClick={() => !o.blocked && onChange(o.value as SmdVoting)}
              aria-pressed={active}
              title={o.blocked ?? o.hint}
              className="rounded-lg px-3 py-2 text-left text-[13px] disabled:cursor-not-allowed"
              style={{
                border: `1px solid ${active ? "var(--bar-450)" : "var(--hairline)"}`,
                background: active ? "var(--bar-450)" : "var(--surface)",
                color: active ? "#ffffff" : o.blocked ? "var(--ink-muted)" : "var(--ink-2)",
                opacity: o.blocked ? 0.55 : 1,
              }}
            >
              {o.label}
              {o.assumed && (
                <span
                  className="ml-1.5 text-[11px]"
                  style={{ color: active ? "#ffffff" : "var(--warning)" }}
                >
                  ※仮定
                </span>
              )}
              {o.blocked && (
                <span className="ml-1.5 text-[11px]">試算不能</span>
              )}
            </button>
          );
        })}
      </div>
      <p className="mt-1.5 max-w-3xl text-[11px]" style={{ color: "var(--ink-muted)" }}>
        {OPTIONS.find((o) => o.value === value)?.hint}
        　比例代表の設定とは独立に効くので、どの案とも組み合わせられます。
      </p>
      {OPTIONS.filter((o) => o.blocked).map((o) => (
        <details key={o.value} className="mt-1">
          <summary className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            {o.label} を試算できない理由
          </summary>
          <p
            className="mt-1 max-w-3xl text-[11px] leading-relaxed"
            style={{ color: "var(--ink-2)" }}
          >
            {o.blocked}
          </p>
        </details>
      ))}
    </div>
  );
}
