/**
 * ゴールデンテスト。
 *
 * 正解の源は Python 側（`src/export_sim.py`、さらにその元は検証済みの
 * `src/verify/checks.py`）。このテストが通らない限り UI には手を付けない。
 *
 * とくに大事なのは「現行制度パラメータで再計算したら、実際の選挙結果と
 * 1議席・1人の狂いもなく一致する」こと。これが崩れたら他の案の試算も信用できない。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { adams, divisorOf, divisorScale, isEligible, simulate } from "./engine";
import { BASELINE_PARAMS } from "./presets";
import type { ElectionData, Personas, SimParams } from "./types";

const ELECTION_IDS = ["r08-02-08", "r06-10-27", "r03-10-31", "h29-10-22", "h26-12-14"];

/** `web/` ディレクトリ。 */
const WEB_ROOT = join(__dirname, "..", "..");

function loadData(id: string): ElectionData {
  return JSON.parse(readFileSync(join(WEB_ROOT, "public", "data", `${id}.sim.json`), "utf8"));
}

type Golden = {
  election_id: string;
  presets: Record<
    string,
    {
      params: {
        divisor_method: string;
        first_divisor_tenths: number;
        pr_seat_delta: number;
        dual_min_vote_share: string;
        dual_min_sekihai_rate: string | null;
        list_exhaustion: string;
        tier_linkage: string;
        heiyo_overhang: string;
        smd_voting: string;
      };
      blocks: {
        block: string;
        seats: number;
        order: { party: string; divisor: number; filled: boolean }[];
        vacancies: number;
        seats_by_party: Record<string, number>;
        capacity: Record<string, number>;
        winners: Record<string, string[]>;
      }[];
      pr_seats_by_party: Record<string, number>;
      total_seats_by_party: Record<string, number>;
      vacancies: number;
      tie_blocks: string[];
    }
  >;
};

const PERSONAS: Personas = JSON.parse(
  readFileSync(join(WEB_ROOT, "public", "data", "personas.json"), "utf8")
);

function loadGolden(id: string): Golden {
  return JSON.parse(readFileSync(join(__dirname, "__fixtures__", `${id}.golden.json`), "utf8"));
}

/** ゴールデン側の params 表現を TS の SimParams に直す。 */
function toParams(p: Golden["presets"][string]["params"]): SimParams {
  const [num, den] = p.dual_min_vote_share.split("/");
  return {
    divisorMethod: p.divisor_method as SimParams["divisorMethod"],
    firstDivisorTenths: p.first_divisor_tenths,
    prSeatDelta: p.pr_seat_delta,
    dualMinVoteShare: [Number(num), den === undefined ? 1 : Number(den)],
    dualMinSekihaiRate: p.dual_min_sekihai_rate === null ? null : Number(p.dual_min_sekihai_rate),
    listExhaustion: p.list_exhaustion as SimParams["listExhaustion"],
    tierLinkage: p.tier_linkage as SimParams["tierLinkage"],
    heiyoOverhang: p.heiyo_overhang as SimParams["heiyoOverhang"],
    smdVoting: p.smd_voting as SimParams["smdVoting"],
  };
}

describe.each(ELECTION_IDS)("%s", (id) => {
  const data = loadData(id);
  const golden = loadGolden(id);

  describe("現行制度での再現", () => {
    const result = simulate(data, BASELINE_PARAMS);

    it("ブロック×党派の議席数が実際の結果と一致する", () => {
      for (const block of data.blocks) {
        const got = result.blocks.find((b) => b.block === block.block)!;
        for (const p of block.parties) {
          expect(
            got.seatsByParty[p.party] ?? 0,
            `${block.block}/${p.party}`
          ).toBe(p.actualSeats);
        }
      }
    });

    it("比例当選者の顔ぶれが実際の結果と一致する", () => {
      for (const block of data.blocks) {
        const got = result.blocks.find((b) => b.block === block.block)!;
        const actual = block.parties
          .flatMap((p) => p.list.filter((e) => e.actualElected).map((e) => e.name))
          .sort();
        const calc = Object.values(got.winners).flat().sort();
        expect(calc, block.block).toEqual(actual);
      }
    });

    it("比例議席の総数が定数どおりで、欠員が出ない", () => {
      const total = Object.values(result.prSeatsByParty).reduce((a, b) => a + b, 0);
      expect(total).toBe(data.meta.pr_seats);
      expect(result.vacancies).toBe(0);
    });

    it("小選挙区と合わせた総議席が定数と一致する", () => {
      const total = Object.values(result.totalSeatsByParty).reduce((a, b) => a + b, 0);
      expect(total).toBe(data.meta.total_seats);
    });
  });

  describe("Python 実装との突合", () => {
    for (const [name, expected] of Object.entries(golden.presets)) {
      it(`${name}: 議席・獲得順・当選者・欠員がすべて一致する`, () => {
        const result = simulate(data, toParams(expected.params), PERSONAS);

        expect(result.prSeatsByParty).toEqual(expected.pr_seats_by_party);
        expect(result.totalSeatsByParty).toEqual(expected.total_seats_by_party);
        expect(result.vacancies).toBe(expected.vacancies);
        expect(result.tieBlocks).toEqual(expected.tie_blocks);

        for (const want of expected.blocks) {
          const got = result.blocks.find((b) => b.block === want.block)!;
          expect(got.seats, `${want.block} 定数`).toBe(want.seats);
          expect(got.order, `${want.block} 獲得順`).toEqual(want.order);
          expect(got.seatsByParty, `${want.block} 議席`).toEqual(want.seats_by_party);
          expect(got.capacity, `${want.block} 名簿`).toEqual(want.capacity);
          expect(got.winners, `${want.block} 当選者`).toEqual(want.winners);
          expect(got.vacancies, `${want.block} 欠員`).toBe(want.vacancies);
        }
      });
    }
  });
});

describe("当選資格の判定", () => {
  const data = loadData("r08-02-08");
  const entries = data.blocks.flatMap((b) => b.parties.flatMap((p) => p.list));

  it("小選挙区で当選した重複立候補者は比例の当選人になれない", () => {
    const won = entries.filter((e) => e.smdWon);
    expect(won.length).toBeGreaterThan(0);
    for (const e of won) expect(isEligible(e, BASELINE_PARAMS)).toBe(false);
  });

  it("単独の名簿登載者は得票率要件でも惜敗率要件でも落とされない", () => {
    const solo = entries.filter((e) => !e.dual);
    expect(solo.length).toBeGreaterThan(0);
    const strict: SimParams = {
      ...BASELINE_PARAMS,
      dualMinVoteShare: [1, 2],
      dualMinSekihaiRate: 99,
    };
    for (const e of solo) expect(isEligible(e, strict)).toBe(true);
  });

  it("得票率要件は境界でちょうど満たすときに通る", () => {
    const entry = {
      rank: 1,
      name: "境界",
      dual: true,
      actualElected: false,
      actualElectedOrder: null,
      districtId: "テスト1",
      smdName: "境界",
      smdWon: false,
      smdVotes: 1000,
      districtValidVotes: 6000,
      districtTopVotes: 3000,
    };
    // 1000 / 6000 はちょうど 1/6
    expect(isEligible(entry, { ...BASELINE_PARAMS, dualMinVoteShare: [1, 6] })).toBe(true);
    expect(isEligible({ ...entry, smdVotes: 999 }, { ...BASELINE_PARAMS, dualMinVoteShare: [1, 6] })).toBe(
      false
    );
  });

  it("惜敗率の下限は境界でちょうど満たすときに通る", () => {
    const entry = {
      rank: 1,
      name: "境界",
      dual: true,
      actualElected: false,
      actualElectedOrder: null,
      districtId: "テスト1",
      smdName: "境界",
      smdWon: false,
      smdVotes: 1500,
      districtValidVotes: 6000,
      districtTopVotes: 3000,
    };
    // 惜敗率はちょうど 50%
    expect(isEligible(entry, { ...BASELINE_PARAMS, dualMinSekihaiRate: 50 })).toBe(true);
    expect(isEligible(entry, { ...BASELINE_PARAMS, dualMinSekihaiRate: 51 })).toBe(false);
  });
});

describe("修正サンラグ式", () => {
  const data = loadData("r08-02-08");
  const modified = (tenths: number): SimParams => ({
    ...BASELINE_PARAMS,
    divisorMethod: "modifiedSainteLague",
    firstDivisorTenths: tenths,
  });

  it("除数列は 第1除数, 3, 5, 7 …（内部では10倍の整数）", () => {
    expect(divisorOf("modifiedSainteLague", 0, 14)).toBe(14);
    expect(divisorOf("modifiedSainteLague", 1, 14)).toBe(30);
    expect(divisorOf("modifiedSainteLague", 2, 14)).toBe(50);
    expect(divisorOf("modifiedSainteLague", 3, 14)).toBe(70);
    // 第1除数だけが動く
    expect(divisorOf("modifiedSainteLague", 0, 21)).toBe(21);
    expect(divisorOf("modifiedSainteLague", 1, 21)).toBe(30);
  });

  it("倍率はこの方式のときだけ10になる", () => {
    expect(divisorScale("dhondt")).toBe(1);
    expect(divisorScale("sainteLague")).toBe(1);
    expect(divisorScale("modifiedSainteLague")).toBe(10);
  });

  it("第1除数を1.0にすると純粋なサンラグ式と同じ議席になる", () => {
    const pure = simulate(data, { ...BASELINE_PARAMS, divisorMethod: "sainteLague" });
    const asModified = simulate(data, modified(10));
    expect(asModified.prSeatsByParty).toEqual(pure.prSeatsByParty);
  });

  it("第1除数を大きくするほど、結果がドント式の側に寄る", () => {
    const dhondt = simulate(data, BASELINE_PARAMS).prSeatsByParty;
    const pure = simulate(data, { ...BASELINE_PARAMS, divisorMethod: "sainteLague" })
      .prSeatsByParty;

    // ドント式からの差の総量。第1除数を上げるほど小さくなっていくはず。
    const distance = (seats: Record<string, number>) =>
      [...new Set([...Object.keys(dhondt), ...Object.keys(seats)])].reduce(
        (sum, p) => sum + Math.abs((seats[p] ?? 0) - (dhondt[p] ?? 0)),
        0
      );

    const d10 = distance(pure);
    const d14 = distance(simulate(data, modified(14)).prSeatsByParty);
    const d30 = distance(simulate(data, modified(30)).prSeatsByParty);

    expect(d10).toBeGreaterThan(0);
    expect(d14).toBeLessThanOrEqual(d10);
    expect(d30).toBeLessThanOrEqual(d14);
  });

  it("1.4では純粋なサンラグ式より小政党の議席が出にくい", () => {
    const pure = simulate(data, { ...BASELINE_PARAMS, divisorMethod: "sainteLague" })
      .prSeatsByParty;
    const m14 = simulate(data, modified(14)).prSeatsByParty;
    const dhondt = simulate(data, BASELINE_PARAMS).prSeatsByParty;

    // 第1党は ドント ≧ 修正サンラグ ≧ 純サンラグ の順に議席が多い
    const top = "自由民主党";
    expect(dhondt[top]).toBeGreaterThanOrEqual(m14[top]);
    expect(m14[top]).toBeGreaterThanOrEqual(pure[top]);
  });

  it("どの第1除数でも比例議席の合計は定数どおり", () => {
    for (let tenths = 10; tenths <= 30; tenths++) {
      const result = simulate(data, modified(tenths));
      const total = Object.values(result.prSeatsByParty).reduce((a, b) => a + b, 0);
      expect(total, `第1除数 ${tenths / 10}`).toBe(data.meta.pr_seats);
    }
  });
});

describe("連用制と併用制", () => {
  const renyo = (id: string) =>
    simulate(loadData(id), { ...BASELINE_PARAMS, tierLinkage: "renyo" });
  const heiyoFixed = (id: string) =>
    simulate(loadData(id), {
      ...BASELINE_PARAMS,
      tierLinkage: "heiyo",
      heiyoOverhang: "truncate",
    });
  const heiyoExpand = (id: string) =>
    simulate(loadData(id), {
      ...BASELINE_PARAMS,
      tierLinkage: "heiyo",
      heiyoOverhang: "expand",
    });

  it.each(ELECTION_IDS)(
    "%s: 総定数を固定した併用制は連用制と完全に一致する",
    (id) => {
      // 比例議席の候補（各党の除数のうち小選挙区当選者数を超えるもの）から商の高い順に
      // 定数分を取る操作が両者で一致するため、これは数学的な同一性であって偶然ではない。
      expect(heiyoFixed(id).prSeatsByParty).toEqual(renyo(id).prSeatsByParty);
      expect(heiyoFixed(id).totalSeatsByParty).toEqual(renyo(id).totalSeatsByParty);
    }
  );

  it.each(ELECTION_IDS)("%s: 連用制では総定数が変わらない", (id) => {
    const data = loadData(id);
    const total = Object.values(renyo(id).totalSeatsByParty).reduce((a, b) => a + b, 0);
    expect(total).toBe(data.meta.total_seats);
  });

  it.each(ELECTION_IDS)("%s: 超過を認めた併用制では議席が増える", (id) => {
    const data = loadData(id);
    const total = Object.values(heiyoExpand(id).totalSeatsByParty).reduce((a, b) => a + b, 0);
    expect(total).toBeGreaterThan(data.meta.total_seats);
    // 連用制とは別の結果になる（同一性は総定数を固定したときだけ）
    expect(heiyoExpand(id).totalSeatsByParty).not.toEqual(renyo(id).totalSeatsByParty);
  });

  it("連用制では小選挙区で勝った党ほど比例が回らない", () => {
    const data = loadData("r08-02-08");
    const base = simulate(data, BASELINE_PARAMS);
    const r = renyo("r08-02-08");
    // 自民は248の小選挙区を取っているので、比例の除数が249から始まる
    expect(data.smd.seatsByParty["自由民主党"]).toBe(248);
    expect(r.prSeatsByParty["自由民主党"]).toBeLessThan(base.prSeatsByParty["自由民主党"]);
    // 小選挙区で議席のない党は比例が増える
    expect(data.smd.seatsByParty["日本共産党"] ?? 0).toBe(0);
    expect(r.prSeatsByParty["日本共産党"]).toBeGreaterThan(base.prSeatsByParty["日本共産党"]);
  });

  it("併用制では比例に名簿のない当選者の分を総議席から差し引く", () => {
    const data = loadData("r08-02-08");
    // 無所属は小選挙区で5議席。比例配分の対象外なので議席数は変わらない
    expect(data.smd.seatsByParty["無所属"]).toBe(5);
    expect(heiyoFixed("r08-02-08").totalSeatsByParty["無所属"]).toBe(5);
    expect(heiyoExpand("r08-02-08").totalSeatsByParty["無所属"]).toBe(5);
  });
});

describe("アダムズ方式", () => {
  it("配分の合計が指定した議席数と一致する", () => {
    const pops = { a: 1000, b: 700, c: 300, d: 90 };
    for (const total of [4, 5, 10, 50, 131]) {
      const got = adams(pops, total);
      expect(Object.values(got).reduce((x, y) => x + y, 0)).toBe(total);
    }
  });

  it("人口が少ないブロックにも必ず1議席が行く", () => {
    const got = adams({ a: 1_000_000, b: 1 }, 10);
    expect(got.b).toBe(1);
    expect(got.a).toBe(9);
  });

  it("ブロック数を下回る議席数は受け付けない", () => {
    expect(() => adams({ a: 10, b: 10 }, 1)).toThrow();
  });
});
