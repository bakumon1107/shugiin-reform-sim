# OGP画像の作り直し

`public/og.png` は X などに貼ったときに出るカード画像。1200×630。

Next.js の `opengraph-image.tsx` 規約で毎回生成させることもできるが、静的
エクスポートすると拡張子の無い `out/opengraph-image` として出力される。すると
Vercel が Content-Type を判定できず `application/octet-stream` になり、X が
画像として扱わない。さらに `trailingSlash: true` の影響で 308 リダイレクトも
挟まる。そのため**生成済みのPNGを静的ファイルとして置いている**。

デザインを変えるときだけ、次の手順で作り直す。

```bash
cd web
cp tools/og-image.tsx src/app/opengraph-image.tsx   # 一時的にルートに置く
npm run build
cp out/opengraph-image public/og.png                # 生成物を取り出す
rm src/app/opengraph-image.tsx                      # ルートから外す
npm run build                                       # og:image が /og.png を指すことを確認
```

最後のビルド後、`out/index.html` の `og:image` と `twitter:image` がどちらも
`/og.png` を指していることを確認すること。ルートを置いたままにすると、ファイル
規約側が優先されて `og:image` が拡張子の無いURLに戻る。
