import type { Metadata } from "next";

import { PRESETS } from "@/sim/presets";

export const metadata: Metadata = {
  title: "各党の案 — 衆院選 選挙制度改革シミュレータ",
  description: "シミュレータが扱っている各党の衆議院選挙制度改革案と、その出典。",
};

export default function Proposals() {
  return (
    <div className="space-y-8">
      <section>
        <h1 className="text-[22px] font-bold">各党の案</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          シミュレータが計算に反映しているのは「議席の決め方」に関わる部分だけです。
          被選挙権年齢や供託金額、インターネット投票のように、同じ投票結果からは議席を
          計算しようのない項目は、下に文章として書き出したうえで計算には入れていません。
        </p>
      </section>

      {PRESETS.map((p) => (
        <section key={p.id} className="card p-4">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h2 className="text-[16px] font-semibold">{p.name}</h2>
            {p.party !== "—" && (
              <span className="text-[12px]" style={{ color: "var(--ink-muted)" }}>
                {p.party}
              </span>
            )}
            {p.kind === "reference" && p.id !== "baseline" && (
              <span
                className="rounded-full px-2 py-0.5 text-[11px]"
                style={{ border: "1px solid var(--hairline)", color: "var(--ink-muted)" }}
              >
                政党の案ではなく比較用の参考ケース
              </span>
            )}
          </div>

          <p className="mt-2 max-w-3xl text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
            {p.summary}
          </p>

          <dl className="mt-3 grid gap-x-6 gap-y-1 text-[12px] sm:grid-cols-2">
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>小選挙区と比例の連動</dt>
              <dd className="font-medium">
                {p.params.tierLinkage === "parallel"
                  ? "並立制（現行）"
                  : p.params.tierLinkage === "renyo"
                    ? "連用制"
                    : `併用制（超過議席は${p.params.heiyoOverhang === "truncate" ? "総定数固定" : "定数増を認容"}）`}
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>比例の配分方式</dt>
              <dd className="font-medium">
                {p.params.divisorMethod === "dhondt"
                  ? "ドント式（÷1,2,3…）"
                  : p.params.divisorMethod === "sainteLague"
                    ? "サンラグ式（÷1,3,5…）"
                    : `修正サンラグ式（÷${(p.params.firstDivisorTenths / 10).toFixed(1)},3,5…）`}
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>比例の定数</dt>
              <dd className="tnum font-medium">
                {p.params.prSeatDelta === 0 ? "現行どおり" : `${p.params.prSeatDelta}`}
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>比例復活の最低得票率</dt>
              <dd className="tnum font-medium">
                {p.params.dualMinVoteShare[0]}/{p.params.dualMinVoteShare[1]}
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>惜敗率の下限</dt>
              <dd className="tnum font-medium">
                {p.params.dualMinSekihaiRate === null ? "なし" : `${p.params.dualMinSekihaiRate}%`}
              </dd>
            </div>
            <div className="flex justify-between gap-3 py-1" style={{ borderTop: "1px solid var(--grid)" }}>
              <dt style={{ color: "var(--ink-muted)" }}>名簿が足りないとき</dt>
              <dd className="font-medium">
                {p.params.listExhaustion === "vacant" ? "欠員にする" : "他党に回す"}
              </dd>
            </div>
          </dl>

          {p.notes.length > 0 && (
            <ul className="mt-3 max-w-3xl space-y-1.5 text-[12px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
              {p.notes.map((n) => (
                <li key={n}>※ {n}</li>
              ))}
            </ul>
          )}

          {p.sources.length > 0 && (
            <div className="mt-3 text-[12px]">
              <span style={{ color: "var(--ink-muted)" }}>出典: </span>
              {p.sources.map((s, i) => (
                <span key={s.url}>
                  {i > 0 && <span style={{ color: "var(--ink-muted)" }}> ／ </span>}
                  <a href={s.url}>{s.label}</a>
                </span>
              ))}
            </div>
          )}
        </section>
      ))}

      <section className="card p-4">
        <h2 className="text-[16px] font-semibold">扱っていない案</h2>
        <div className="mt-2 max-w-3xl space-y-3 text-[13px] leading-relaxed" style={{ color: "var(--ink-2)" }}>
          <p>
            <strong style={{ color: "var(--ink)" }}>国民民主党</strong>が2026年7月1日に公表した
            「参議院議員選挙の今後の選挙制度改革について」は、その表題のとおり
            <strong style={{ color: "var(--ink)" }}>参議院</strong>の制度に関する案です。
            合区の解消、憲法改正による「広域の地方公共団体」の位置づけ、参議院の定数248の維持などを
            扱っており、衆議院の議席配分方式には触れていません。このシミュレータは衆議院を対象と
            しているため、比較の対象に入れていません。衆議院向けの案が示された時点で追加します。
          </p>
          <p>
            <strong style={{ color: "var(--ink)" }}>チームみらいの抜本改革案に含まれる優先順位付投票（RCV）</strong>
            は、有権者が候補者にどう順位をつけたかというデータがなければ計算できません。
            投票用紙に記載されるのは第1希望のみで、第2希望以降の情報はどこにも存在しないため、
            実際の投票結果から機械的に再計算する方法がありません。仮定を置けば数字は出せますが、
            それは投票結果ではなく仮定が生む数字なので、このシミュレータでは扱いません。
          </p>
        </div>
      </section>
    </div>
  );
}
