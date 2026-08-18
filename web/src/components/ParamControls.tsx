"use client";

import type { SimParams } from "@/sim/types";

const ROW = "flex flex-wrap items-center justify-between gap-3 py-3";
const LABEL = "text-[13px] font-medium";
const HINT = "text-[11px]";

function Choice<T extends string | number>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    // 狭い画面では選択肢が1行に収まらないので折り返す。折り返さないと親から
    // はみ出してページ全体が横に伸びてしまう。
    <div
      className="inline-flex max-w-full flex-wrap overflow-hidden rounded-lg"
      style={{ border: "1px solid var(--hairline)" }}
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={String(o.value)}
            type="button"
            onClick={() => onChange(o.value)}
            aria-pressed={active}
            className="px-3 py-1.5 text-[12px] whitespace-nowrap"
            style={{
              background: active ? "var(--bar-450)" : "transparent",
              color: active ? "#ffffff" : "var(--ink-2)",
            }}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

/** 制度パラメータの操作盤。どの案を選んでいても、ここから個別に上書きできる。 */
export function ParamControls({
  params,
  prSeats,
  onChange,
}: {
  params: SimParams;
  /** その選挙回の比例定数（現行） */
  prSeats: number;
  onChange: (next: SimParams) => void;
}) {
  const set = (patch: Partial<SimParams>) => onChange({ ...params, ...patch });
  const [num, den] = params.dualMinVoteShare;

  return (
    <div className="divide-y" style={{ borderColor: "var(--grid)" }}>
      <div className={ROW}>
        <div>
          <div className={LABEL}>小選挙区と比例の連動</div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            並立制は互いに独立。連用制・併用制は小選挙区で勝った党ほど比例が回らなくなる
          </div>
        </div>
        <Choice
          value={params.tierLinkage}
          onChange={(v) => set({ tierLinkage: v })}
          options={[
            { value: "parallel", label: "並立制（現行）" },
            { value: "renyo", label: "連用制" },
            { value: "heiyo", label: "併用制" },
          ]}
        />
      </div>

      {params.tierLinkage === "heiyo" && (
        <div className={ROW}>
          <div>
            <div className={LABEL}>超過議席の扱い</div>
            <div className={HINT} style={{ color: "var(--ink-muted)" }}>
              小選挙区の当選者数が比例配分を上回った分をどうするか
            </div>
          </div>
          <Choice
            value={params.heiyoOverhang}
            onChange={(v) => set({ heiyoOverhang: v })}
            options={[
              { value: "truncate", label: "総定数を固定" },
              { value: "expand", label: "定数が増えるのを認める" },
            ]}
          />
        </div>
      )}

      {params.tierLinkage === "heiyo" && params.heiyoOverhang === "truncate" && (
        <p className="py-2 text-[11px]" style={{ color: "var(--warning)" }}>
          ⚠ 総定数を固定した併用制は、連用制と数学的に同一の制度です。比例議席の候補から
          商の高い順に定数分を取る操作が両者で一致するため、議席配分は必ず一致します。
          違いを見るには「定数が増えるのを認める」に切り替えてください。
        </p>
      )}

      <div className={ROW}>
        <div>
          <div className={LABEL}>比例の議席配分方式</div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            サンラグ式は奇数で割るので、大政党の2議席目以降が取りにくくなる
          </div>
        </div>
        <Choice
          value={params.divisorMethod}
          onChange={(v) => set({ divisorMethod: v })}
          options={[
            { value: "dhondt", label: "ドント式" },
            { value: "sainteLague", label: "サンラグ式" },
            { value: "modifiedSainteLague", label: "修正サンラグ式" },
          ]}
        />
      </div>

      {params.divisorMethod === "modifiedSainteLague" && (
        <div className={ROW}>
          <div>
            <div className={LABEL}>
              修正サンラグの第1除数{" "}
              <span className="tnum" style={{ color: "var(--ink-2)" }}>
                {(params.firstDivisorTenths / 10).toFixed(1)}
              </span>
            </div>
            <div className={HINT} style={{ color: "var(--ink-muted)" }}>
              ÷{(params.firstDivisorTenths / 10).toFixed(1)}, 3, 5, 7 …
              　大きいほど小政党が1議席目を取りにくい（1.0で純粋なサンラグ式）
            </div>
          </div>
          <div className="flex items-center gap-3">
            <input
              type="range"
              // 0.1刻み。10倍した整数で持っているので step は 1。
              min={10}
              max={30}
              step={1}
              value={params.firstDivisorTenths}
              onChange={(e) => set({ firstDivisorTenths: Number(e.target.value) })}
              aria-label="修正サンラグの第1除数"
              className="w-40"
            />
            <span className="tnum w-10 text-right text-[13px] font-semibold">
              {(params.firstDivisorTenths / 10).toFixed(1)}
            </span>
          </div>
        </div>
      )}

      <div className={ROW}>
        <div>
          <div className={LABEL}>
            比例の定数{" "}
            <span className="tnum" style={{ color: "var(--ink-2)" }}>
              {prSeats + params.prSeatDelta}
            </span>
            <span style={{ color: "var(--ink-muted)" }}>（現行 {prSeats}）</span>
          </div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            小選挙区の定数は動かさない。ブロックへはアダムズ方式で配り直す
          </div>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="range"
            // 5刻み。自民案の −45 も現行の 10増10減 も5の倍数なので届く。
            min={-Math.floor(Math.max(prSeats - 11, 0) / 5) * 5}
            max={0}
            step={5}
            value={params.prSeatDelta}
            onChange={(e) => set({ prSeatDelta: Number(e.target.value) })}
            aria-label="比例定数の増減"
            className="w-40"
          />
          <span className="tnum w-12 text-right text-[13px] font-semibold">
            {params.prSeatDelta === 0 ? "±0" : `−${Math.abs(params.prSeatDelta)}`}
          </span>
        </div>
      </div>

      <div className={ROW}>
        <div>
          <div className={LABEL}>比例復活の最低得票率</div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            重複立候補者が小選挙区で取るべき、有効投票総数に対する割合
          </div>
        </div>
        <Choice
          value={`${num}/${den}`}
          onChange={(v) => {
            const [a, b] = v.split("/").map(Number);
            set({ dualMinVoteShare: [a, b] });
          }}
          options={[
            { value: "1/10", label: "1/10（現行）" },
            { value: "1/8", label: "1/8" },
            { value: "1/6", label: "1/6" },
            { value: "1/4", label: "1/4" },
          ]}
        />
      </div>

      <div className={ROW}>
        <div>
          <div className={LABEL}>
            比例復活の惜敗率下限{" "}
            <span className="tnum" style={{ color: "var(--ink-2)" }}>
              {params.dualMinSekihaiRate === null ? "なし" : `${params.dualMinSekihaiRate}%`}
            </span>
          </div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            惜敗率＝その選挙区の当選者の得票に対する割合
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Choice
            value={params.dualMinSekihaiRate === null ? "off" : "on"}
            onChange={(v) => set({ dualMinSekihaiRate: v === "off" ? null : 30 })}
            options={[
              { value: "off", label: "なし" },
              { value: "on", label: "設ける" },
            ]}
          />
          <input
            type="range"
            // 5刻み。自民案が例示する30%・50%はどちらも5の倍数。
            min={5}
            max={95}
            step={5}
            disabled={params.dualMinSekihaiRate === null}
            value={params.dualMinSekihaiRate ?? 30}
            onChange={(e) => set({ dualMinSekihaiRate: Number(e.target.value) })}
            aria-label="惜敗率の下限"
            className="w-28 disabled:opacity-30"
          />
        </div>
      </div>

      <div className={ROW}>
        <div>
          <div className={LABEL}>名簿の登載者が足りないとき</div>
          <div className={HINT} style={{ color: "var(--ink-muted)" }}>
            小選挙区で当選した者と復活の資格を欠く者は、比例の当選人になれない
          </div>
        </div>
        <Choice
          value={params.listExhaustion}
          onChange={(v) => set({ listExhaustion: v })}
          options={[
            { value: "reallocate", label: "他党に回す（現行）" },
            { value: "vacant", label: "欠員にする" },
          ]}
        />
      </div>
    </div>
  );
}
