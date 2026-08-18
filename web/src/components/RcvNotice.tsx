"use client";

import { OrderingEditor } from "./OrderingEditor";
import type { Personas, SimResult } from "@/sim/types";

/**
 * 優先順位付投票を選んでいるあいだ、画面上部に出しっぱなしにする警告。
 *
 * この試算だけは、実際の投票結果から機械的に計算したものではない。有権者の順位付け
 * データが存在しないため、調査から作った仮想のペルソナで代用している。他の案の試算と
 * 同じ重みで読まれないよう、見た目からはっきり分ける。
 */
export function RcvNotice({
  smd,
  personas,
  districtCount,
  voteScale,
  orderOverrides,
  onChangeOrder,
  onResetOrders,
}: {
  smd: SimResult["smd"];
  personas: Personas | null;
  districtCount: number;
  voteScale: number;
  orderOverrides: Record<string, string[]>;
  onChangeOrder: (party: string, order: string[]) => void;
  onResetOrders: () => void;
}) {
  const moved = smd.flipped.length;
  const secured = smd.securedOnFirstPreferences;
  // 有効投票の1%を境に、結果を歪めるほどの規模かどうかで分ける
  const major = smd.unorderedParties.filter((p) => p.share >= 1);
  const minor = smd.unorderedParties.filter((p) => p.share < 1);

  return (
    <section
      className="rounded-xl p-4"
      style={{
        border: "2px solid var(--warning)",
        background: "color-mix(in srgb, var(--warning) 8%, var(--surface))",
      }}
    >
      <h2 className="text-[15px] font-bold">⚠ これは仮想のペルソナが生む数字です</h2>
      <p className="mt-2 max-w-3xl text-[13px] leading-relaxed">
        有権者が候補者にどう順位をつけたかのデータは<strong>存在しません</strong>。
        投票用紙に残るのは第1希望だけで、第2希望以降はどこにも記録されていません。
        ここでは「どの政党を拒否しているか」を尋ねた調査から作った
        <strong>仮想の選好順序</strong>で代用しています。
        <strong>実際の投票結果ではなく、予測でもありません。</strong>
        ペルソナの置き方を変えれば数字は変わります。
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <div className="rounded-lg px-3 py-2" style={{ background: "var(--surface)" }}>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            仮定によらず確定
          </div>
          <div className="tnum text-[20px] font-semibold">{secured}</div>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            第1選好で過半数。移譲がどう転んでも動かない
          </div>
        </div>
        <div className="rounded-lg px-3 py-2" style={{ background: "var(--surface)" }}>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            移譲次第で動きうる
          </div>
          <div className="tnum text-[20px] font-semibold">{districtCount - secured}</div>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            この範囲だけが仮定の影響を受ける
          </div>
        </div>
        <div className="rounded-lg px-3 py-2" style={{ background: "var(--surface)" }}>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            実際に動いた
          </div>
          <div className="tnum text-[20px] font-semibold" style={{ color: "var(--warning)" }}>
            {moved}
          </div>
          <div className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            全{districtCount}選挙区の {((moved / districtCount) * 100).toFixed(1)}%
          </div>
        </div>
      </div>

      {/*
        順序を持たない党が諸派だけなら影響は小さいが、調査に無い大政党（第47回の民主党、
        第48回の希望の党など）が含まれると結果が大きく歪む。得票規模で扱いを分ける。
      */}
      {major.length > 0 && (
        <div
          className="mt-3 rounded-lg px-3 py-2"
          style={{ border: "1px solid var(--critical)", background: "var(--surface)" }}
        >
          <div className="text-[13px] font-semibold" style={{ color: "var(--critical)" }}>
            この選挙回には、選好順序を持たない大きな政党があります
          </div>
          <p className="mt-1 max-w-3xl text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            元にした調査は第51回（2026年）の政党構成で行われているため、それ以前の回に出てくる
            政党の一部は順序を持ちません。該当する党の票は移譲されずに死票となり、他党からも票が
            回ってきません。<strong>下記の得票が大きいほど、この回の試算は歪んでいます。</strong>
          </p>
          <ul className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
            {major.map((p) => (
              <li key={p.party} className="tnum" style={{ color: "var(--ink-2)" }}>
                {p.party}{" "}
                <span style={{ color: "var(--critical)" }}>
                  {Math.round(p.votes / voteScale).toLocaleString("ja-JP")}票（
                  {p.share.toFixed(1)}%）
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {minor.length > 0 && (
        <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
          選好順序を持たない諸派: {minor.map((p) => p.party).join("・")}
          （合計 {Math.round(minor.reduce((a, b) => a + b.votes, 0) / voteScale).toLocaleString("ja-JP")}票）。
          落選時に票が移譲されず死票になります。
        </p>
      )}

      {smd.exhausted > 0 && (
        <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
          移譲先が定義できず死票になった票:{" "}
          <span className="tnum">
            {Math.round(smd.exhausted / voteScale).toLocaleString("ja-JP")}
          </span>
          （選好順序を持たない諸派の候補が落ちたとき）
        </p>
      )}

      {personas && (
        <details className="mt-3">
          <summary className="text-[12px] font-medium">
            使っている選好順序をすべて見る（{Object.keys(personas.orderings).length}政党）
          </summary>
          <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
            {personas.method}
          </p>
          <p className="mt-1 text-[11px]" style={{ color: "var(--ink-muted)" }}>
            出典: {personas.source}
          </p>
          <div className="mt-3">
            <OrderingEditor
              personas={personas}
              overrides={orderOverrides}
              onChange={onChangeOrder}
              onReset={onResetOrders}
            />
          </div>
          <div className="mt-3">
            <div className="text-[12px] font-medium">想定で置いた政党</div>
            <ul className="mt-1 space-y-0.5 text-[11px]" style={{ color: "var(--ink-2)" }}>
              {Object.entries(personas.derived).map(([party, why]) => (
                <li key={party}>
                  <span style={{ color: "var(--warning)" }}>{party}</span>: {why}
                </li>
              ))}
            </ul>
          </div>
          <ul className="mt-3 space-y-1 text-[11px]" style={{ color: "var(--ink-2)" }}>
            {personas.caveats.map((c) => (
              <li key={c}>※ {c}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
