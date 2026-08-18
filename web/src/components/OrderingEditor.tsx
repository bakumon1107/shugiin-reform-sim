"use client";

import { useState } from "react";

import type { Personas } from "@/sim/types";

/**
 * 選好順序を読み手が自分で組み替えられるようにする。
 *
 * 優先順位付投票の議席数は、こちらが置いたペルソナの並べ方で変わる。数字が仮定に
 * 依存する以上、その仮定を隠して1つの答えを出すより、読み手に握らせて動かして
 * もらうほうが正直だと考えている。並べ替えると議席がその場で計算し直される。
 *
 * 操作はドラッグで直接動かせるようにしつつ、キーボードとタッチのために上下ボタンも
 * 残している。ドラッグだけだとキーボードで操作できず、ボタンだけだと遠くへ動かすのに
 * 何度も押すことになる。
 */
export function OrderingEditor({
  personas,
  overrides,
  onChange,
  onReset,
}: {
  personas: Personas;
  /** 読み手が組み替えた順序。政党名 → 並び */
  overrides: Record<string, string[]>;
  onChange: (party: string, order: string[]) => void;
  onReset: () => void;
}) {
  const [dragging, setDragging] = useState<{ party: string; from: number } | null>(null);
  const [over, setOver] = useState<number | null>(null);
  const edited = Object.keys(overrides);

  const orderOf = (party: string) => overrides[party] ?? personas.orderings[party];

  const move = (party: string, from: number, to: number) => {
    const order = [...orderOf(party)];
    // 先頭（自党）は動かさないし、その手前にも置かせない
    if (from < 1 || to < 1 || to >= order.length || from === to) return;
    const [x] = order.splice(from, 1);
    order.splice(to, 0, x);
    onChange(party, order);
  };

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="max-w-2xl text-[12px]" style={{ color: "var(--ink-2)" }}>
          ドラッグするか、選んで <kbd>↑</kbd> <kbd>↓</kbd> で動かせます。並べ替えると議席が
          その場で計算し直されるので、数字がどれだけこの並びに依存しているか確かめられます。
          先頭（自党）は動きません。
        </p>
        {edited.length > 0 && (
          <button
            type="button"
            onClick={onReset}
            className="rounded-lg px-3 py-1.5 text-[12px]"
            style={{ border: "1px solid var(--hairline)", color: "var(--ink-2)" }}
          >
            既定の順序に戻す（{edited.length}件を編集中）
          </button>
        )}
      </div>

      <div className="mt-3 space-y-3">
        {Object.keys(personas.orderings).map((party) => {
          const order = orderOf(party);
          const isEdited = party in overrides;
          return (
            <div key={party} className="card p-3">
              <div className="mb-2 flex flex-wrap items-baseline gap-2 text-[13px]">
                <span className="font-semibold">{party}</span>
                <span className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
                  に投じた人の選好順序
                </span>
                {party in personas.derived && (
                  <span className="text-[11px]" style={{ color: "var(--warning)" }}>
                    ※調査に無いため想定
                  </span>
                )}
                {isEdited && (
                  <span className="text-[11px]" style={{ color: "var(--gain)" }}>
                    編集済み
                  </span>
                )}
              </div>

              <ol className="flex flex-wrap gap-1.5">
                {order.map((p, i) => {
                  const fixed = i === 0;
                  const isOver =
                    dragging?.party === party && over === i && dragging.from !== i;
                  return (
                    <li
                      key={p}
                      draggable={!fixed}
                      onDragStart={() => setDragging({ party, from: i })}
                      onDragEnd={() => {
                        setDragging(null);
                        setOver(null);
                      }}
                      onDragOver={(e) => {
                        if (!dragging || dragging.party !== party || fixed) return;
                        e.preventDefault();
                        setOver(i);
                      }}
                      onDrop={(e) => {
                        e.preventDefault();
                        if (dragging && dragging.party === party) move(party, dragging.from, i);
                        setDragging(null);
                        setOver(null);
                      }}
                      className="flex items-center gap-1 rounded-lg px-2 py-1 text-[12px]"
                      style={{
                        background: fixed ? "var(--bar-450)" : "var(--neutral)",
                        color: fixed ? "#ffffff" : "var(--ink-2)",
                        cursor: fixed ? "default" : "grab",
                        outline: isOver ? "2px solid var(--gain)" : "none",
                        opacity: dragging?.party === party && dragging.from === i ? 0.4 : 1,
                      }}
                    >
                      <span className="tnum opacity-60">{i + 1}</span>
                      <span
                        style={
                          p in personas.derived && !fixed
                            ? { color: "var(--warning)" }
                            : undefined
                        }
                      >
                        {p}
                      </span>
                      {!fixed && (
                        <span className="ml-0.5 flex gap-0.5">
                          <button
                            type="button"
                            onClick={() => move(party, i, i - 1)}
                            disabled={i <= 1}
                            aria-label={`${party}の順序: ${p} を上げる`}
                            className="px-1 leading-none disabled:opacity-25"
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            onClick={() => move(party, i, i + 1)}
                            disabled={i >= order.length - 1}
                            aria-label={`${party}の順序: ${p} を下げる`}
                            className="px-1 leading-none disabled:opacity-25"
                          >
                            ↓
                          </button>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </div>
          );
        })}
      </div>
    </div>
  );
}
