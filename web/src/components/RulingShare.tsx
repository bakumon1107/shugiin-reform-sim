"use client";

import { summarize } from "@/lib/ruling";
import { Delta } from "./Delta";

/**
 * 与党の議席占有率。
 *
 * 占有率（％）を主役にする。案によって定数が変わるので、議席数をそのまま並べても
 * 比べられないため。多数派のラインも比率で引く。
 */
function ShareBar({
  ratio,
  lines,
  label,
  muted = false,
}: {
  ratio: number;
  lines: { id: string; label: string; ratio: number }[];
  label: string;
  muted?: boolean;
}) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-[12px]">
        <span style={{ color: "var(--ink-muted)" }}>{label}</span>
        <span className="tnum font-semibold" style={{ color: muted ? "var(--ink-2)" : "var(--ink)" }}>
          {ratio.toFixed(1)}%
        </span>
      </div>
      <div className="relative h-6 rounded" style={{ background: "var(--neutral)" }}>
        <div
          className="absolute inset-y-0 left-0"
          style={{
            width: `${Math.min(ratio, 100)}%`,
            background: muted ? "var(--bar-250)" : "var(--bar-450)",
            borderRadius: "4px 0 0 4px",
          }}
        />
        {lines.map((t) => (
          <div
            key={t.id}
            className="absolute inset-y-0 w-0.5"
            style={{ left: `${t.ratio}%`, background: "var(--ink)", opacity: 0.55 }}
            title={`${t.label} ${t.ratio.toFixed(1)}%`}
          />
        ))}
      </div>
    </div>
  );
}

export function RulingShare({
  baselineSeats,
  proposalSeats,
  baselineMembers,
  proposalMembers,
  ruling,
  parties,
  proposalName,
  onChangeRuling,
}: {
  baselineSeats: Record<string, number>;
  proposalSeats: Record<string, number>;
  baselineMembers: number;
  proposalMembers: number;
  ruling: string[];
  /** その選挙回に議席を持つ党派 */
  parties: string[];
  proposalName: string;
  onChangeRuling: (next: string[]) => void;
}) {
  const base = summarize(baselineSeats, ruling, baselineMembers);
  const prop = summarize(proposalSeats, ruling, proposalMembers);

  const toggle = (party: string) => {
    onChangeRuling(
      ruling.includes(party) ? ruling.filter((p) => p !== party) : [...ruling, party]
    );
  };

  return (
    <section className="card p-4">
      <h2 className="text-[15px] font-semibold">与党の議席占有率</h2>
      <p className="mt-1 text-[12px]" style={{ color: "var(--ink-muted)" }}>
        与党の顔ぶれは選挙のたびに変わります。既定値は選挙時点の連立で、下から選び直せます。
      </p>

      {/* --- 与党の選択 --- */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {parties.map((party) => {
          const on = ruling.includes(party);
          return (
            <button
              key={party}
              type="button"
              onClick={() => toggle(party)}
              aria-pressed={on}
              className="rounded-full px-3 py-1.5 text-[12px]"
              style={{
                border: `1px solid ${on ? "var(--bar-450)" : "var(--hairline)"}`,
                background: on ? "var(--bar-450)" : "transparent",
                color: on ? "#ffffff" : "var(--ink-2)",
              }}
            >
              {on ? "✓ " : ""}
              {party}
            </button>
          );
        })}
      </div>

      {ruling.length === 0 ? (
        <p className="mt-4 text-[13px]" style={{ color: "var(--ink-muted)" }}>
          与党を1つ以上選んでください。
        </p>
      ) : (
        <>
          <div className="mt-4 space-y-3">
            <ShareBar
              label={`現行制度　${base.seats}／${base.members}議席`}
              ratio={base.ratio}
              lines={base.thresholds}
              muted
            />
            <ShareBar
              label={`${proposalName}　${prop.seats}／${prop.members}議席`}
              ratio={prop.ratio}
              lines={prop.thresholds}
            />
          </div>

          <div className="mt-3 flex flex-wrap items-baseline gap-x-6 gap-y-1 text-[13px]">
            <span>
              占有率{" "}
              <span className="tnum font-semibold">{prop.ratio.toFixed(1)}%</span>{" "}
              <Delta value={Number((prop.ratio - base.ratio).toFixed(1))} />
            </span>
            <span style={{ color: "var(--ink-2)" }}>
              議席 <span className="tnum">{base.seats}</span> →{" "}
              <span className="tnum font-semibold" style={{ color: "var(--ink)" }}>
                {prop.seats}
              </span>
            </span>
            <span style={{ color: "var(--ink-2)" }}>
              到達ライン{" "}
              <span style={{ color: "var(--ink)" }}>{base.reached?.label ?? "過半数に届かず"}</span>
              {" → "}
              <span className="font-semibold" style={{ color: "var(--ink)" }}>
                {prop.reached?.label ?? "過半数に届かず"}
              </span>
            </span>
          </div>

          {/* --- ラインの説明 --- */}
          <div className="mt-3 scroll-x">
            <table className="w-full min-w-[520px] border-collapse text-[12px]">
              <thead>
                <tr style={{ color: "var(--ink-muted)" }} className="text-left">
                  <th className="py-1.5 pr-3 font-medium">ライン</th>
                  <th className="py-1.5 pr-3 text-right font-medium">現行制度</th>
                  <th className="py-1.5 pr-3 text-right font-medium">{proposalName}</th>
                  <th className="py-1.5 font-medium">意味</th>
                </tr>
              </thead>
              <tbody>
                {base.thresholds.map((t, i) => {
                  const p = prop.thresholds[i];
                  return (
                    <tr key={t.id} style={{ borderTop: "1px solid var(--grid)" }}>
                      <td className="py-1.5 pr-3">
                        {t.label}
                        {!p.exact && (
                          <span className="ml-1" style={{ color: "var(--warning)" }} title="目安">
                            ※
                          </span>
                        )}
                      </td>
                      <td className="tnum py-1.5 pr-3 text-right" style={{ color: "var(--ink-2)" }}>
                        {t.seats}
                        {base.seats >= t.seats && (
                          <span className="ml-1" style={{ color: "#0ca30c" }}>
                            ✓
                          </span>
                        )}
                      </td>
                      <td className="tnum py-1.5 pr-3 text-right font-semibold">
                        {p.seats}
                        {prop.seats >= p.seats && (
                          <span className="ml-1" style={{ color: "#0ca30c" }}>
                            ✓
                          </span>
                        )}
                      </td>
                      <td className="py-1.5" style={{ color: "var(--ink-muted)" }}>
                        {t.hint}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {prop.thresholds.some((t) => !t.exact) && (
            <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
              ※ 安定多数・絶対安定多数の議席数は、常任委員会の数と各委員会の委員数から決まります。
              定数を変える案では委員会の委員数をどうするかが示されていないため、正確な議席数は
              制度上決まりません。ここでは現行465議席での比率から換算した目安を示しています。
            </p>
          )}
          <p className="mt-2 text-[11px]" style={{ color: "var(--ink-muted)" }}>
            分母は欠員を除いた議員数です。
            {proposalMembers !== baselineMembers &&
              `（${proposalName}は法定定数のうち欠員を差し引いて ${proposalMembers} 人）`}
          </p>
          <p className="mt-1 text-[11px]" style={{ color: "var(--ink-muted)" }}>
            党派は<strong>立候補の届出時点</strong>のものです。選挙後の追加公認や、無所属で
            当選した人の会派入りは反映されていません。たとえば第49回の自由民主党は、
            報道では追加公認を含めて261議席とされますが、届出の党派では259議席です。
            会派としての規模で見たい場合は、上のボタンで無所属を与党に加えてください。
          </p>
        </>
      )}
    </section>
  );
}
