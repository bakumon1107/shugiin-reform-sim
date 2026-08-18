/**
 * 各党の選挙制度改革案を、シミュレータのパラメータに落としたもの。
 *
 * ここに書いてあるのは「議席配分の計算に効く部分」だけ。被選挙権年齢や供託金額、
 * インターネット投票のように、同じ投票結果からは議席が計算できない項目は
 * `notes` に文章として残し、計算には反映しない。
 */

import type { SimParams } from "./types";

export type Preset = {
  id: string;
  name: string;
  party: string;
  /**
   * `party` は実際に政党が示している案、`reference` は比較のためにこちらで置いた
   * 参考ケース。どの党の案でもないものを党の案と並べて誤解されないように区別する。
   */
  kind: "party" | "reference";
  /** 議席配分に効く部分の要約 */
  summary: string;
  /** 出典 */
  sources: { label: string; url: string }[];
  params: SimParams;
  /** 計算に反映していない項目と、その理由 */
  notes: string[];
};

export const BASELINE_PARAMS: SimParams = {
  divisorMethod: "dhondt",
  firstDivisorTenths: 14,
  prSeatDelta: 0,
  dualMinVoteShare: [1, 10],
  dualMinSekihaiRate: null,
  listExhaustion: "reallocate",
  tierLinkage: "parallel",
  heiyoOverhang: "truncate",
  smdVoting: "plurality",
};

export const PRESETS: Preset[] = [
  {
    id: "baseline",
    name: "現行制度",
    party: "—",
    kind: "reference",
    summary:
      "小選挙区289・比例176の並立制。比例はドント式。重複立候補者は小選挙区で" +
      "有効投票総数の1/10以上を取れば比例名簿から復活でき、同一順位は惜敗率順。" +
      "名簿が尽きた党の議席は他党に回る。",
    sources: [
      {
        label: "公職選挙法",
        url: "https://laws.e-gov.go.jp/law/325AC1000000100",
      },
    ],
    params: BASELINE_PARAMS,
    notes: [],
  },
  {
    id: "ldp",
    name: "自民党案",
    party: "自由民主党",
    kind: "party",
    summary:
      "①比例の配分をサンラグ式に ②比例復活に必要な小選挙区での最低得票率を1/10から" +
      "1/6へ ③比例復活に惜敗率の下限を追加 ④名簿が不足したら欠員にして他党に回さない " +
      "⑤比例定数を45削減（176→131）。",
    sources: [
      {
        label: "東京新聞: 衆院選の比例配分で浮上した「サンラグ式」",
        url: "https://www.tokyo-np.co.jp/article/509182",
      },
      {
        label: "日本経済新聞: 自民合同会議、衆院定数「比例45削減」法案を了承",
        url: "https://www.nikkei.com/article/DGXZQOUA114780R10C26A6000000/",
      },
      {
        label: "時事: 高市首相、衆院比例45減を指示",
        url: "https://www.jiji.com/jc/article?k=2026060400618&g=pol",
      },
    ],
    params: {
      divisorMethod: "sainteLague",
      firstDivisorTenths: 14,
      prSeatDelta: -45,
      dualMinVoteShare: [1, 6],
      dualMinSekihaiRate: 30,
      listExhaustion: "vacant",
      tierLinkage: "parallel",
      heiyoOverhang: "truncate",
      smdVoting: "plurality",
    },
    notes: [
      "惜敗率の下限は座長試案が「30%や50%」を例示したもので、確定値ではない。既定は30%とし、スライダーで変更できる。",
      "削減後の比例131議席を11ブロックへ配り直す方法は案に書かれていない。ここでは各ブロックの選挙人数を用いたアダムズ方式で配分している。",
    ],
  },
  {
    id: "mirai",
    name: "チームみらい案",
    party: "チームみらい",
    kind: "party",
    summary:
      "比例の配分をドント式からサンラグ式へ。小選挙区比例代表並立制は踏襲し、" +
      "議員定数・ブロック構成・比例復活・重複立候補のルールは変えない。",
    sources: [
      {
        label: "チームみらい: 衆議院選挙制度改革案",
        url: "https://team-mir.ai/artifacts/senkyo/proposal.html",
      },
    ],
    params: {
      divisorMethod: "sainteLague",
      firstDivisorTenths: 14,
      prSeatDelta: 0,
      dualMinVoteShare: [1, 10],
      dualMinSekihaiRate: null,
      listExhaustion: "reallocate",
      tierLinkage: "parallel",
      heiyoOverhang: "truncate",
      smdVoting: "plurality",
    },
    notes: [
      "ここに入っているのは比例のサンラグ式だけで、これは修正案にあたる。抜本改革案にはさらに優先順位付投票（RCV）が含まれるので、上の「選挙区制度」で RCV を選ぶと抜本改革案の組み合わせになる。",
      "ただし RCV の試算は仮想のペルソナに依存する。有権者が候補者にどう順位をつけたかのデータは存在しないため、「絶対投票したくない政党」を尋ねた調査の拒否率から組み立てて代用している（画面から動かせる）。修正案（サンラグのみ）の方は実際の投票結果からの機械的な再計算で、仮定は入っていない。",
    ],
  },
  {
    id: "modified",
    name: "修正サンラグ（参考）",
    party: "—",
    kind: "reference",
    summary:
      "比例の配分を修正サンラグ式（÷1.4, 3, 5, 7…）にする。第1除数だけを大きくして、" +
      "得票の少ない党が1議席目を取る条件を厳しくする方式。純粋なサンラグ式より小政党の" +
      "議席が出にくく、ドント式ほど大政党に寄らない中間にあたる。",
    sources: [],
    params: {
      divisorMethod: "modifiedSainteLague",
      firstDivisorTenths: 14,
      prSeatDelta: 0,
      dualMinVoteShare: [1, 10],
      dualMinSekihaiRate: null,
      listExhaustion: "reallocate",
      tierLinkage: "parallel",
      heiyoOverhang: "truncate",
      smdVoting: "plurality",
    },
    notes: [
      "これはどの政党の案でもなく、ドント式とサンラグ式を比べるために置いた参考ケース。スウェーデンやノルウェーなどで使われている第1除数が1.4で、既定値もそれに合わせている。",
      "第1除数は0.1刻みで変えられる。1.0にすると純粋なサンラグ式と同じ結果になり、大きくするほどドント式の側に寄る。",
    ],
  },
  {
    id: "renyo",
    name: "連用制",
    party: "—",
    kind: "reference",
    summary:
      "小選挙区の結果はそのままに、比例代表の配分で各党の除数を「1」ではなく" +
      "「その党の小選挙区当選者数 + 1」から始める。小選挙区で勝った党ほど比例が" +
      "回りにくくなり、全体として比例代表に近い議席配分になる。総定数は変わらない。",
    sources: [],
    params: { ...BASELINE_PARAMS, tierLinkage: "renyo" },
    notes: [
      "この制度では比例代表の票が議席を決める主役になるため、大政党が系列の別政党に比例票を回す「ダミー政党」の誘因が非常に強くなる。1990年代の連用制論議でも最大の批判点だった。試算は投票行動が変わらないという前提での機械的な再計算なので、この点はとくに割り引いて見る必要がある。",
    ],
  },
  {
    id: "heiyo",
    name: "併用制",
    party: "—",
    kind: "reference",
    summary:
      "比例代表の得票で各党の総議席を決め、小選挙区の当選者をまずその枠に充てて、" +
      "残りを比例名簿から埋める（ドイツ型）。小選挙区で勝ちすぎた党には超過議席が生じる。",
    sources: [],
    params: { ...BASELINE_PARAMS, tierLinkage: "heiyo" },
    notes: [
      "総定数を固定する場合、併用制は連用制と数学的に同一の制度になる。比例議席の候補（各党の除数のうち小選挙区当選者数を超えるもの）から商の高い順に定数分を取る操作が、両者で一致するため。全5選挙回で議席配分が完全に一致することを確かめている。",
      "両者が分かれるのは、超過議席の分だけ定数が増えるのを認めたときだけ。「超過議席」の切り替えで比べられる。",
    ],
  },
];

export function presetById(id: string): Preset {
  const hit = PRESETS.find((p) => p.id === id);
  if (!hit) throw new Error(`未知のプリセット: ${id}`);
  return hit;
}
