/**
 * 与党の議席占有率。
 *
 * 与党の顔ぶれは選挙のたびに変わるので、選挙回ごとに既定値を持ち、画面から
 * 選び直せるようにしている。
 */

/**
 * 各選挙回の与党（選挙時点の連立の構成）。
 *
 * 第47〜50回は自民党・公明党の連立。第51回は自民党・日本維新の会。
 * 党名は `pr_party_blocks` などに現れる表記に合わせる。
 */
export const RULING_DEFAULT: Record<string, string[]> = {
  "r08-02-08": ["自由民主党", "日本維新の会"],
  "r06-10-27": ["自由民主党", "公明党"],
  "r03-10-31": ["自由民主党", "公明党"],
  "h29-10-22": ["自由民主党", "公明党"],
  "h26-12-14": ["自由民主党", "公明党"],
};

export type Threshold = {
  id: "majority" | "stable" | "absolute";
  label: string;
  /** 占有率のライン（％） */
  ratio: number;
  /** その議席数。定数が既知の構成と違う場合は目安。 */
  seats: number;
  exact: boolean;
  hint: string;
};

/**
 * 安定多数・絶対安定多数の議席数は、常任委員会の数と各委員会の委員数から決まる。
 *
 * 465議席なら安定多数244・絶対安定多数261、475議席なら249・266。
 * 定数を変える案では委員会の委員数をどうするかが示されていないため、正確な
 * 議席数は制度上決まらない。その場合は比率から換算した目安として示し、画面にも
 * 目安である旨を出す。
 */
const KNOWN: Record<number, { stable: number; absolute: number }> = {
  465: { stable: 244, absolute: 261 },
  475: { stable: 249, absolute: 266 },
};

/** 議員数（欠員を除いた実数）に対する多数派のライン。 */
export function thresholds(members: number): Threshold[] {
  const known = KNOWN[members];
  const majority = Math.floor(members / 2) + 1;

  const stable = known ? known.stable : Math.ceil((244 / 465) * members);
  const absolute = known ? known.absolute : Math.ceil((261 / 465) * members);

  return [
    {
      id: "majority",
      label: "過半数",
      ratio: (majority / members) * 100,
      seats: majority,
      exact: true,
      hint: "議案を可決できる",
    },
    {
      id: "stable",
      label: "安定多数",
      ratio: (stable / members) * 100,
      seats: stable,
      exact: Boolean(known),
      hint: "全ての常任委員会で委員長を出し、委員が与野党同数になる",
    },
    {
      id: "absolute",
      label: "絶対安定多数",
      ratio: (absolute / members) * 100,
      seats: absolute,
      exact: Boolean(known),
      hint: "全ての常任委員会で委員長を出し、かつ委員の過半数を占める",
    },
  ];
}

export type RulingSummary = {
  seats: number;
  /** 欠員を除いた議員数 */
  members: number;
  ratio: number;
  thresholds: Threshold[];
  /** 満たしているラインのうち、いちばん厳しいもの */
  reached: Threshold | null;
};

export function summarize(
  seatsByParty: Record<string, number>,
  ruling: string[],
  members: number
): RulingSummary {
  const seats = ruling.reduce((sum, p) => sum + (seatsByParty[p] ?? 0), 0);
  const lines = thresholds(members);
  const reached = [...lines].reverse().find((t) => seats >= t.seats) ?? null;
  return {
    seats,
    members,
    ratio: members === 0 ? 0 : (seats / members) * 100,
    thresholds: lines,
    reached,
  };
}
