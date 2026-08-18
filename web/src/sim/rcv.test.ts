/**
 * 優先順位付投票の検算。
 *
 * この試算だけは実際の投票結果ではなく、仮想のペルソナの選好順序が生む数字なので、
 * 「正しい議席数」というものが存在しない。そのかわりここで確かめるのは
 *
 *   ・Python 側で書いた同じ手順の実装と、同じ答えになること
 *   ・仮定によらず成り立つ性質（議席の総数、第1選好で過半数なら結果が動かない）
 *
 * の2つ。前者は移植のずれを、後者は実装の壊れを捕まえる。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { simulate } from "./engine";
import { BASELINE_PARAMS } from "./presets";
import { irvDistrict, isSecuredOnFirstPreferences, solveSmd } from "./rcv";
import type { ElectionData, Personas, SimParams } from "./types";

const DATA_DIR = join(__dirname, "..", "..", "public", "data");
const PERSONAS: Personas = JSON.parse(
  readFileSync(join(DATA_DIR, "personas.json"), "utf8")
);
const ELECTION_IDS = ["r08-02-08", "r06-10-27", "r03-10-31", "h29-10-22", "h26-12-14"];

function loadData(id: string): ElectionData {
  return JSON.parse(readFileSync(join(DATA_DIR, `${id}.sim.json`), "utf8"));
}

const RCV: SimParams = { ...BASELINE_PARAMS, smdVoting: "rcv" };

describe("Python 側の試算と一致する", () => {
  it("第51回", () => {
    const data = loadData("r08-02-08");
    const r = simulate(data, RCV, PERSONAS);
    expect(r.smd.seatsByParty["自由民主党"]).toBe(218);
    expect(r.smd.seatsByParty["国民民主党"]).toBe(27);
    expect(r.smd.seatsByParty["日本維新の会"]).toBe(29);
    expect(r.smd.securedOnFirstPreferences).toBe(156);
    expect(r.smd.flipped.length).toBe(38);
  });

  it("第50回", () => {
    const r = simulate(loadData("r06-10-27"), RCV, PERSONAS);
    expect(r.smd.seatsByParty["自由民主党"]).toBe(152);
    expect(r.smd.seatsByParty["立憲民主党"]).toBe(67);
    expect(r.smd.seatsByParty["無所属"]).toBe(15);
    expect(r.smd.securedOnFirstPreferences).toBe(127);
  });

  it("第49回", () => {
    const r = simulate(loadData("r03-10-31"), RCV, PERSONAS);
    expect(r.smd.seatsByParty["自由民主党"]).toBe(195);
    expect(r.smd.seatsByParty["立憲民主党"]).toBe(40);
    expect(r.smd.securedOnFirstPreferences).toBe(199);
  });
});

describe.each(ELECTION_IDS)("%s — 仮定によらず成り立つこと", (id) => {
  const data = loadData(id);
  const result = simulate(data, RCV, PERSONAS);

  it("小選挙区の議席の総数は定数どおり", () => {
    const total = Object.values(result.smd.seatsByParty).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.meta.smd_seats);
  });

  it("小選挙区と比例を合わせた総議席も定数どおり", () => {
    const total = Object.values(result.totalSeatsByParty).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.meta.total_seats);
  });

  it("第1選好で過半数を取った選挙区は結果が動かない", () => {
    let checked = 0;
    for (const d of data.smd.districts) {
      if (!isSecuredOnFirstPreferences(d)) continue;
      checked += 1;
      const r = irvDistrict(d, PERSONAS);
      expect(r.winner, d.id).toBe(d.winner);
      expect(r.rounds, d.id).toBe(1);
    }
    expect(checked).toBeGreaterThan(100);
  });

  it("入れ替わるのは、第1選好で過半数に達していない選挙区だけ", () => {
    const secured = new Set(
      data.smd.districts.filter(isSecuredOnFirstPreferences).map((d) => d.id)
    );
    for (const f of result.smd.flipped) {
      expect(secured.has(f.district), f.district).toBe(false);
    }
  });

  it("単記を選べば現行の結果に戻る", () => {
    const plurality = solveSmd(data.smd.districts, PERSONAS, "plurality");
    expect(plurality.seatsByParty).toEqual(data.smd.seatsByParty);
    expect(plurality.flipped).toEqual([]);
    expect(plurality.exhausted).toBe(0);
  });
});

describe("移譲の筋道", () => {
  const data = loadData("r08-02-08");

  it("各回の記録は候補が1人ずつ減っていく形になっている", () => {
    const d = data.smd.districts.find((x) => !isSecuredOnFirstPreferences(x))!;
    const r = irvDistrict(d, PERSONAS);
    for (let i = 1; i < r.log.length; i++) {
      expect(r.log[i].standing.length).toBe(r.log[i - 1].standing.length - 1);
    }
    // 最後の回だけが当選確定（脱落者なし）
    expect(r.log[r.log.length - 1].eliminated).toBeNull();
    for (let i = 0; i < r.log.length - 1; i++) {
      expect(r.log[i].eliminated).not.toBeNull();
    }
  });

  it("当選者は最後の回で過半数を取っている", () => {
    for (const d of data.smd.districts.slice(0, 40)) {
      const r = irvDistrict(d, PERSONAS);
      const last = r.log[r.log.length - 1];
      const top = last.standing[0];
      expect(top.name, d.id).toBe(r.winner);
      // 候補が1人だけ残った場合を除き、過半数に達している
      if (last.standing.length > 1) expect(top.share, d.id).toBeGreaterThan(50);
    }
  });

  it("選好順序を組み替えると結果が変わる", () => {
    const base = simulate(data, RCV, PERSONAS);
    // 自民党支持層の2位以下を逆順にする
    const flipped = [...PERSONAS.orderings["自由民主党"]];
    const [head, ...rest] = flipped;
    const modified: Personas = {
      ...PERSONAS,
      orderings: { ...PERSONAS.orderings, 自由民主党: [head, ...rest.reverse()] },
    };
    const after = simulate(data, RCV, modified);
    expect(after.smd.seatsByParty).not.toEqual(base.smd.seatsByParty);
  });
});
