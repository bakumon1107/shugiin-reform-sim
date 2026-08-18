"use client";

import { useEffect, useMemo, useState } from "react";

import { BlockDetail } from "@/components/BlockDetail";
import { Decomposition } from "@/components/Decomposition";
import { ParamControls } from "@/components/ParamControls";
import { RulingShare } from "@/components/RulingShare";
import { SeatTable } from "@/components/SeatTable";
import { StatTiles } from "@/components/StatTiles";
import { decompose } from "@/lib/decompose";
import { RULING_DEFAULT } from "@/lib/ruling";
import { simulate } from "@/sim/engine";
import { BASELINE_PARAMS, PRESETS } from "@/sim/presets";
import { DistrictSystem } from "@/components/DistrictSystem";
import { RcvDistricts } from "@/components/RcvDistricts";
import { RcvNotice } from "@/components/RcvNotice";
import type { ElectionData, Personas, SimParams } from "@/sim/types";

type IndexEntry = {
  id: string;
  ordinal: number;
  date: string;
  smdSeats: number;
  prSeats: number;
  totalSeats: number;
  sourceUrl: string;
};

function sameParams(a: SimParams, b: SimParams): boolean {
  return (
    a.divisorMethod === b.divisorMethod &&
    // 第1除数は修正サンラグのときしか効かない
    (a.divisorMethod !== "modifiedSainteLague" ||
      a.firstDivisorTenths === b.firstDivisorTenths) &&
    a.prSeatDelta === b.prSeatDelta &&
    a.dualMinVoteShare[0] === b.dualMinVoteShare[0] &&
    a.dualMinVoteShare[1] === b.dualMinVoteShare[1] &&
    a.dualMinSekihaiRate === b.dualMinSekihaiRate &&
    a.listExhaustion === b.listExhaustion &&
    a.tierLinkage === b.tierLinkage &&
    // 超過議席のルールは併用制のときしか効かない
    (a.tierLinkage !== "heiyo" || a.heiyoOverhang === b.heiyoOverhang)
    // 選挙区制度は別のタブで選ぶ独立の軸なので、案の一致判定には含めない
  );
}

export default function Home() {
  const [index, setIndex] = useState<IndexEntry[] | null>(null);
  const [electionId, setElectionId] = useState<string | null>(null);
  // 読み込み済みのデータは、どの選挙回のものかを添えて持つ。選挙回を切り替えた
  // 直後に前の回の数字が残らないよう、表示に使うかどうかはここから導く。
  const [loaded, setLoaded] = useState<{ id: string; data: ElectionData } | null>(null);
  const [presetId, setPresetId] = useState("ldp");
  const [params, setParams] = useState<SimParams>(
    PRESETS.find((p) => p.id === "ldp")!.params
  );
  const [error, setError] = useState<string | null>(null);
  // 与党の選び直しは選挙回ごとに覚える。既定値は選挙時点の連立。
  const [rulingOverride, setRulingOverride] = useState<Record<string, string[]>>({});
  const [personas, setPersonas] = useState<Personas | null>(null);
  // 読み手が動かした拒否率。優先順位付投票の数字はこの値が決めているので、
  // 仮定を隠して1つの答えを出すより、握らせて動かしてもらう。
  const [rateOverrides, setRateOverrides] = useState<Record<string, Record<string, number>>>({});

  useEffect(() => {
    fetch("/data/index.json")
      .then((r) => r.json())
      .then((idx: IndexEntry[]) => {
        setIndex(idx);
        setElectionId(idx[0].id);
      })
      .catch(() => setError("選挙回の一覧を読み込めませんでした"));
  }, []);

  // 優先順位付投票で使う仮想ペルソナの選好順序
  useEffect(() => {
    fetch("/data/personas.json")
      .then((r) => r.json())
      .then(setPersonas)
      .catch(() => setError("選好順序を読み込めませんでした"));
  }, []);

  useEffect(() => {
    if (!electionId) return;
    let stale = false;
    fetch(`/data/${electionId}.sim.json`)
      .then((r) => r.json())
      .then((d: ElectionData) => {
        if (!stale) setLoaded({ id: electionId, data: d });
      })
      .catch(() => setError("選挙データを読み込めませんでした"));
    return () => {
      stale = true;
    };
  }, [electionId]);

  const data = loaded && loaded.id === electionId ? loaded.data : null;

  const preset = PRESETS.find((p) => p.id === presetId);
  const isCustom = preset ? !sameParams(params, preset.params) : true;

  // 読み手が動かした拒否率を反映する。順序も層もここから作り直される。
  const effectivePersonas = useMemo<Personas | null>(() => {
    if (!personas) return null;
    if (Object.keys(rateOverrides).length === 0) return personas;
    const rates: Personas["rejectionRates"] = {};
    for (const [voter, row] of Object.entries(personas.rejectionRates)) {
      rates[voter] = { ...row, ...(rateOverrides[voter] ?? {}) };
    }
    // 選好順序は拒否率から導出されるので、ここでは率だけ差し替えればよい
    return { ...personas, rejectionRates: rates };
  }, [personas, rateOverrides]);

  const view = useMemo(() => {
    if (!data) return null;
    if (params.smdVoting === "rcv" && !effectivePersonas) return null;
    const baseline = simulate(data, BASELINE_PARAMS, effectivePersonas);
    const proposal = simulate(data, params, effectivePersonas);
    const steps = decompose(data, params, effectivePersonas);

    // 法定定数。併用制で超過議席を認めた場合はここが膨らむので、配られた比例議席の
    // 実数と、条文上の比例定数の大きい方を取る。
    const prAwarded = proposal.blocks.reduce((s, b) => s + b.order.length, 0);
    const statutoryPr = data.meta.pr_seats + params.prSeatDelta;
    const legalTotal = data.meta.smd_seats + Math.max(prAwarded, statutoryPr);
    // 実際に議席が埋まった数から欠員を出す（名簿が尽きて配れなかった分も欠員に含める）
    const filled = Object.values(proposal.totalSeatsByParty).reduce((a, b) => a + b, 0);
    const vacancies = legalTotal - filled;
    // 議席を持つ党派（与党の選択肢）。議席の多い順に並べる。
    const parties = Object.keys(baseline.totalSeatsByParty)
      .concat(Object.keys(proposal.totalSeatsByParty))
      .filter((p, i, a) => a.indexOf(p) === i)
      .sort((a, b) => (baseline.totalSeatsByParty[b] ?? 0) - (baseline.totalSeatsByParty[a] ?? 0));
    return { baseline, proposal, steps, legalTotal, filled, vacancies, parties };
  }, [data, params, effectivePersonas]);

  const ruling =
    (electionId ? rulingOverride[electionId] : undefined) ??
    (electionId ? (RULING_DEFAULT[electionId] ?? []) : []);

  const meta = index?.find((e) => e.id === electionId);

  if (error) {
    return (
      <p className="py-10 text-[14px]" style={{ color: "var(--critical)" }}>
        {error}
      </p>
    );
  }

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-bold">もし、この選挙が各党の改革案で行われていたら</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          実際に投じられた票をそのまま使い、議席の決め方だけを各党の案に差し替えて計算し直します。
          制度が変われば有権者も政党も行動を変えるので、これは
          <strong style={{ color: "var(--ink)" }}>「投票行動が同じだったら」という仮定の下での機械的な再計算</strong>
          であって、その制度で選挙をした場合の予測ではありません。
        </p>
      </section>

      {/* --- 選択 --- */}
      <section className="card p-4">
        <div className="divide-y" style={{ borderColor: "var(--grid)" }}>
          <div className="pb-4">
            <label
              htmlFor="election"
              className="mb-1 block text-[12px]"
              style={{ color: "var(--ink-muted)" }}
            >
              選挙回
            </label>
            <select
              id="election"
              value={electionId ?? ""}
              onChange={(e) => setElectionId(e.target.value)}
              className="rounded-lg px-3 py-2 text-[13px]"
              style={{
                border: "1px solid var(--hairline)",
                background: "var(--surface)",
                color: "var(--ink)",
              }}
            >
              {index?.map((e) => (
                <option key={e.id} value={e.id}>
                  第{e.ordinal}回（{e.date}）
                </option>
              ))}
            </select>
          </div>

          <div className="py-4">
            <DistrictSystem
              value={params.smdVoting}
              onChange={(v) => setParams((p) => ({ ...p, smdVoting: v }))}
            />
          </div>

          <div className="pt-4">
            <div id="preset-label" className="mb-1 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              比例代表・各党の案
            </div>
            <div role="group" aria-labelledby="preset-label" className="flex flex-wrap gap-2">
              {PRESETS.map((p) => {
                const active = p.id === presetId && !isCustom;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => {
                      setPresetId(p.id);
                      // 選挙区制度は別タブの選択なので、案を切り替えても保つ
                      setParams({ ...p.params, smdVoting: params.smdVoting });
                    }}
                    aria-pressed={active}
                    className="rounded-lg px-3 py-2 text-[13px]"
                    style={{
                      border: `1px solid ${active ? "var(--bar-450)" : "var(--hairline)"}`,
                      background: active ? "var(--bar-450)" : "var(--surface)",
                      color: active ? "#ffffff" : "var(--ink-2)",
                    }}
                  >
                    {p.name}
                  </button>
                );
              })}
              {isCustom && (
                <span
                  className="self-center rounded-lg px-3 py-2 text-[13px]"
                  style={{ border: "1px solid var(--bar-450)", color: "var(--bar-450)" }}
                >
                  カスタム（{preset?.name}を編集中）
                </span>
              )}
            </div>

            {preset && !isCustom && (
              <p className="mt-2 max-w-3xl text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
                {preset.summary}
              </p>
            )}
            {preset && preset.notes.length > 0 && (
              <ul className="mt-2 max-w-3xl space-y-1 text-[11px]" style={{ color: "var(--ink-muted)" }}>
                {preset.notes.map((n) => (
                  <li key={n}>※ {n}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </section>

      {!view || !data || !meta ? (
        <p className="py-10 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          読み込み中…
        </p>
      ) : (
        <>
          {/* --- 見出しの数字 --- */}
          <StatTiles
            tiles={[
              {
                label: "法定定数",
                value: String(view.legalTotal),
                delta: view.legalTotal - data.meta.total_seats,
                note: `小選挙区 ${data.meta.smd_seats}・比例 ${view.legalTotal - data.meta.smd_seats}`,
              },
              {
                label: "実際に埋まる議席",
                value: String(view.filled),
                delta:
                  view.filled - data.meta.total_seats,
                note: "欠員を差し引いた議員数",
              },
              {
                label: "名簿不足による欠員",
                value: String(view.vacancies),
                note: view.vacancies > 0 ? "他党には回らない" : "発生しない",
              },
              (() => {
                const filled = view.filled;
                const top = Object.entries(view.proposal.totalSeatsByParty).sort(
                  (a, b) => b[1] - a[1]
                )[0];
                const baseTop = view.baseline.totalSeatsByParty[top[0]] ?? 0;
                const baseFilled = data.meta.total_seats;
                return {
                  label: `第1党（${top[0]}）の議席率`,
                  value: `${((top[1] / filled) * 100).toFixed(1)}%`,
                  note: `現行 ${((baseTop / baseFilled) * 100).toFixed(1)}% → ${top[1]}議席`,
                };
              })(),
            ]}
          />

          {/* --- 優先順位付投票を選んでいるあいだの警告 --- */}
          {params.smdVoting === "rcv" && (
            <RcvNotice
              smd={view.proposal.smd}
              personas={effectivePersonas}
              districtCount={data.meta.smd_seats}
              voteScale={data.voteScale}
              rateOverrides={rateOverrides}
              onChangeRate={(voter, target, rate) =>
                setRateOverrides((prev) => ({
                  ...prev,
                  [voter]: { ...(prev[voter] ?? {}), [target]: rate },
                }))
              }
              onResetRates={() => setRateOverrides({})}
            />
          )}

          {/* --- 与党の議席占有率 --- */}
          <RulingShare
            baselineSeats={view.baseline.totalSeatsByParty}
            proposalSeats={view.proposal.totalSeatsByParty}
            baselineMembers={data.meta.total_seats}
            proposalMembers={view.filled}
            ruling={ruling}
            parties={view.parties}
            proposalName={isCustom ? "カスタム" : (preset?.name ?? "案")}
            onChangeRuling={(next) =>
              setRulingOverride((prev) => ({ ...prev, [electionId!]: next }))
            }
          />

          {/* --- 党派別の議席 --- */}
          <section className="card p-4">
            <h2 className="text-[15px] font-semibold">党派別の議席</h2>
            <p className="mt-1 mb-3 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              縦線が現行制度の議席、バーが選択中の案の議席。
            </p>
            <SeatTable
              baseline={view.baseline.totalSeatsByParty}
              proposal={view.proposal.totalSeatsByParty}
              proposalName={isCustom ? "カスタム" : (preset?.name ?? "案")}
              totalSeats={view.legalTotal}
            />
            {view.proposal.tieBlocks.length > 0 && (
              <p className="mt-3 text-[12px]" style={{ color: "var(--warning)" }}>
                ⚠ {view.proposal.tieBlocks.join("・")}
                で商が同値になりました。実際の選挙ではくじ引きになる場面で、ここでは得票数の多い党、
                なお同じなら党派名の順という決め方をしています。
              </p>
            )}
          </section>

          {/* --- 寄与分解 --- */}
          <section className="card p-4">
            <h2 className="text-[15px] font-semibold">何がこの変化を起こしたか</h2>
            <p className="mt-1 mb-2 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              現行制度から、案の要素を1つずつ順に適用したときの議席の動き。
            </p>
            <Decomposition
              steps={view.steps}
              baselineSeats={view.baseline.totalSeatsByParty}
            />
          </section>

          {/* --- パラメータ --- */}
          <section className="card p-4">
            <h2 className="text-[15px] font-semibold">制度を自分で動かす</h2>
            <p className="mt-1 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              どの案を選んでいても、ここから個別に変えられます。現行制度の値に戻せば、
              上の表は実際の選挙結果と一致します。
            </p>
            <div className="mt-2">
              <ParamControls
                params={params}
                prSeats={data.meta.pr_seats}
                onChange={setParams}
              />
            </div>
            <button
              type="button"
              // 選挙区制度は別タブの選択なので、ここでは戻さない
              onClick={() => setParams({ ...BASELINE_PARAMS, smdVoting: params.smdVoting })}
              className="mt-3 rounded-lg px-3 py-2 text-[12px]"
              style={{ border: "1px solid var(--hairline)", color: "var(--ink-2)" }}
            >
              現行制度の値に戻す
            </button>
          </section>

          {/* --- 選挙区ごとの移譲の経過 --- */}
          {params.smdVoting === "rcv" && view.proposal.smd.districts.length > 0 && (
            <RcvDistricts
              districts={view.proposal.smd.districts}
              voteScale={data.voteScale}
            />
          )}

          {/* --- ブロック別 --- */}
          <section>
            <h2 className="mb-1 text-[15px] font-semibold">比例ブロック別の内訳</h2>
            <p className="mb-3 text-[12px]" style={{ color: "var(--ink-muted)" }}>
              各ブロックを開くと、除数表・名簿の枯渇状況・比例当選者の入れ替わりまで見られます。
            </p>
            <BlockDetail
              data={data}
              baseline={view.baseline}
              proposal={view.proposal}
              params={params}
            />
          </section>

          <p className="text-[11px]" style={{ color: "var(--ink-muted)" }}>
            出典: 総務省「衆議院議員総選挙・最高裁判所裁判官国民審査結果調」（
            <a href={meta.sourceUrl}>第{meta.ordinal}回</a>）
          </p>
        </>
      )}
    </div>
  );
}
