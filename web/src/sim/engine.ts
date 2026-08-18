/**
 * 議席計算エンジン。
 *
 * 正解の源は Python 側の `src/export_sim.py`（さらにその元は検証済みの
 * `src/verify/checks.py`）にある。この実装はそれを移植したもので、
 * `engine.test.ts` のゴールデンテストで全選挙回・全プリセットの一致を確かめている。
 *
 * 数値はすべて整数のまま扱う。得票は1000倍の整数で入ってくるので、商の比較は
 * 割り算せず交差乗算で行い、浮動小数点の誤差を持ち込まない。
 */

import type {
  Block,
  BlockResult,
  DivisorMethod,
  ElectionData,
  ListEntry,
  SeatAward,
  SimParams,
  SimResult,
} from "./types";

/**
 * 除数を整数で扱うための倍率。
 *
 * 修正サンラグは第1除数を0.1刻みで動かせるようにするので、この方式だけ全ての除数を
 * 10倍して持つ（1.4, 3, 5, 7 → 14, 30, 50, 70）。商の比較は同じブロック内で同じ倍率
 * どうしなので、倍率は結果に影響しない。表示するときだけこの値で割る。
 */
export function divisorScale(method: DivisorMethod): number {
  return method === "modifiedSainteLague" ? 10 : 1;
}

/**
 * 獲得済み議席数から次の除数を返す（`divisorScale` 倍した整数）。
 *
 * 修正サンラグは第1除数だけを大きくして、得票の少ない党が1議席目を取る条件を厳しく
 * する方式。北欧などで使われている値は1.4。1.0にすると純粋なサンラグ式と同じになる。
 */
export function divisorOf(
  method: DivisorMethod,
  seatsWon: number,
  firstDivisorTenths = 14
): number {
  switch (method) {
    case "dhondt":
      return seatsWon + 1;
    case "sainteLague":
      return 2 * seatsWon + 1;
    case "modifiedSainteLague":
      return seatsWon === 0 ? firstDivisorTenths : 10 * (2 * seatsWon + 1);
  }
}

/**
 * この名簿登載者が、与えられたパラメータのもとで比例の当選人になれるか。
 *
 * 得票率要件・惜敗率要件は**重複立候補者にのみ**適用される。単独の名簿登載者には
 * 小選挙区の得票が存在しないので、これらで落としてはいけない
 * （公職選挙法95条の2第6項は重複立候補者についての規定）。
 */
export function isEligible(entry: ListEntry, params: SimParams): boolean {
  if (!entry.dual) return true;
  if (entry.smdWon) return false;

  const votes = entry.smdVotes ?? 0;
  const valid = entry.districtValidVotes ?? 0;
  const [num, den] = params.dualMinVoteShare;
  // votes / valid >= num / den
  if (votes * den < valid * num) return false;

  if (params.dualMinSekihaiRate !== null) {
    const top = entry.districtTopVotes ?? 0;
    // votes / top * 100 >= rate
    if (votes * 100 < params.dualMinSekihaiRate * top) return false;
  }
  return true;
}

/** 惜敗率（％）。分母はその選挙区の最多得票で、区割りを変えない限り不変。 */
export function sekihaiRate(entry: ListEntry): number | null {
  if (!entry.dual || !entry.smdVotes || !entry.districtTopVotes) return null;
  return (entry.smdVotes / entry.districtTopVotes) * 100;
}

/**
 * 次の1議席を取る党派を選ぶ。同値なら得票数の多い方、なお同じなら党派名順。
 *
 * `head` は除数の起点。連用制では各党の小選挙区当選者数を渡すので、小選挙区で
 * 勝った党ほど比例が回りにくくなる。
 */
function pick(
  votes: Record<string, number>,
  used: Record<string, number>,
  params: SimParams,
  allowed: string[],
  head: Record<string, number> = {}
): { party: string; divisor: number; tie: boolean } {
  const { divisorMethod: method, firstDivisorTenths: tenths } = params;
  let best = "";
  let bestDiv = 0;
  let tie = false;

  for (const party of [...allowed].sort()) {
    const div = divisorOf(method, (head[party] ?? 0) + used[party], tenths);
    if (best === "") {
      best = party;
      bestDiv = div;
      continue;
    }
    const left = votes[party] * bestDiv;
    const right = votes[best] * div;
    if (left > right) {
      best = party;
      bestDiv = div;
      tie = false;
    } else if (left === right) {
      tie = true;
      // (-votes, name) の辞書順で小さい方を採る（Python 実装と同じ決め方）
      if (
        -votes[party] < -votes[best] ||
        (-votes[party] === -votes[best] && party < best)
      ) {
        best = party;
        bestDiv = div;
      }
    }
  }
  return {
    party: best,
    divisor: divisorOf(method, (head[best] ?? 0) + used[best], tenths),
    tie,
  };
}

/**
 * 併用制でブロックの比例議席を配る。
 *
 * ブロックの総議席を比例得票で順に配り、各党への割り当てがその党の小選挙区当選者数
 * を超えた分だけを比例議席として取り出す。小選挙区で勝ちすぎた党（超過議席）には
 * 比例が回らない。
 *
 * 比例に名簿を出していない当選者（無所属など）はその議席をそのまま得るので、比例
 * 配分の対象となる総議席から先に差し引く。
 *
 * `heiyoOverhang` が `truncate` なら、取り出した比例議席が定数に達した時点で打ち切る
 * （総定数固定）。`expand` なら超過分だけ議席が増える。
 */
export function allocateHeiyo(
  votes: Record<string, number>,
  prSeats: number,
  smdByParty: Record<string, number>,
  capacity: Record<string, number>,
  params: SimParams
): { order: SeatAward[]; tie: boolean } {
  const parties = Object.keys(votes);
  const smdTotal = Object.values(smdByParty).reduce((a, b) => a + b, 0);
  const independent = Object.entries(smdByParty)
    .filter(([p]) => !(p in votes))
    .reduce((a, [, n]) => a + n, 0);
  const pool = smdTotal + prSeats - independent;
  if (pool <= 0) return { order: [], tie: false };

  const used: Record<string, number> = {}; // 総議席（小選挙区＋比例）の獲得数
  const prWon: Record<string, number> = {};
  for (const p of parties) {
    used[p] = 0;
    prWon[p] = 0;
  }
  const order: SeatAward[] = [];
  let tieSeen = false;

  for (let i = 0; i < pool; i++) {
    if (params.heiyoOverhang === "truncate" && order.length === prSeats) break;
    let allowed = parties;
    if (params.listExhaustion === "reallocate") {
      // 比例で埋める段階に入っていて名簿が尽きた党は、以後の対象から外す
      allowed = parties.filter(
        (p) => used[p] < (smdByParty[p] ?? 0) || prWon[p] < (capacity[p] ?? 0)
      );
    }
    if (allowed.length === 0) break;
    const { party, divisor, tie } = pick(votes, used, params, allowed);
    tieSeen = tieSeen || tie;
    used[party] += 1;
    if (used[party] > (smdByParty[party] ?? 0)) {
      // この議席は小選挙区当選者では埋まらないので、比例名簿から埋める
      prWon[party] += 1;
      order.push({ party, divisor, filled: prWon[party] <= (capacity[party] ?? 0) });
    }
  }
  return { order, tie: tieSeen };
}

/**
 * ブロックの議席を配分し、獲得順の一覧を返す。
 *
 * `reallocate`（現行）は名簿を使い切った党派を対象から外し、残りの議席を他党に
 * 回す（公職選挙法95条の2第4項）。
 *
 * `vacant`（自民案④）は、まず名簿の制約を無視して純粋に商の順で配分し、自党の
 * 名簿人数を超えて回ってきた議席を欠員として確定させる。他党には回さない。
 */
export function allocate(
  votes: Record<string, number>,
  seats: number,
  capacity: Record<string, number>,
  params: SimParams,
  /** 各党の除数の起点。連用制では小選挙区当選者数を渡す。 */
  headStart: Record<string, number> = {}
): { order: SeatAward[]; tie: boolean } {
  const parties = Object.keys(votes);
  const used: Record<string, number> = {};
  for (const p of parties) used[p] = 0;
  const order: SeatAward[] = [];
  let tieSeen = false;

  if (params.listExhaustion === "vacant") {
    for (let i = 0; i < seats; i++) {
      const { party, divisor, tie } = pick(votes, used, params, parties, headStart);
      tieSeen = tieSeen || tie;
      used[party] += 1;
      order.push({ party, divisor, filled: used[party] <= (capacity[party] ?? 0) });
    }
    return { order, tie: tieSeen };
  }

  for (let i = 0; i < seats; i++) {
    const allowed = parties.filter((p) => used[p] < (capacity[p] ?? 0));
    if (allowed.length === 0) break; // 全党の名簿が尽きた
    const { party, divisor, tie } = pick(votes, used, params, allowed, headStart);
    tieSeen = tieSeen || tie;
    used[party] += 1;
    order.push({ party, divisor, filled: true });
  }
  return { order, tie: tieSeen };
}

/**
 * アダムズ方式で `total` 議席を配分する。
 *
 * 除数列 0,1,2,3… の最大平均法として逐次に配る。第1議席の除数は0（＝商が無限大）
 * なので各ブロックに必ず1議席が行く。同値なら人口の多い方、なお同じならブロック名順。
 */
export function adams(populations: Record<string, number>, total: number): Record<string, number> {
  const blocks = Object.keys(populations).sort();
  if (total < blocks.length) {
    throw new Error(`議席数(${total})がブロック数(${blocks.length})を下回る`);
  }
  const seats: Record<string, number> = {};
  for (const b of blocks) seats[b] = 1;

  for (let i = 0; i < total - blocks.length; i++) {
    let best = blocks[0];
    for (const b of blocks.slice(1)) {
      const left = populations[b] * seats[best];
      const right = populations[best] * seats[b];
      if (left > right || (left === right && populations[b] > populations[best])) {
        best = b;
      }
    }
    seats[best] += 1;
  }
  return seats;
}

/** 名簿順位順（同一順位内は惜敗率降順）に並べる。 */
function listOrder(entries: ListEntry[]): ListEntry[] {
  return [...entries].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    return (sekihaiRate(b) ?? 0) - (sekihaiRate(a) ?? 0);
  });
}

function solveBlock(
  block: Block,
  seats: number,
  smdByParty: Record<string, number>,
  params: SimParams
): { result: BlockResult; tie: boolean } {
  const votes: Record<string, number> = {};
  const capacity: Record<string, number> = {};
  for (const p of block.parties) {
    votes[p.party] = p.votes;
    capacity[p.party] = p.list.filter((e) => isEligible(e, params)).length;
  }

  const { order, tie } =
    params.tierLinkage === "heiyo"
      ? allocateHeiyo(votes, seats, smdByParty, capacity, params)
      : allocate(
          votes,
          seats,
          capacity,
          params,
          // 連用制は除数の起点をその党の小選挙区当選者数にする
          params.tierLinkage === "renyo" ? smdByParty : {}
        );

  const seatsByParty: Record<string, number> = {};
  for (const seat of order) {
    if (seat.filled) seatsByParty[seat.party] = (seatsByParty[seat.party] ?? 0) + 1;
  }

  const winners: Record<string, string[]> = {};
  for (const p of block.parties) {
    const n = seatsByParty[p.party] ?? 0;
    if (n === 0) continue;
    const pool = listOrder(p.list.filter((e) => isEligible(e, params)));
    if (pool.length < n) {
      throw new Error(`${block.block}/${p.party}: 当選者を${n}人埋められない`);
    }
    winners[p.party] = pool.slice(0, n).map((e) => e.name);
  }

  return {
    result: {
      block: block.block,
      seats,
      order,
      vacancies: order.filter((s) => !s.filled).length,
      seatsByParty,
      capacity,
      winners,
    },
    tie,
  };
}

/**
 * 1回分のデータに制度パラメータを当てはめ、比例代表の議席を解く。
 *
 * 小選挙区の結果は動かさない。第1版が扱う3案はいずれも区割りにも小選挙区の投票方式
 * にも手を入れないため（チームみらい抜本案の優先順位付投票は、有権者の選好順序
 * データが存在しないので試算対象外）。
 */
export function simulate(data: ElectionData, params: SimParams): SimResult {
  const totalPr = data.meta.pr_seats + params.prSeatDelta;
  if (totalPr < data.blocks.length) {
    throw new Error(`比例定数(${totalPr})がブロック数を下回る`);
  }

  let seatsByBlock: Record<string, number>;
  if (params.prSeatDelta === 0) {
    seatsByBlock = Object.fromEntries(data.blocks.map((b) => [b.block, b.seats]));
  } else {
    seatsByBlock = adams(
      Object.fromEntries(data.blocks.map((b) => [b.block, b.electors])),
      totalPr
    );
  }

  const solved = data.blocks.map((b) =>
    solveBlock(b, seatsByBlock[b.block], data.smd.byBlock[b.block] ?? {}, params)
  );
  const blocks = solved.map((s) => s.result);
  const tieBlocks = solved.filter((s) => s.tie).map((s) => s.result.block);

  const prSeatsByParty: Record<string, number> = {};
  for (const b of blocks) {
    for (const [party, n] of Object.entries(b.seatsByParty)) {
      prSeatsByParty[party] = (prSeatsByParty[party] ?? 0) + n;
    }
  }

  const totalSeatsByParty: Record<string, number> = { ...data.smd.seatsByParty };
  for (const [party, n] of Object.entries(prSeatsByParty)) {
    totalSeatsByParty[party] = (totalSeatsByParty[party] ?? 0) + n;
  }

  return {
    blocks,
    prSeatsByParty,
    totalSeatsByParty,
    vacancies: blocks.reduce((s, b) => s + b.vacancies, 0),
    tieBlocks,
  };
}
