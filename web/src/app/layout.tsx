import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

/**
 * OGP画像のURLを絶対URLにするための基準。
 *
 * これが無いと `http://localhost:3000/...` が埋め込まれ、X などのクローラーが
 * 画像を取得できない。公開先が決まったら `NEXT_PUBLIC_SITE_URL` に設定する。
 * Vercel では本番ドメインが `VERCEL_PROJECT_PRODUCTION_URL` に入るのでそれを使う。
 */
function siteUrl(): URL {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return new URL(explicit);
  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (vercel) return new URL(`https://${vercel}`);
  return new URL("http://localhost:3000");
}

export const metadata: Metadata = {
  metadataBase: siteUrl(),
  title: "衆院選 選挙制度改革シミュレータ",
  description:
    "各党の衆議院選挙制度改革案を、実際の選挙結果に当てはめて議席を再計算し比較する。" +
    "総務省の結果調PDFから抽出・検証したデータを使い、現行制度での再計算が実際の結果と" +
    "一致することを確かめたうえで試算している。",
};

const NAV = [
  { href: "/", label: "シミュレータ" },
  { href: "/proposals/", label: "各党の案" },
  { href: "/verify/", label: "検証と限界" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <header
          className="sticky top-0 z-20 border-b backdrop-blur"
          style={{ borderColor: "var(--hairline)", background: "color-mix(in srgb, var(--plane) 88%, transparent)" }}
        >
          <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
            <Link href="/" className="text-[15px] font-bold no-underline" style={{ color: "var(--ink)" }}>
              衆院選 選挙制度改革シミュレータ
            </Link>
            <nav className="flex gap-4 text-[13px]">
              {NAV.map((n) => (
                <Link key={n.href} href={n.href} className="no-underline" style={{ color: "var(--ink-2)" }}>
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>

        <footer
          className="mx-auto max-w-6xl px-4 py-10 text-[12px] leading-relaxed"
          style={{ color: "var(--ink-muted)" }}
        >
          <p>
            出典: 総務省「衆議院議員総選挙・最高裁判所裁判官国民審査結果調」をもとに
            shugiin-reform-sim が作成
          </p>
          <p className="mt-1">
            データは{" "}
            <a href="https://creativecommons.org/licenses/by/4.0/deed.ja">CC BY 4.0</a>、
            コードは MIT。試算の前提と限界は{" "}
            <Link href="/verify/">検証と限界</Link> を参照。
          </p>
        </footer>
      </body>
    </html>
  );
}
