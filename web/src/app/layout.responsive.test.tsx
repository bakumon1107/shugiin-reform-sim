// @vitest-environment jsdom
/**
 * 狭い画面での崩れ方を、DOMの構造から確かめられる範囲で押さえておく。
 *
 * jsdom はレイアウトを計算しないので「実際に何px溢れるか」は測れない。そのかわり、
 * 横に溢れる原因になる構造上の約束を検査する:
 *
 * - 幅を固定した表は、必ず横スクロールする入れ物（.scroll-x）の中にある
 * - グリッドで段組みしている箇所の子は、縮められる（min-w-0）
 *
 * 実寸での確認は実ブラウザでないとできないので、これは崩れの「原因」を潰すための
 * 検査であって、見た目が正しいことの保証ではない。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import Proposals from "./proposals/page";
import Verify from "./verify/page";

const DATA_DIR = join(__dirname, "..", "..", "public", "data");

beforeEach(() => {
  vi.stubGlobal("fetch", (input: string) => {
    const name = String(input).replace(/^\/data\//, "");
    const body = readFileSync(join(DATA_DIR, name), "utf8");
    return Promise.resolve({ ok: true, json: () => Promise.resolve(JSON.parse(body)) });
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** 祖先をたどって、横スクロールする入れ物に入っているか調べる。 */
function hasScrollableAncestor(el: HTMLElement): boolean {
  for (let node = el.parentElement; node; node = node.parentElement) {
    if (node.classList.contains("scroll-x")) return true;
  }
  return false;
}

/** グリッドの子が縮められるようになっているか。 */
function gridChildrenCanShrink(root: HTMLElement): string[] {
  const bad: string[] = [];
  for (const grid of root.querySelectorAll<HTMLElement>(".grid")) {
    const cls = grid.className;
    // 段組みの列幅を明示している箇所だけを見る（grid-cols-2 などの等分割は対象外）
    if (!cls.includes("grid-cols-[")) continue;
    if (!cls.includes("minmax(0,")) {
      bad.push(`列指定が minmax(0,…) でない: ${cls}`);
    }
    for (const child of Array.from(grid.children) as HTMLElement[]) {
      const isFixed = child.className.includes("w-6") || child.className.includes("w-5");
      if (!isFixed && !child.className.includes("min-w-0")) {
        bad.push(`グリッドの子に min-w-0 がない: ${child.className.slice(0, 60)}`);
      }
    }
  }
  return bad;
}

async function renderHome() {
  render(<Home />);
  await waitFor(() => expect(screen.getByText("議員数の合計")).toBeDefined());
  return document.body;
}

describe("狭い画面で横に溢れない", () => {
  it("シミュレータ: 幅を固定した表がすべて横スクロールの中にある", async () => {
    const body = await renderHome();
    const tables = body.querySelectorAll<HTMLElement>("table");
    expect(tables.length).toBeGreaterThan(0);
    for (const table of tables) {
      if (!table.className.includes("min-w-")) continue;
      expect(hasScrollableAncestor(table), `表がはみ出す: ${table.className}`).toBe(true);
    }
  });

  it("シミュレータ: グリッドの子が縮められる", async () => {
    const body = await renderHome();
    expect(gridChildrenCanShrink(body)).toEqual([]);
  });

  it("ブロック詳細を開いても、中の表が横スクロールの中にある", async () => {
    const body = await renderHome();
    // すべての details を開く
    for (const d of body.querySelectorAll("details")) d.setAttribute("open", "");

    const tables = body.querySelectorAll<HTMLElement>("table");
    const wide = [...tables].filter((t) => t.className.includes("min-w-"));
    // 除数表・名簿の表まで出ていること
    expect(wide.length).toBeGreaterThan(3);
    for (const table of wide) {
      expect(hasScrollableAncestor(table), `表がはみ出す: ${table.className}`).toBe(true);
    }
  });

  it("検証ページ: 幅を固定した表が横スクロールの中にある", async () => {
    render(<Verify />);
    await waitFor(() => expect(screen.getAllByText("✓ 完全一致").length).toBe(5), {
      timeout: 15000,
    });
    for (const table of document.body.querySelectorAll<HTMLElement>("table")) {
      if (!table.className.includes("min-w-")) continue;
      expect(hasScrollableAncestor(table)).toBe(true);
    }
  });

  it("各党の案ページ: 幅を固定した表がない（表を使っていない）", () => {
    render(<Proposals />);
    const wide = [...document.body.querySelectorAll<HTMLElement>("table")].filter((t) =>
      t.className.includes("min-w-")
    );
    for (const table of wide) expect(hasScrollableAncestor(table)).toBe(true);
  });

  it("長い党派名のチップが折り返せる", async () => {
    const body = await renderHome();
    const chips = [...body.querySelectorAll<HTMLElement>("span")].filter((s) =>
      s.textContent?.includes("減税日本・ゆうこく連合")
    );
    expect(chips.length).toBeGreaterThan(0);
    // チップ本体（rounded-full）が親幅を超えないようになっている
    const chip = chips.find((c) => c.className.includes("rounded-full"));
    expect(chip).toBeDefined();
    expect(chip!.className).toContain("max-w-full");
    expect(within(chip!).getByText("減税日本・ゆうこく連合").className).toContain("break-all");
  });
});
