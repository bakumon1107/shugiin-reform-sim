import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { simulate } from "@/sim/engine";
import { BASELINE_PARAMS, PRESETS } from "@/sim/presets";
import type { ElectionData } from "@/sim/types";

import { RULING_DEFAULT, summarize, thresholds } from "./ruling";

const DATA_DIR = join(__dirname, "..", "..", "public", "data");

function loadData(id: string): ElectionData {
  return JSON.parse(readFileSync(join(DATA_DIR, `${id}.sim.json`), "utf8"));
}

describe("多数派のライン", () => {
  it("465議席なら過半数233・安定多数244・絶対安定多数261", () => {
    const [majority, stable, absolute] = thresholds(465);
    expect(majority.seats).toBe(233);
    expect(stable.seats).toBe(244);
    expect(absolute.seats).toBe(261);
    expect(stable.exact).toBe(true);
  });

  it("475議席なら過半数238・安定多数249・絶対安定多数266", () => {
    const [majority, stable, absolute] = thresholds(475);
    expect(majority.seats).toBe(238);
    expect(stable.seats).toBe(249);
    expect(absolute.seats).toBe(266);
    expect(stable.exact).toBe(true);
  });

  it("定数が既知の構成と違うときは、過半数だけが正確で他は目安になる", () => {
    const [majority, stable, absolute] = thresholds(411);
    expect(majority.seats).toBe(206);
    expect(majority.exact).toBe(true);
    expect(stable.exact).toBe(false);
    expect(absolute.exact).toBe(false);
    // 比率は現行の水準を保つ
    expect(stable.ratio).toBeGreaterThan(52);
    expect(stable.ratio).toBeLessThan(54);
    expect(absolute.seats).toBeGreaterThan(stable.seats);
  });

  it("到達ラインは満たしている中でいちばん厳しいものを返す", () => {
    expect(summarize({ A: 232 }, ["A"], 465).reached).toBeNull();
    expect(summarize({ A: 233 }, ["A"], 465).reached?.id).toBe("majority");
    expect(summarize({ A: 244 }, ["A"], 465).reached?.id).toBe("stable");
    expect(summarize({ A: 261 }, ["A"], 465).reached?.id).toBe("absolute");
  });
});

describe("与党の集計", () => {
  it("複数政党の議席を足し合わせる", () => {
    const s = summarize({ 自由民主党: 191, 公明党: 24, 立憲民主党: 148 }, ["自由民主党", "公明党"], 465);
    expect(s.seats).toBe(215);
    expect(s.ratio).toBeCloseTo((215 / 465) * 100, 5);
    expect(s.reached).toBeNull(); // 2024年の自公は過半数割れ
  });

  it("与党を選ばなければ0議席になる", () => {
    expect(summarize({ A: 100 }, [], 465).seats).toBe(0);
  });
});

describe("既定の与党が実際の選挙結果と整合する", () => {
  it("第50回の自公は過半数（233）に届かない", () => {
    const data = loadData("r06-10-27");
    const seats = simulate(data, BASELINE_PARAMS).totalSeatsByParty;
    const s = summarize(seats, RULING_DEFAULT["r06-10-27"], data.meta.total_seats);
    expect(s.seats).toBe(215);
    expect(s.reached).toBeNull();
  });

  it("第49回の自公は絶対安定多数に届く", () => {
    const data = loadData("r03-10-31");
    const seats = simulate(data, BASELINE_PARAMS).totalSeatsByParty;
    const s = summarize(seats, RULING_DEFAULT["r03-10-31"], data.meta.total_seats);
    expect(s.seats).toBe(291);
    expect(s.reached?.id).toBe("absolute");
  });

  it("既定の与党は、その選挙回に実在する党名になっている", () => {
    for (const [id, ruling] of Object.entries(RULING_DEFAULT)) {
      const data = loadData(id);
      const seats = simulate(data, BASELINE_PARAMS).totalSeatsByParty;
      for (const party of ruling) {
        expect(Object.keys(seats), `${id} の ${party}`).toContain(party);
      }
    }
  });

  it("自民案では与党の議席は減るが占有率は上がる（第51回・自民＋維新）", () => {
    const data = loadData("r08-02-08");
    const ruling = RULING_DEFAULT["r08-02-08"];
    const ldp = PRESETS.find((p) => p.id === "ldp")!.params;

    const base = simulate(data, BASELINE_PARAMS);
    const prop = simulate(data, ldp);
    const legal = data.meta.smd_seats + data.meta.pr_seats + ldp.prSeatDelta;

    const b = summarize(base.totalSeatsByParty, ruling, data.meta.total_seats);
    const p = summarize(prop.totalSeatsByParty, ruling, legal - prop.vacancies);

    expect(p.seats).toBeLessThan(b.seats);
    expect(p.ratio).toBeGreaterThan(b.ratio);
  });
});
