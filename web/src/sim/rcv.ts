/**
 * 優先順位付投票（RCV／即時決選投票）。
 *
 * **ここで出る数字は投票結果ではなく、仮定が生む数字である。**
 *
 * 有権者が候補者にどう順位をつけたかのデータは存在しない。投票用紙に残るのは第1希望
 * だけで、第2希望以降はどこにも記録されていない。そこで「どの政党を拒否しているか」を
 * 尋ねた調査から作った**仮想のペルソナ**の選好順序で代用している。
 * 詳しくは `research/personas/README.md`。
 *
 * 計算そのものは素直で、過半数を取る候補が出るまで最下位を落とし、その票を落ちた候補の
 * 党派の選好順序で次に来る党派の候補へ移す。移す先が無ければ死票になる。
 */

import type { District, IrvRound, Personas, SmdOutcome } from "./types";

/** 1選挙区の優先順位付投票。各回の途中経過も返す。 */
export function irvDistrict(
  district: District,
  personas: Personas
): {
  winner: string;
  winnerParty: string;
  rounds: number;
  exhausted: number;
  log: IrvRound[];
} {
  const log: IrvRound[] = [];
  const live = new Map<string, number>();
  const partyOf = new Map<string, string>();
  for (const c of district.candidates) {
    // 同姓同名は原典側で区別されているのでキーは氏名でよい
    live.set(c.name, c.votes);
    partyOf.set(c.name, c.party);
  }

  let exhausted = 0;
  let rounds = 0;

  for (;;) {
    rounds += 1;
    let total = 0;
    for (const v of live.values()) total += v;

    // 首位。同数は氏名順で決定的にする。
    let leader = "";
    for (const [name, v] of live) {
      if (leader === "" || v > live.get(leader)! || (v === live.get(leader)! && name < leader)) {
        leader = name;
      }
    }

    const standing = [...live.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, votes]) => ({
        name,
        party: partyOf.get(name)!,
        votes,
        share: total > 0 ? (votes / total) * 100 : 0,
      }));

    // 継続票の過半数を取ったら当選。候補が1人になったときも確定。
    if (live.size === 1 || live.get(leader)! * 2 > total) {
      log.push({ standing, eliminated: null, movedTo: null });
      return { winner: leader, winnerParty: partyOf.get(leader)!, rounds, exhausted, log };
    }

    // 最下位を落とす。同数は党派名・氏名の順で決定的にする。
    let loser = "";
    for (const [name, v] of live) {
      if (loser === "") {
        loser = name;
        continue;
      }
      const lv = live.get(loser)!;
      if (
        v < lv ||
        (v === lv && partyOf.get(name)! < partyOf.get(loser)!) ||
        (v === lv && partyOf.get(name)! === partyOf.get(loser)! && name < loser)
      ) {
        loser = name;
      }
    }

    const moving = live.get(loser)!;
    const loserParty = partyOf.get(loser)!;
    live.delete(loser);

    const order = personas.orderings[loserParty];
    if (!order) {
      // 選好順序を持たない党派（諸派など）は移譲先が分からないので死票
      exhausted += moving;
      log.push({ standing, eliminated: { name: loser, party: loserParty, votes: moving }, movedTo: null });
      continue;
    }

    // 順序の上から、まだ残っている候補のいる党派を探す
    let targets: string[] = [];
    for (const party of order) {
      targets = [...live.keys()].filter((n) => partyOf.get(n) === party);
      if (targets.length > 0) break;
    }
    if (targets.length === 0) {
      exhausted += moving;
      log.push({ standing, eliminated: { name: loser, party: loserParty, votes: moving }, movedTo: null });
      continue;
    }
    log.push({
      standing,
      eliminated: { name: loser, party: loserParty, votes: moving },
      movedTo: partyOf.get(targets[0])!,
    });
    // 同じ党派の候補が複数残っていれば現在の得票で按分する
    let base = 0;
    for (const n of targets) base += live.get(n)!;
    for (const n of targets) {
      const share = base > 0 ? live.get(n)! / base : 1 / targets.length;
      live.set(n, live.get(n)! + moving * share);
    }
  }
}

/**
 * 第1選好だけで当選が確定している選挙区か。
 *
 * 過半数を取っている候補がいれば、移譲がどう転んでも結果は動かない。ペルソナの
 * 置き方に左右されない部分なので、結果を読むときの土台になる。
 */
export function isSecuredOnFirstPreferences(district: District): boolean {
  let total = 0;
  let top = 0;
  for (const c of district.candidates) {
    total += c.votes;
    if (c.votes > top) top = c.votes;
  }
  return top * 2 > total;
}

/** 全選挙区の小選挙区の当落を、指定した投票方式で決める。 */
export function solveSmd(
  districts: District[],
  personas: Personas | null,
  voting: "plurality" | "rcv"
): SmdOutcome {
  const winners: Record<string, string> = {};
  const seatsByParty: Record<string, number> = {};
  const byBlock: Record<string, Record<string, number>> = {};
  const flipped: SmdOutcome["flipped"] = [];
  const detail: SmdOutcome["districts"] = [];
  const winnerVotes: Record<string, number> = {};
  let exhausted = 0;
  let secured = 0;

  // 選好順序を持たない党派。その候補が落ちても票の行き先が分からず死票になり、
  // 他党の順序にも載っていないので票が回ってこない。調査は第51回の政党構成で
  // 行われているため、それ以前の回では大政党がここに入りうる。
  const unordered = new Map<string, number>();
  let allVotes = 0;
  if (voting === "rcv" && personas) {
    for (const d of districts) {
      for (const c of d.candidates) {
        allVotes += c.votes;
        if (!(c.party in personas.orderings)) {
          unordered.set(c.party, (unordered.get(c.party) ?? 0) + c.votes);
        }
      }
    }
  }

  for (const d of districts) {
    const isSecured = isSecuredOnFirstPreferences(d);
    if (isSecured) secured += 1;

    let winner = d.winner;
    let winnerParty = d.winnerParty;
    if (voting === "rcv") {
      if (!personas) throw new Error("優先順位付投票にはペルソナの選好順序が要る");
      const r = irvDistrict(d, personas);
      exhausted += r.exhausted;
      winner = r.winner;
      winnerParty = r.winnerParty;
      detail.push({
        district: d.id,
        winner,
        winnerParty,
        pluralityWinner: d.winner,
        pluralityWinnerParty: d.winnerParty,
        secured: isSecured,
        log: r.log,
      });
      if (winner !== d.winner) {
        flipped.push({
          district: d.id,
          fromParty: d.winnerParty,
          fromName: d.winner,
          toParty: winnerParty,
          toName: winner,
          rounds: r.rounds,
        });
      }
    }

    winners[d.id] = winner;
    // 惜敗率の分母。当選者が変われば分母も変わるので、その人の第1選好の得票を持つ。
    // これを持たずに元の最多得票で割ると、単記で勝っていた人が必ず 100% になり、
    // 比例名簿の同一順位で先頭に立ってしまう。
    winnerVotes[d.id] = d.candidates.find((c) => c.name === winner)?.votes ?? d.topVotes;
    seatsByParty[winnerParty] = (seatsByParty[winnerParty] ?? 0) + 1;
    byBlock[d.block] = byBlock[d.block] ?? {};
    byBlock[d.block][winnerParty] = (byBlock[d.block][winnerParty] ?? 0) + 1;
  }

  return {
    winners,
    seatsByParty,
    byBlock,
    flipped,
    exhausted,
    securedOnFirstPreferences: secured,
    districts: detail,
    winnerVotes,
    unorderedParties: [...unordered.entries()]
      .map(([party, votes]) => ({
        party,
        votes,
        share: allVotes > 0 ? (votes / allVotes) * 100 : 0,
      }))
      .sort((a, b) => b.votes - a.votes),
  };
}
