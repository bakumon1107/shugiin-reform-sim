/**
 * 描画のスモークテスト。
 *
 * エンジンの正しさは `sim/engine.test.ts` が見ているので、ここで見るのは
 * 「実データを流し込んだときに画面側が落ちないか」。全選挙回 × 全プリセット、
 * さらに極端なパラメータでも組み立てられることを確かめる。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { decompose } from "@/lib/decompose";
import { simulate } from "@/sim/engine";
import { BASELINE_PARAMS, PRESETS } from "@/sim/presets";
import type { ElectionData, Personas, SimParams } from "@/sim/types";

import { BlockDetail } from "./BlockDetail";
import { DistrictSystem } from "./DistrictSystem";
import { RateEditor } from "./RateEditor";
import { RcvDistricts } from "./RcvDistricts";
import { RcvNotice } from "./RcvNotice";
import { Decomposition } from "./Decomposition";
import { ParamControls } from "./ParamControls";
import { SeatTable } from "./SeatTable";
import { StatTiles } from "./StatTiles";

const ELECTION_IDS = ["r08-02-08", "r06-10-27", "r03-10-31", "h29-10-22", "h26-12-14"];
const DATA_DIR = join(__dirname, "..", "..", "public", "data");

// 優先順位付投票のプリセットは仮想ペルソナの選好順序を要るので、ここでも読み込む
const PERSONAS: Personas = JSON.parse(
  readFileSync(join(DATA_DIR, "personas.json"), "utf8")
);

function loadData(id: string): ElectionData {
  return JSON.parse(readFileSync(join(DATA_DIR, `${id}.sim.json`), "utf8"));
}

/** 案のプリセットに加えて、操作盤で作れる極端な組み合わせも試す。 */
function paramCases(data: ElectionData): { name: string; params: SimParams }[] {
  return [
    ...PRESETS.map((p) => ({ name: p.name, params: p.params })),
    {
      name: "比例を11まで削る",
      params: { ...BASELINE_PARAMS, prSeatDelta: -(data.meta.pr_seats - 11) },
    },
    {
      name: "要件を最も厳しく",
      params: {
        divisorMethod: "sainteLague" as const,
        firstDivisorTenths: 14,
        prSeatDelta: -45,
        dualMinVoteShare: [1, 4] as [number, number],
        dualMinSekihaiRate: 95,
        listExhaustion: "vacant" as const,
        tierLinkage: "parallel" as const,
        heiyoOverhang: "truncate" as const,
        smdVoting: "plurality" as const,
      },
    },
    {
      name: "優先順位付投票",
      params: { ...BASELINE_PARAMS, smdVoting: "rcv" as const },
    },
    {
      name: "優先順位付投票＋自民案",
      params: {
        ...PRESETS.find((p) => p.id === "ldp")!.params,
        smdVoting: "rcv" as const,
      },
    },
    {
      name: "修正サンラグの第1除数を上限まで",
      params: {
        ...BASELINE_PARAMS,
        divisorMethod: "modifiedSainteLague" as const,
        firstDivisorTenths: 30,
      },
    },
  ];
}

describe.each(ELECTION_IDS)("%s", (id) => {
  const data = loadData(id);
  const baseline = simulate(data, BASELINE_PARAMS, PERSONAS);

  it.each(paramCases(data))("$name で画面が組み立てられる", ({ params }) => {
    const proposal = simulate(data, params, PERSONAS);
    const steps = decompose(data, params, PERSONAS);
    const legalTotal = data.meta.smd_seats + data.meta.pr_seats + params.prSeatDelta;

    const html = renderToStaticMarkup(
      <>
        <StatTiles
          tiles={[
            { label: "法定定数", value: String(legalTotal), delta: legalTotal - data.meta.total_seats },
            { label: "欠員", value: String(proposal.vacancies) },
          ]}
        />
        <SeatTable
          baseline={baseline.totalSeatsByParty}
          proposal={proposal.totalSeatsByParty}
          proposalName="案"
          totalSeats={legalTotal}
        />
        <Decomposition steps={steps} baselineSeats={baseline.totalSeatsByParty} />
        <ParamControls params={params} prSeats={data.meta.pr_seats} onChange={() => {}} />
        <BlockDetail data={data} baseline={baseline} proposal={proposal} params={params} />
        <DistrictSystem value={params.smdVoting} onChange={() => {}} />
        {params.smdVoting === "rcv" && (
          <>
            <RcvNotice
              smd={proposal.smd}
              personas={PERSONAS}
              districtCount={data.meta.smd_seats}
              voteScale={data.voteScale}
              rateOverrides={{}}
              onChangeRate={() => {}}
              onResetRates={() => {}}
            />
            <RateEditor
              personas={PERSONAS}
              overrides={{}}
              onChange={() => {}}
              onReset={() => {}}
            />
            <RcvDistricts districts={proposal.smd.districts} voteScale={data.voteScale} />
          </>
        )}
      </>
    );

    expect(html.length).toBeGreaterThan(1000);
    // 全ブロックが出ていること
    for (const b of data.blocks) expect(html).toContain(b.block);
  });

  it("欠員を含めても議席の合計は法定定数を超えない", () => {
    for (const { params } of paramCases(data)) {
      const proposal = simulate(data, params, PERSONAS);
      const legalTotal = data.meta.smd_seats + data.meta.pr_seats + params.prSeatDelta;
      const filled = Object.values(proposal.totalSeatsByParty).reduce((a, b) => a + b, 0);
      expect(filled + proposal.vacancies).toBe(legalTotal);
    }
  });
});
