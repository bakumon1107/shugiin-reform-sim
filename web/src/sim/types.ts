/** `src/export_sim.py` が書き出す `web/public/data/<id>.sim.json` の型。 */

export type ListEntry = {
  rank: number;
  name: string;
  dual: boolean;
  /** 実際の選挙で比例当選したか（検証用） */
  actualElected: boolean;
  actualElectedOrder: number | null;
  /** 以下は重複立候補者のみ。単独の名簿登載者は null。 */
  districtId: string | null;
  smdWon: boolean;
  smdVotes: number | null;
  districtValidVotes: number | null;
  districtTopVotes: number | null;
};

export type BlockParty = {
  party: string;
  /** 得票数 × 1000（按分票が小数第3位まであるため整数で持つ） */
  votes: number;
  actualSeats: number;
  list: ListEntry[];
};

export type Block = {
  block: string;
  prefectures: string[];
  seats: number;
  /** 選挙人数。定数再配分の人口比の代わりに使う近似値。 */
  electors: number;
  parties: BlockParty[];
};

export type District = {
  id: string;
  pref: string;
  no: number;
  block: string;
  validVotes: number;
  topVotes: number;
  winner: string;
  winnerParty: string;
};

export type ElectionData = {
  meta: {
    election_id: string;
    ordinal: number;
    election_date: string;
    source_url: string;
    source_sha256: string;
    smd_seats: number;
    pr_seats: number;
    total_seats: number;
  };
  voteScale: number;
  smd: {
    seatsByParty: Record<string, number>;
    /** ブロック別・党派別の小選挙区当選者数。連用制・併用制で使う。 */
    byBlock: Record<string, Record<string, number>>;
    districts: District[];
  };
  blocks: Block[];
};

// ---------------------------------------------------------------------------
// 制度パラメータ
// ---------------------------------------------------------------------------

/**
 * 比例代表の議席配分方式。
 *
 * - `dhondt` … ÷1, 2, 3, 4 …（現行）
 * - `sainteLague` … ÷1, 3, 5, 7 …
 * - `modifiedSainteLague` … 第1除数だけを大きくした ÷1.4, 3, 5, 7 …
 */
export type DivisorMethod = "dhondt" | "sainteLague" | "modifiedSainteLague";

/** 名簿が尽きたときの扱い。`reallocate` は現行、`vacant` は自民案。 */
export type ListExhaustion = "reallocate" | "vacant";

/**
 * 小選挙区と比例代表の連動のさせ方。
 *
 * - `parallel` … 並立制（現行）。互いに独立に決まる。
 * - `renyo` … 連用制。比例の除数を「その党の小選挙区当選者数 + 1」から始める。
 * - `heiyo` … 併用制。比例得票で総議席を決め、小選挙区当選者をその枠に充てる。
 */
export type TierLinkage = "parallel" | "renyo" | "heiyo";

/**
 * 併用制で超過議席が出たときの扱い。
 *
 * `truncate` は総定数を固定して商の低い方から打ち切る。`expand` は超過分だけ
 * 定数が増えるのを認める（ドイツの旧制度型）。
 *
 * **`truncate` を選ぶと、併用制は連用制と数学的に同一の制度になる。** 比例議席の
 * 候補（各党の除数のうち小選挙区当選者数を超えるもの）から商の高い順に定数分を
 * 取る操作が両者で一致するため。両者が分岐するのは `expand` のときだけ。
 */
export type HeiyoOverhang = "truncate" | "expand";

export type SimParams = {
  divisorMethod: DivisorMethod;
  /**
   * 修正サンラグの第1除数を10倍した整数（14 なら 1.4）。0.1刻みで動かせるように
   * 整数で持つ。`modifiedSainteLague` 以外の方式では使わない。
   */
  firstDivisorTenths: number;
  /** 比例定数の増減。自民案は −45。小選挙区の定数は動かさない。 */
  prSeatDelta: number;
  /**
   * 重複立候補者が比例名簿から当選するのに必要な、小選挙区での最低得票率を
   * `[分子, 分母]` で表す。現行は有効投票総数の 1/10（＝供託物没収点）、自民案は 1/6。
   */
  dualMinVoteShare: [number, number];
  /** 重複立候補者に課す惜敗率の下限（％、整数）。null なら課さない。 */
  dualMinSekihaiRate: number | null;
  listExhaustion: ListExhaustion;
  tierLinkage: TierLinkage;
  heiyoOverhang: HeiyoOverhang;
};

// ---------------------------------------------------------------------------
// 計算結果
// ---------------------------------------------------------------------------

export type SeatAward = {
  party: string;
  /** 比較に使った除数。修正サンラグでは10倍した整数なので、表示前に `divisorScale` で割る。 */
  divisor: number;
  /** false なら名簿不足による欠員（`vacant` のときだけ起こる） */
  filled: boolean;
};

export type BlockResult = {
  block: string;
  seats: number;
  order: SeatAward[];
  vacancies: number;
  seatsByParty: Record<string, number>;
  /** 党派ごとの「当選人になれる名簿登載者数」 */
  capacity: Record<string, number>;
  /** 党派ごとの比例当選者（名簿順） */
  winners: Record<string, string[]>;
};

export type SimResult = {
  blocks: BlockResult[];
  prSeatsByParty: Record<string, number>;
  totalSeatsByParty: Record<string, number>;
  vacancies: number;
  /** 商が同値になり、本来はくじ引きが必要だったブロック */
  tieBlocks: string[];
};
