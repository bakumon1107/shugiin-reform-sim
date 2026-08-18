"use client";

import { divisorScale, isEligible, sekihaiRate } from "@/sim/engine";
import type { Block, BlockResult, ElectionData, SimParams, SimResult } from "@/sim/types";
import { Delta } from "./Delta";

function fmtVotes(scaled: number, scale: number): string {
  return (scaled / scale).toLocaleString("ja-JP", { maximumFractionDigits: 3 });
}

/** 1ブロックの内訳。除数表・名簿枯渇・比例当選者の入れ替わりを出す。 */
function BlockRow({
  block,
  base,
  prop,
  params,
  scale,
}: {
  block: Block;
  base: BlockResult;
  prop: BlockResult;
  params: SimParams;
  scale: number;
}) {
  const parties = [...block.parties].sort((a, b) => b.votes - a.votes);

  const baseWinners = new Set(Object.values(base.winners).flat());
  const propWinners = new Set(Object.values(prop.winners).flat());
  const lost = [...baseWinners].filter((n) => !propWinners.has(n));
  const gained = [...propWinners].filter((n) => !baseWinners.has(n));

  const nameToParty = new Map<string, string>();
  for (const p of block.parties) for (const e of p.list) nameToParty.set(e.name, p.party);

  return (
    <details className="card px-4 py-3">
      <summary className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px]">
        <span className="font-semibold">{block.block}</span>
        <span className="tnum" style={{ color: "var(--ink-2)" }}>
          定数 {base.seats}
          {prop.seats !== base.seats && (
            <>
              {" → "}
              <span className="font-semibold" style={{ color: "var(--ink)" }}>
                {prop.seats}
              </span>
            </>
          )}
        </span>
        {prop.vacancies > 0 && (
          <span className="tnum font-semibold" style={{ color: "var(--critical)" }}>
            欠員 {prop.vacancies}
          </span>
        )}
        {(lost.length > 0 || gained.length > 0) && (
          <span className="tnum" style={{ color: "var(--ink-muted)" }}>
            当選者 {lost.length} 人入れ替わり
          </span>
        )}
      </summary>

      <div className="mt-3 scroll-x">
        <table className="w-full min-w-[620px] border-collapse text-[12px]">
          <thead>
            <tr style={{ color: "var(--ink-muted)" }} className="text-left">
              <th className="py-1.5 pr-3 font-medium">党派</th>
              <th className="py-1.5 pr-3 text-right font-medium">得票</th>
              <th className="py-1.5 pr-3 text-right font-medium">現行</th>
              <th className="py-1.5 pr-3 text-right font-medium">案</th>
              <th className="py-1.5 pr-3 text-right font-medium">増減</th>
              <th className="py-1.5 pr-3 text-right font-medium">当選可能な名簿</th>
              <th className="py-1.5 font-medium">備考</th>
            </tr>
          </thead>
          <tbody>
            {parties.map((p) => {
              const b = base.seatsByParty[p.party] ?? 0;
              const n = prop.seatsByParty[p.party] ?? 0;
              const cap = prop.capacity[p.party] ?? 0;
              const wanted = prop.order.filter((s) => s.party === p.party).length;
              const short = wanted - n;
              return (
                <tr key={p.party} style={{ borderTop: "1px solid var(--grid)" }}>
                  <td className="py-1.5 pr-3">{p.party}</td>
                  <td className="tnum py-1.5 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                    {fmtVotes(p.votes, scale)}
                  </td>
                  <td className="tnum py-1.5 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                    {b}
                  </td>
                  <td className="tnum py-1.5 pr-3 text-right font-semibold">{n}</td>
                  <td className="py-1.5 pr-3 text-right">
                    <Delta value={n - b} />
                  </td>
                  <td className="tnum py-1.5 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                    {cap} / {p.list.length}
                  </td>
                  <td className="py-1.5" style={{ color: "var(--ink-muted)" }}>
                    {short > 0 && (
                      <span style={{ color: "var(--critical)" }}>
                        名簿不足で {short} 議席が欠員
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {(lost.length > 0 || gained.length > 0) && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <div className="text-[12px] font-medium" style={{ color: "var(--loss)" }}>
              現行では比例当選、案では落選（{lost.length}人）
            </div>
            <ul className="mt-1 space-y-0.5 text-[12px]" style={{ color: "var(--ink-2)" }}>
              {lost.map((n) => (
                <li key={n}>
                  {n} <span style={{ color: "var(--ink-muted)" }}>／ {nameToParty.get(n)}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <div className="text-[12px] font-medium" style={{ color: "var(--gain)" }}>
              案では新たに比例当選（{gained.length}人）
            </div>
            <ul className="mt-1 space-y-0.5 text-[12px]" style={{ color: "var(--ink-2)" }}>
              {gained.map((n) => (
                <li key={n}>
                  {n} <span style={{ color: "var(--ink-muted)" }}>／ {nameToParty.get(n)}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      <details className="mt-3">
        <summary className="text-[12px]" style={{ color: "var(--ink-2)" }}>
          議席の獲得順（除数表）を見る
        </summary>
        <div className="mt-2 scroll-x">
          <table className="w-full min-w-[420px] border-collapse text-[12px]">
            <thead>
              <tr style={{ color: "var(--ink-muted)" }} className="text-left">
                <th className="py-1 pr-3 font-medium">順</th>
                <th className="py-1 pr-3 font-medium">党派</th>
                <th className="py-1 pr-3 text-right font-medium">除数</th>
                <th className="py-1 pr-3 text-right font-medium">商</th>
                <th className="py-1 font-medium">結果</th>
              </tr>
            </thead>
            <tbody>
              {prop.order.map((s, i) => {
                const votes = block.parties.find((p) => p.party === s.party)!.votes;
                // 修正サンラグの除数は10倍した整数で持っているので、表示前に戻す
                const dScale = divisorScale(params.divisorMethod);
                const shown = s.divisor / dScale;
                return (
                  <tr key={i} style={{ borderTop: "1px solid var(--grid)" }}>
                    <td className="tnum py-1 pr-3">{i + 1}</td>
                    <td className="py-1 pr-3">{s.party}</td>
                    <td className="tnum py-1 pr-3 text-right">
                      {Number.isInteger(shown) ? shown : shown.toFixed(1)}
                    </td>
                    <td className="tnum py-1 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                      {fmtVotes(Math.round((votes * dScale) / s.divisor), scale)}
                    </td>
                    <td className="py-1">
                      {s.filled ? (
                        <span style={{ color: "var(--ink-muted)" }}>当選</span>
                      ) : (
                        <span style={{ color: "var(--critical)" }}>欠員（名簿不足）</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </details>

      <details className="mt-2">
        <summary className="text-[12px]" style={{ color: "var(--ink-2)" }}>
          比例名簿と復活の資格を見る
        </summary>
        <div className="mt-2 scroll-x">
          <table className="w-full min-w-[640px] border-collapse text-[12px]">
            <thead>
              <tr style={{ color: "var(--ink-muted)" }} className="text-left">
                <th className="py-1 pr-3 font-medium">党派</th>
                <th className="py-1 pr-3 text-right font-medium">順位</th>
                <th className="py-1 pr-3 font-medium">氏名</th>
                <th className="py-1 pr-3 font-medium">小選挙区</th>
                <th className="py-1 pr-3 text-right font-medium">得票率</th>
                <th className="py-1 pr-3 text-right font-medium">惜敗率</th>
                <th className="py-1 font-medium">案での資格</th>
              </tr>
            </thead>
            <tbody>
              {parties.flatMap((p) =>
                p.list.map((e) => {
                  const ok = isEligible(e, params);
                  const rate = sekihaiRate(e);
                  const share =
                    e.smdVotes && e.districtValidVotes
                      ? (e.smdVotes / e.districtValidVotes) * 100
                      : null;
                  return (
                    <tr key={`${p.party}-${e.rank}-${e.name}`} style={{ borderTop: "1px solid var(--grid)" }}>
                      <td className="py-1 pr-3" style={{ color: "var(--ink-muted)" }}>
                        {p.party}
                      </td>
                      <td className="tnum py-1 pr-3 text-right">{e.rank}</td>
                      <td className="py-1 pr-3">{e.name}</td>
                      <td className="py-1 pr-3" style={{ color: "var(--ink-2)" }}>
                        {e.dual ? `${e.districtId}${e.smdWon ? "・当選" : "・落選"}` : "単独"}
                      </td>
                      <td className="tnum py-1 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {share === null ? "—" : `${share.toFixed(1)}%`}
                      </td>
                      <td className="tnum py-1 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {rate === null ? "—" : `${rate.toFixed(1)}%`}
                      </td>
                      <td className="py-1">
                        {e.smdWon ? (
                          <span style={{ color: "var(--ink-muted)" }}>小選挙区で当選</span>
                        ) : ok ? (
                          <span style={{ color: "var(--gain)" }}>復活できる</span>
                        ) : (
                          <span style={{ color: "var(--loss)" }}>資格なし</span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </details>
    </details>
  );
}

export function BlockDetail({
  data,
  baseline,
  proposal,
  params,
}: {
  data: ElectionData;
  baseline: SimResult;
  proposal: SimResult;
  params: SimParams;
}) {
  return (
    <div className="space-y-2">
      {data.blocks.map((block) => (
        <BlockRow
          key={block.block}
          block={block}
          base={baseline.blocks.find((b) => b.block === block.block)!}
          prop={proposal.blocks.find((b) => b.block === block.block)!}
          params={params}
          scale={data.voteScale}
        />
      ))}
    </div>
  );
}
