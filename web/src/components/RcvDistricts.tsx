"use client";

import { useState } from "react";

import type { DistrictRcv } from "@/sim/types";

/**
 * 選挙区ごとに、優先順位付投票の途中経過を開いて見せる。
 *
 * どの候補がどの回で落ち、その票がどこへ流れて結果が変わったのかを、順を追って
 * 確かめられるようにする。数字が仮定に依存する以上、結論だけでなく過程が見えて
 * いないと読み手が判断できない。
 */
function fmt(scaled: number, scale: number): string {
  return Math.round(scaled / scale).toLocaleString("ja-JP");
}

function DistrictRow({ d, scale }: { d: DistrictRcv; scale: number }) {
  const flipped = d.winner !== d.pluralityWinner;
  return (
    <details className="card px-3 py-2">
      <summary className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px]">
        <span className="font-semibold">{d.district}</span>
        {d.secured ? (
          <span style={{ color: "var(--ink-muted)" }}>第1選好で過半数・確定</span>
        ) : (
          <span className="tnum" style={{ color: "var(--ink-muted)" }}>
            {d.log.length}回
          </span>
        )}
        {flipped ? (
          <span>
            <span style={{ color: "var(--loss)" }}>{d.pluralityWinnerParty}</span>
            <span style={{ color: "var(--ink-muted)" }}> → </span>
            <span className="font-semibold" style={{ color: "var(--gain)" }}>
              {d.winnerParty}
            </span>
          </span>
        ) : (
          <span style={{ color: "var(--ink-2)" }}>{d.winnerParty}（変わらず）</span>
        )}
      </summary>

      <div className="mt-2 space-y-2">
        {d.log.map((round, i) => (
          <div key={i}>
            <div className="text-[11px] font-medium" style={{ color: "var(--ink-muted)" }}>
              第{i + 1}回
              {round.eliminated ? (
                <>
                  {" — "}
                  <span style={{ color: "var(--loss)" }}>
                    {round.eliminated.name}（{round.eliminated.party}）
                  </span>
                  を落として {fmt(round.eliminated.votes, scale)} 票を
                  {round.movedTo ? (
                    <span style={{ color: "var(--gain)" }}> {round.movedTo} へ移譲</span>
                  ) : (
                    <span style={{ color: "var(--critical)" }}> 死票に（移譲先なし）</span>
                  )}
                </>
              ) : (
                " — 過半数に達し当選確定"
              )}
            </div>
            <div className="mt-1 space-y-0.5">
              {round.standing.map((c) => (
                <div key={c.name} className="flex items-center gap-2 text-[11px]">
                  <span className="w-28 shrink-0 truncate" title={`${c.name}（${c.party}）`}>
                    {c.name}
                  </span>
                  <span
                    className="w-24 shrink-0 truncate"
                    style={{ color: "var(--ink-muted)" }}
                  >
                    {c.party}
                  </span>
                  <span className="relative h-3 flex-1" style={{ minWidth: 60 }}>
                    <span
                      className="absolute inset-y-0 left-0"
                      style={{
                        width: `${Math.min(c.share, 100)}%`,
                        background:
                          round.eliminated?.name === c.name
                            ? "var(--loss)"
                            : "var(--bar-450)",
                        borderRadius: "0 2px 2px 0",
                      }}
                    />
                    {/* 過半数の線 */}
                    <span
                      className="absolute inset-y-0 w-px"
                      style={{ left: "50%", background: "var(--ink)", opacity: 0.4 }}
                    />
                  </span>
                  <span className="tnum w-14 shrink-0 text-right" style={{ color: "var(--ink-2)" }}>
                    {fmt(c.votes, scale)}
                  </span>
                  <span className="tnum w-12 shrink-0 text-right">{c.share.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </details>
  );
}

export function RcvDistricts({
  districts,
  voteScale,
}: {
  districts: DistrictRcv[];
  voteScale: number;
}) {
  const [filter, setFilter] = useState<"flipped" | "contested" | "all">("flipped");
  const [query, setQuery] = useState("");

  const shown = districts
    .filter((d) => {
      if (filter === "flipped") return d.winner !== d.pluralityWinner;
      if (filter === "contested") return !d.secured;
      return true;
    })
    .filter((d) => (query ? d.district.includes(query) : true));

  const flippedCount = districts.filter((d) => d.winner !== d.pluralityWinner).length;
  const contestedCount = districts.filter((d) => !d.secured).length;

  return (
    <section>
      <h2 className="mb-1 text-[15px] font-semibold">選挙区ごとの途中経過</h2>
      <p className="mb-3 text-[12px]" style={{ color: "var(--ink-muted)" }}>
        どの候補が何回目で落ち、その票がどこへ流れたか。棒の中央の縦線が過半数です。
      </p>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div
          className="inline-flex overflow-hidden rounded-lg"
          style={{ border: "1px solid var(--hairline)" }}
        >
          {(
            [
              ["flipped", `入れ替わった（${flippedCount}）`],
              ["contested", `移譲で動きうる（${contestedCount}）`],
              ["all", `全て（${districts.length}）`],
            ] as const
          ).map(([v, label]) => (
            <button
              key={v}
              type="button"
              onClick={() => setFilter(v)}
              aria-pressed={filter === v}
              className="px-3 py-1.5 text-[12px] whitespace-nowrap"
              style={{
                background: filter === v ? "var(--bar-450)" : "transparent",
                color: filter === v ? "#ffffff" : "var(--ink-2)",
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="選挙区で絞り込み（例: 東京都11）"
          aria-label="選挙区で絞り込み"
          className="rounded-lg px-3 py-1.5 text-[12px]"
          style={{
            border: "1px solid var(--hairline)",
            background: "var(--surface)",
            color: "var(--ink)",
          }}
        />
      </div>

      {shown.length === 0 ? (
        <p className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
          該当する選挙区がありません。
        </p>
      ) : (
        <div className="space-y-1.5">
          {shown.map((d) => (
            <DistrictRow key={d.district} d={d} scale={voteScale} />
          ))}
        </div>
      )}
    </section>
  );
}
