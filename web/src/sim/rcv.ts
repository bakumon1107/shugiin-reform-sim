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

import type { District, IrvRound, Layer, Personas, SmdOutcome } from "./types";

/**
 * 拒否率から有権者の層を作る（入れ子モデル）。
 *
 * 拒否率の高い順に政党を並べ、有権者ごとに一様乱数 u を引いて「拒否率が u より高い
 * 政党すべて」を拒否集合とする。こうすると
 *
 *   ・各政党の拒否率（周辺分布）が定義どおり正確に再現される
 *   ・拒否集合が入れ子になるので、「自民は拒否するが保守は拒否しない」のような
 *     整合しない組み合わせが出ない
 *
 * が同時に成り立つ。同率は党名順にして、実行するたびに結果が変わらないようにする。
 */
export function buildLayers(rates: Record<string, number>): Layer[] {
  const order = Object.entries(rates).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const out: Layer[] = [];
  let prev = 100;
  const rejects: string[] = [];
  for (const [party, rate] of order) {
    if (prev - rate > 0) out.push({ rejects: new Set(rejects), weight: (prev - rate) / 100 });
    rejects.push(party);
    prev = rate;
  }
  if (prev > 0) out.push({ rejects: new Set(rejects), weight: prev / 100 });
  return out;
}

/**
 * 拒否率から選好順序を作り直す。
 *
 * 順序は「拒否されていない順」に並べただけのものなので、拒否率が動けば順序も動く。
 * 両方を別々に持つと、拒否率だけ差し替えたときに順序が古いまま残る。ここで必ず
 * 作り直すことで、渡す側がどちらか片方だけを変えても食い違わないようにする。
 *
 * 拒否率を持たない政党（無所属）は、元の順序での位置をそのまま保つ。
 */
export function orderingsFromRates(personas: Personas): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const [voter, stored] of Object.entries(personas.orderings)) {
    const rates = personas.rejectionRates[voter];
    if (!rates) {
      out[voter] = stored;
      continue;
    }
    const ranked = Object.keys(rates)
      .filter((p) => p !== voter)
      .sort((a, b) => rates[a] - rates[b] || a.localeCompare(b));
    const result = [voter, ...ranked];
    for (const p of stored) {
      if (p === voter || p in rates) continue;
      result.splice(stored.indexOf(p), 0, p);
    }
    out[voter] = result;
  }
  return out;
}

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
  const layers = new Map<string, Layer[]>();
  for (const [party, rates] of Object.entries(personas.rejectionRates)) {
    layers.set(party, buildLayers(rates));
  }
  const orderings = orderingsFromRates(personas);
  const partyOf = new Map<string, string>();
  for (const c of district.candidates) partyOf.set(c.name, c.party);

  // 候補 → その候補が抱えている票の内訳（元の党派と層）
  type Held = { src: string; layer: number; votes: number };
  const held = new Map<string, Held[]>();
  for (const c of district.candidates) {
    const ls = layers.get(c.party);
    held.set(
      c.name,
      ls && ls.length > 0
        ? ls.map((l, i) => ({ src: c.party, layer: i, votes: c.votes * l.weight }))
        : [{ src: c.party, layer: 0, votes: c.votes }]
    );
  }

  const sum = (bag: Held[]) => bag.reduce((a, b) => a + b.votes, 0);
  let exhausted = 0;
  let rounds = 0;

  for (;;) {
    rounds += 1;
    const totals = new Map<string, number>();
    for (const [name, bag] of held) totals.set(name, sum(bag));
    let total = 0;
    for (const v of totals.values()) total += v;

    let leader = "";
    for (const [name, v] of totals) {
      if (leader === "" || v > totals.get(leader)! || (v === totals.get(leader)! && name < leader)) {
        leader = name;
      }
    }

    const standing = [...totals.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([name, votes]) => ({
        name,
        party: partyOf.get(name)!,
        votes,
        share: total > 0 ? (votes / total) * 100 : 0,
      }));

    if (held.size === 1 || totals.get(leader)! * 2 > total) {
      log.push({ standing, eliminated: null, movedTo: null });
      return { winner: leader, winnerParty: partyOf.get(leader)!, rounds, exhausted, log };
    }

    // 最下位を落とす。同数は党派名・氏名の順で決定的にする。
    let loser = "";
    for (const [name, v] of totals) {
      if (loser === "") {
        loser = name;
        continue;
      }
      const lv = totals.get(loser)!;
      if (
        v < lv ||
        (v === lv && partyOf.get(name)! < partyOf.get(loser)!) ||
        (v === lv && partyOf.get(name)! === partyOf.get(loser)! && name < loser)
      ) {
        loser = name;
      }
    }

    const bag = held.get(loser)!;
    const movedVotes = sum(bag);
    held.delete(loser);
    const liveParties = new Set([...held.keys()].map((n) => partyOf.get(n)!));
    const movedTo: string[] = [];

    for (const { src, layer, votes } of bag) {
      const ls = layers.get(src);
      if (!ls) {
        if (personas.orderings[src]) {
          // 順序はあるが拒否率が無い（無所属）。手がかりが無いので均等に割る。
          for (const n of held.keys()) {
            held.get(n)!.push({ src, layer: 0, votes: votes / held.size });
          }
        } else {
          exhausted += votes; // 諸派。行き先が分からない。
        }
        continue;
      }

      const rejects = ls[layer].rejects;
      let targets: string[] = [];
      for (const party of orderings[src] ?? []) {
        if (rejects.has(party) || !liveParties.has(party)) continue;
        targets = [...held.keys()].filter((n) => partyOf.get(n) === party);
        break;
      }
      if (targets.length === 0) {
        exhausted += votes;
        continue;
      }
      movedTo.push(partyOf.get(targets[0])!);
      let base = 0;
      for (const n of targets) base += totals.get(n)!;
      for (const n of targets) {
        const share = base > 0 ? totals.get(n)! / base : 1 / targets.length;
        held.get(n)!.push({ src, layer, votes: votes * share });
      }
    }

    log.push({
      standing,
      eliminated: { name: loser, party: partyOf.get(loser)!, votes: movedVotes },
      // 層ごとに行き先が分かれるので、いちばん多く流れた党派を代表として出す
      movedTo: movedTo.length > 0 ? mode(movedTo) : null,
    });
  }
}

/** いちばん多く現れた要素。同数なら先に出てきた方。 */
function mode(xs: string[]): string {
  const count = new Map<string, number>();
  for (const x of xs) count.set(x, (count.get(x) ?? 0) + 1);
  let best = xs[0];
  for (const [x, n] of count) if (n > (count.get(best) ?? 0)) best = x;
  return best;
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
