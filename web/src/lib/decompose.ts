/**
 * 寄与分解。
 *
 * 現行制度から目的の案へ、パラメータを1つずつ順に切り替えていき、どの変更で
 * 議席がどれだけ動いたかを取り出す。自民案のように5つの要素が同時に効く案は、
 * 最終結果だけを見ても何が効いたのか読めない。
 *
 * 順番を変えれば各段の内訳も変わる（要素は独立ではない）。ここでは
 * 「配分方式 → 定数 → 得票率要件 → 惜敗率下限 → 名簿枯渇」の順に固定し、
 * 画面上でもその旨を断ったうえで見せる。
 */

import { simulate } from "@/sim/engine";
import { BASELINE_PARAMS } from "@/sim/presets";
import type { ElectionData, Personas, SimParams } from "@/sim/types";

export type StepId =
  | "smdVoting"
  | "tierLinkage"
  | "heiyoOverhang"
  | "divisorMethod"
  | "firstDivisorTenths"
  | "prSeatDelta"
  | "dualMinVoteShare"
  | "dualMinSekihaiRate"
  | "listExhaustion";

export type Step = {
  id: StepId;
  /** この段までを適用したパラメータ */
  params: SimParams;
  label: string;
  /** 何をしたか */
  change: string;
  /** この段だけで動いた議席（党派 → 増減） */
  deltas: Record<string, number>;
  /** この段までの累計議席 */
  seats: Record<string, number>;
  vacancies: number;
};

function describe(id: StepId, params: SimParams): { label: string; change: string } {
  switch (id) {
    case "smdVoting":
      return {
        label: "小選挙区の投票方式",
        change:
          params.smdVoting === "rcv"
            ? "単記 → 優先順位付投票（※仮想ペルソナの選好順序による）"
            : "単記（現行）",
      };
    case "tierLinkage":
      return {
        label: "小選挙区と比例の連動",
        change:
          params.tierLinkage === "renyo"
            ? "並立制 → 連用制（比例の除数を「小選挙区当選者数 + 1」から始める）"
            : params.tierLinkage === "heiyo"
              ? "並立制 → 併用制（比例得票で総議席を決め、小選挙区当選者をその枠に充てる）"
              : "並立制（現行）",
      };
    case "heiyoOverhang":
      return {
        label: "超過議席の扱い",
        change:
          params.heiyoOverhang === "expand"
            ? "超過した分だけ定数が増えるのを認める"
            : "総定数を固定し、商の低い方から打ち切る",
      };
    case "divisorMethod":
      return {
        label: "比例の配分方式",
        change:
          params.divisorMethod === "sainteLague"
            ? "ドント式（÷1,2,3…）→ サンラグ式（÷1,3,5…）"
            : params.divisorMethod === "modifiedSainteLague"
              ? `ドント式（÷1,2,3…）→ 修正サンラグ式（÷${(params.firstDivisorTenths / 10).toFixed(1)},3,5…）`
              : "ドント式（÷1,2,3…）",
      };
    case "firstDivisorTenths":
      return {
        label: "修正サンラグの第1除数",
        change: `÷${(params.firstDivisorTenths / 10).toFixed(1)}, 3, 5, 7 …`,
      };
    case "prSeatDelta":
      return {
        label: "比例の定数",
        change:
          params.prSeatDelta === 0
            ? "変更なし"
            : `${params.prSeatDelta > 0 ? "+" : "−"}${Math.abs(params.prSeatDelta)}議席（ブロックへはアダムズ方式で配り直し）`,
      };
    case "dualMinVoteShare":
      return {
        label: "比例復活の最低得票率",
        change: `小選挙区で有効投票総数の ${params.dualMinVoteShare[0]}/${params.dualMinVoteShare[1]} 以上`,
      };
    case "dualMinSekihaiRate":
      return {
        label: "比例復活の惜敗率下限",
        change:
          params.dualMinSekihaiRate === null
            ? "下限なし"
            : `惜敗率 ${params.dualMinSekihaiRate}% 以上`,
      };
    case "listExhaustion":
      return {
        label: "名簿が足りないとき",
        change:
          params.listExhaustion === "vacant"
            ? "欠員にする（他党に回さない）"
            : "他党に回す（現行）",
      };
  }
}

const ORDER: StepId[] = [
  "smdVoting",
  "tierLinkage",
  "heiyoOverhang",
  "divisorMethod",
  "firstDivisorTenths",
  "prSeatDelta",
  "dualMinVoteShare",
  "dualMinSekihaiRate",
  "listExhaustion",
];

function same(id: StepId, a: SimParams, b: SimParams): boolean {
  if (id === "dualMinVoteShare") {
    return a.dualMinVoteShare[0] === b.dualMinVoteShare[0] &&
      a.dualMinVoteShare[1] === b.dualMinVoteShare[1];
  }
  // 第1除数は修正サンラグのときしか効かないので、それ以外では段として出さない。
  // 修正サンラグを選んだ段でその値も一緒に効いているため、既定値からの差だけを見る。
  if (id === "firstDivisorTenths" && b.divisorMethod !== "modifiedSainteLague") {
    return true;
  }
  // 超過議席のルールは併用制のときしか効かない
  if (id === "heiyoOverhang" && b.tierLinkage !== "heiyo") {
    return true;
  }
  return a[id] === b[id];
}

/** 現行制度から `target` へ、実際に変わるパラメータだけを1段ずつ適用する。 */
export function decompose(
  data: ElectionData,
  target: SimParams,
  personas: Personas | null = null
): Step[] {
  const steps: Step[] = [];
  let current: SimParams = { ...BASELINE_PARAMS };
  let prev = simulate(data, current, personas).totalSeatsByParty;

  for (const id of ORDER) {
    if (same(id, current, target)) continue;

    current = { ...current, [id]: target[id] } as SimParams;
    const result = simulate(data, current, personas);
    const seats = result.totalSeatsByParty;

    const deltas: Record<string, number> = {};
    for (const party of new Set([...Object.keys(prev), ...Object.keys(seats)])) {
      const d = (seats[party] ?? 0) - (prev[party] ?? 0);
      if (d !== 0) deltas[party] = d;
    }

    steps.push({
      id,
      params: current,
      ...describe(id, current),
      deltas,
      seats,
      vacancies: result.vacancies,
    });
    prev = seats;
  }
  return steps;
}
