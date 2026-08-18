import { ImageResponse } from "next/og";

/**
 * X などに貼ったときに出るカード画像。
 *
 * タイムラインの中で小さく表示されるので、何のサイトかが一目で分かることだけを
 * 目的にする。図や数字は入れない。配色はサイト本体と揃えている。
 */
// 静的エクスポートするので、ビルド時に1枚だけ生成する
export const dynamic = "force-static";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "衆院選 選挙制度改革シミュレータ";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#f4f2ee",
          padding: "56px 72px",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            flex: 1,
            background: "#ffffff",
            border: "3px solid #a9c7ee",
            borderRadius: 28,
            padding: "48px 64px",
          }}
        >
          {/* 自動で折り返すと語の途中で切れて左寄りに見えるので、意図した位置で改行する */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              fontSize: 84,
              fontWeight: 700,
              color: "#2a78d6",
              letterSpacing: 2,
              lineHeight: 1.25,
            }}
          >
            <div style={{ display: "flex" }}>選挙制度改革</div>
            <div style={{ display: "flex" }}>シミュレータ</div>
          </div>
          <div
            style={{
              display: "flex",
              width: "82%",
              height: 3,
              background: "#2a78d6",
              margin: "28px 0 32px",
            }}
          />
          <div style={{ display: "flex", fontSize: 40, color: "#52514e" }}>
            衆議院議員総選挙
          </div>
        </div>

        <div
          style={{
            display: "flex",
            marginTop: 30,
            fontSize: 30,
            color: "#0b0b0b",
          }}
        >
          各党の改革案を、実際に投じられた票に当てはめて議席を計算し直す
        </div>
      </div>
    ),
    size
  );
}
