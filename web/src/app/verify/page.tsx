"use client";

import { useEffect, useState } from "react";

import { simulate } from "@/sim/engine";
import { BASELINE_PARAMS } from "@/sim/presets";
import type { ElectionData } from "@/sim/types";

type IndexEntry = { id: string; ordinal: number; date: string; sourceUrl: string };

type Check = {
  ordinal: number;
  date: string;
  sourceUrl: string;
  blocks: number;
  seatRows: number;
  winners: number;
  mismatches: string[];
};

/**
 * 現行制度のパラメータで再計算した結果が、実際の選挙結果と一致するかを
 * その場で確かめる。読み込んだデータに対してブラウザ内で計算しているので、
 * 表示されている数字はいま実際に走った検証の結果。
 */
function verify(data: ElectionData): Check {
  const result = simulate(data, BASELINE_PARAMS);
  const mismatches: string[] = [];
  let seatRows = 0;
  let winners = 0;

  for (const block of data.blocks) {
    const got = result.blocks.find((b) => b.block === block.block)!;

    for (const p of block.parties) {
      seatRows += 1;
      const calc = got.seatsByParty[p.party] ?? 0;
      if (calc !== p.actualSeats) {
        mismatches.push(`${block.block}/${p.party}: 再計算 ${calc} ≠ 実際 ${p.actualSeats}`);
      }
    }

    const actual = block.parties
      .flatMap((p) => p.list.filter((e) => e.actualElected).map((e) => e.name))
      .sort();
    const calc = Object.values(got.winners).flat().sort();
    winners += actual.length;
    if (actual.join("|") !== calc.join("|")) {
      mismatches.push(`${block.block}: 比例当選者の顔ぶれが一致しない`);
    }
  }

  const prTotal = Object.values(result.prSeatsByParty).reduce((a, b) => a + b, 0);
  if (prTotal !== data.meta.pr_seats) {
    mismatches.push(`比例議席の合計: ${prTotal} ≠ ${data.meta.pr_seats}`);
  }

  return {
    ordinal: data.meta.ordinal,
    date: data.meta.election_date,
    sourceUrl: data.meta.source_url,
    blocks: data.blocks.length,
    seatRows,
    winners,
    mismatches,
  };
}

const LIMITS: { title: string; body: string }[] = [
  {
    title: "投票行動は制度によって変わる",
    body:
      "これは「同じ票が投じられたら」という仮定の下での再計算です。制度が変われば、" +
      "有権者の投票先も、政党の候補者擁立や選挙協力も変わります。実際にその制度で" +
      "選挙をした場合にこの議席になる、という予測ではありません。",
  },
  {
    title: "優先順位付投票（RCV）の議席数は仮定が生む数字",
    body:
      "有権者が候補者にどう順位をつけたかというデータは存在しません。投票用紙に残るのは" +
      "第1希望だけです。RCVの試算では、「絶対投票したくない政党」を尋ねた調査の拒否率から、" +
      "有権者の層と選好順序を組み立てて代用しています。実際の投票結果からの機械的な再計算ではないので、他の案と同じ重みで" +
      "読まないでください。ただし第1選好で過半数を取った候補は移譲がどう転んでも当選が" +
      "動かないため、その議席数（第51回では289中156）は仮定によらず確定しており、画面に" +
      "併記しています。",
  },
  {
    title: "RCVの拒否率は第51回の政党構成で調べられている",
    body:
      "元にした調査は第51回（2026年）に行われたものです。それ以前の選挙回には、調査に" +
      "出てこない政党（民主党・維新の党・希望の党など）が出てきます。該当する党の票は" +
      "移譲されず死票になり、他党からも票が回ってこないため、結果が大きく歪みます。" +
      "RCVを選んだときは、その選挙回に拒否率の分からない政党があれば画面に名前と得票を出します。拒否率そのものも画面から動かせます。",
  },
  {
    title: "定数削減後のブロック配分は案に書かれていない",
    body:
      "比例定数を減らしたあと、残りの議席を11ブロックにどう配り直すかは案に示されていません。" +
      "ここでは各ブロックの選挙人数を用いたアダムズ方式で配分しています。" +
      "法定のアダムズ方式は国勢調査人口を使うため、公式の再配分とは結果が異なる可能性があります。",
  },
  {
    title: "惜敗率の下限は確定値ではない",
    body:
      "自民党案の惜敗率下限は座長試案が「30%や50%」を例示したものです。" +
      "既定を30%としていますが、シミュレータ側のスライダーで変更できます。",
  },
  {
    title: "商が同値になる場合がある",
    body:
      "議席の境界で商がちょうど同じになると、実際の選挙ではくじ引きになります。" +
      "このシミュレータは得票数の多い党、なお同じなら党派名の順という決め方をしており、" +
      "その場合は結果の画面に注意書きを出します。",
  },
  {
    title: "政党は選挙回をまたいで同じではない",
    body:
      "民主党・民進党・立憲民主党・希望の党のように、政党は分裂・合流・改称を繰り返しています。" +
      "第51回では立憲民主党と公明党が姿を消し、中道改革連合が現れています。" +
      "党名を手がかりに複数の選挙回を横に並べて比べることはしていません。",
  },
  {
    title: "按分票のため得票の合計はわずかに揃わない",
    body:
      "同姓同名の候補者がいる場合、票は小数第3位まで按分され、切り捨てが生じます。" +
      "そのため候補者の得票を合計すると、有効投票総数を1票弱下回ることがあります。" +
      "第51回では289選挙区のうち281区が完全一致し、残り8区の差は0.001〜0.020票でした。",
  },
  {
    title: "出典のPDF自体に矛盾がある箇所がある",
    body:
      "第48回（2017年）の沖縄県は、表(6)と表(13)がともに636,134.995票で一致する一方、" +
      "表(8)の有効投票数は636,030票と105票少なくなっています。" +
      "どちらが正しいかを決める根拠がないため、理由をつけて記録するにとどめています。",
  },
];

export default function Verify() {
  const [checks, setChecks] = useState<Check[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/data/index.json")
      .then((r) => r.json())
      .then(async (idx: IndexEntry[]) => {
        const loaded = await Promise.all(
          idx.map((e) => fetch(`/data/${e.id}.sim.json`).then((r) => r.json() as Promise<ElectionData>))
        );
        setChecks(loaded.map(verify));
      })
      .catch(() => setError("データを読み込めませんでした"));
  }, []);

  const allOk = checks?.every((c) => c.mismatches.length === 0) ?? false;

  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-bold">検証と限界</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          試算の結果は、入力データの正しさと計算の正しさに完全に依存します。
          そこでこのシミュレータは、まず
          <strong style={{ color: "var(--ink)" }}>
            現行制度のパラメータで計算し直したときに、実際の選挙結果と1議席・1人の狂いもなく
            一致すること
          </strong>
          を条件にしています。下の表は、いまあなたのブラウザでその計算を実行した結果です。
        </p>
      </section>

      <section className="card p-4">
        <h2 className="text-[15px] font-semibold">現行制度での再現</h2>
        {error && (
          <p className="mt-2 text-[13px]" style={{ color: "var(--critical)" }}>
            {error}
          </p>
        )}
        {!checks && !error && (
          <p className="mt-2 text-[13px]" style={{ color: "var(--ink-muted)" }}>
            計算中…
          </p>
        )}
        {checks && (
          <>
            <div className="mt-3 scroll-x">
              <table className="w-full min-w-[560px] border-collapse text-[13px]">
                <thead>
                  <tr style={{ color: "var(--ink-muted)" }} className="text-left">
                    <th className="py-2 pr-3 font-medium">選挙回</th>
                    <th className="py-2 pr-3 text-right font-medium">ブロック</th>
                    <th className="py-2 pr-3 text-right font-medium">照合した議席数</th>
                    <th className="py-2 pr-3 text-right font-medium">照合した当選者</th>
                    <th className="py-2 font-medium">結果</th>
                  </tr>
                </thead>
                <tbody>
                  {checks.map((c) => (
                    <tr key={c.ordinal} style={{ borderTop: "1px solid var(--grid)" }}>
                      <td className="py-2 pr-3">
                        <a href={c.sourceUrl}>第{c.ordinal}回</a>
                        <span className="ml-2 text-[12px]" style={{ color: "var(--ink-muted)" }}>
                          {c.date}
                        </span>
                      </td>
                      <td className="tnum py-2 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {c.blocks}
                      </td>
                      <td className="tnum py-2 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {c.seatRows}
                      </td>
                      <td className="tnum py-2 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {c.winners}
                      </td>
                      <td className="py-2">
                        {c.mismatches.length === 0 ? (
                          <span className="font-medium" style={{ color: "#0ca30c" }}>
                            ✓ 完全一致
                          </span>
                        ) : (
                          <span style={{ color: "var(--critical)" }}>
                            ✗ 不一致 {c.mismatches.length} 件: {c.mismatches[0]}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[12px]" style={{ color: "var(--ink-2)" }}>
              {allOk
                ? "全ての選挙回で、ブロック×党派の議席数と比例当選者の顔ぶれが実際の結果と一致しました。"
                : "一致しない項目があります。この状態の試算は信用できません。"}
            </p>
          </>
        )}
      </section>

      <section className="card p-4">
        <h2 className="text-[15px] font-semibold">この試算の限界</h2>
        <div className="mt-1 divide-y" style={{ borderColor: "var(--grid)" }}>
          {LIMITS.map((l) => (
            <div key={l.title} className="py-3">
              <div className="text-[13px] font-medium">{l.title}</div>
              <p className="mt-1 max-w-3xl text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
                {l.body}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="card p-4">
        <h2 className="text-[15px] font-semibold">データの作り方</h2>
        <div className="mt-2 max-w-3xl space-y-3 text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          <p>
            総務省が公表する「衆議院議員総選挙・最高裁判所裁判官国民審査結果調」のPDFから、
            候補者別得票・比例名簿・ドント除数表などを抽出しています。抽出したデータには
            35項目の機械検証をかけており、たとえば「候補者の得票の合計＝供託物没収点×10」を
            全289選挙区で、「惜敗率＝得票÷その選挙区の最多得票×100」を全重複立候補者で
            確かめています。検証に1件でも失敗があればデータは出力されません。
          </p>
          <p>
            このシミュレータが使う比例代表の計算は、上記の検証で
            「ドント式の独立再計算が印字されている議席配分・獲得順と一致する」ことを
            確かめたコードを一般化したものです。
          </p>
          <p>
            出典PDFはリポジトリに同梱せず、URLとsha256だけを記録しています。
          </p>
        </div>
      </section>
    </div>
  );
}
