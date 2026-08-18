// @vitest-environment jsdom
/**
 * ページ全体を実際に起動して動かす。
 *
 * `render.test.tsx` は部品を組み立てられるかを見るだけなので、fetch → 状態更新 →
 * 再計算 → 描画という実際の流れは通っていない。ここではブラウザに近い環境で
 * ページを起動し、案の切り替えと制度パラメータの操作が本当に効くかを確かめる。
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import Home from "./page";
import Verify from "./verify/page";

const DATA_DIR = join(__dirname, "..", "..", "public", "data");

beforeEach(() => {
  // 静的エクスポートしたサイトと同じように /data/*.json を返す
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

/** 改革案のタブ。制度パラメータの操作盤にも同名のボタンがあるので、範囲を絞る。 */
function presetTab(name: string): HTMLElement {
  return within(screen.getByRole("group", { name: "比例代表・各党の案" })).getByRole("button", { name });
}

/** 「議員数の合計」行から、現行と案の議席数を読む。 */
function readTotals(): { baseline: number; proposal: number } {
  const row = screen.getByText("議員数の合計").closest("tr")!;
  const cells = within(row).getAllByRole("cell");
  return { baseline: Number(cells[1].textContent), proposal: Number(cells[2].textContent) };
}

/** 「党派別の議席」表から、ある党の現行と案の議席数を読む。 */
function readParty(party: string): { baseline: number; proposal: number } {
  const section = screen.getByRole("heading", { name: "党派別の議席" }).closest("section")!;
  const row = within(section).getByRole("cell", { name: party }).closest("tr")!;
  const cells = within(row).getAllByRole("cell");
  return { baseline: Number(cells[1].textContent), proposal: Number(cells[2].textContent) };
}

describe("シミュレータのページ", () => {
  it("既定では第51回に自民党案を当てはめた結果が出る", async () => {
    render(<Home />);

    await waitFor(() => expect(screen.getByText("議員数の合計")).toBeDefined());

    // 現行465、自民案は比例45減なので法定420・欠員9で411
    const { baseline, proposal } = readTotals();
    expect(baseline).toBe(465);
    expect(proposal).toBe(411);

    expect(screen.getByText("法定定数").parentElement!.textContent).toContain("420");
    expect(screen.getByText("名簿不足による欠員").parentElement!.textContent).toContain("9");
  });

  it("案を切り替えると結果が変わる", async () => {
    const { user } = await setup();

    await user.click(presetTab("チームみらい案"));
    await waitFor(() => expect(readTotals().proposal).toBe(465));

    await user.click(presetTab("現行制度"));
    await waitFor(() => expect(readTotals().proposal).toBe(465));

    // 現行制度を選んだときは、寄与分解が「変化なし」を示す
    expect(screen.getByText(/現行制度と同じパラメータなので/)).toBeDefined();
  });

  it("現行制度に戻すと実際の選挙結果に一致する", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: "現行制度の値に戻す" }));

    await waitFor(() => {
      const { baseline, proposal } = readTotals();
      expect(proposal).toBe(baseline);
      expect(proposal).toBe(465);
    });
  });

  it("配分方式をサンラグ式にすると議席が動く", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: "現行制度の値に戻す" }));
    await waitFor(() => expect(screen.getByText(/現行制度と同じパラメータなので/)).toBeDefined());

    await user.click(screen.getByRole("button", { name: "サンラグ式" }));

    await waitFor(() => {
      // 総定数は変わらないが、寄与分解に配分方式の段が現れる
      expect(readTotals().proposal).toBe(465);
      expect(screen.getByText("比例の配分方式")).toBeDefined();
      expect(screen.getByText(/ドント式（÷1,2,3…）→ サンラグ式/)).toBeDefined();
    });
  });

  it("途中の段で増えて後の段で消える議席は、純増減で打ち消されて見える", async () => {
    await setup();

    const section = screen
      .getByRole("heading", { name: "何がこの変化を起こしたか" })
      .closest("section")!;

    // 減税日本・ゆうこく連合は、①サンラグ式で東海の1議席を得るが
    // ②比例45減で東海の定数が21→15になり、その議席を失う。差し引きゼロ。
    const method = within(section).getByText("比例の配分方式").closest("li")!;
    expect(method.textContent).toMatch(/減税日本・ゆうこく連合\s*\+1/);

    const seatCount = within(section).getByText("比例の定数").closest("li")!;
    expect(seatCount.textContent).toMatch(/減税日本・ゆうこく連合\s*−1/);

    // 純増減には出てこない
    const net = within(section).getByText("現行制度からの純増減").parentElement!;
    expect(net.textContent).not.toContain("減税日本・ゆうこく連合 +");
    expect(net.textContent).toContain("途中の段で議席が動きますが");
    expect(net.textContent).toContain("減税日本・ゆうこく連合");
  });

  it("与党の既定は自民＋維新で、自民案では議席が減るのに占有率は上がる", async () => {
    await setup();

    const panel = screen.getByRole("heading", { name: "与党の議席占有率" }).closest("section")!;

    // 既定の与党が選ばれている
    expect(within(panel).getByRole("button", { name: "✓ 自由民主党" })).toBeDefined();
    expect(within(panel).getByRole("button", { name: "✓ 日本維新の会" })).toBeDefined();

    // 現行 351/465 = 75.5%、自民案 325/411 = 79.1%
    expect(panel.textContent).toContain("351／465議席");
    expect(panel.textContent).toContain("325／411議席");
    expect(panel.textContent).toContain("79.1%");
  });

  it("与党を選び直すと占有率が変わる", async () => {
    const { user } = await setup();
    const panel = screen.getByRole("heading", { name: "与党の議席占有率" }).closest("section")!;

    await user.click(within(panel).getByRole("button", { name: "✓ 日本維新の会" }));

    // 自民単独 315/465 = 67.7%
    await waitFor(() => expect(panel.textContent).toContain("315／465議席"));
  });

  it("選挙回を切り替えると与党の既定も変わる", async () => {
    const { user } = await setup();
    await user.selectOptions(screen.getByLabelText("選挙回"), "r06-10-27");

    await waitFor(() => {
      const panel = screen.getByRole("heading", { name: "与党の議席占有率" }).closest("section")!;
      // 第50回は自公。215/465 で過半数（233）に届かない
      expect(within(panel).getByRole("button", { name: "✓ 公明党" })).toBeDefined();
      expect(panel.textContent).toContain("215／465議席");
      expect(panel.textContent).toContain("過半数に届かず");
    });
  });

  it("修正サンラグを選ぶと第1除数のスライダーが出て、0.1刻みで動かせる", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: "現行制度の値に戻す" }));
    expect(screen.queryByLabelText("修正サンラグの第1除数")).toBeNull();

    await user.click(screen.getByRole("button", { name: "修正サンラグ式" }));

    const slider = await screen.findByLabelText<HTMLInputElement>("修正サンラグの第1除数");
    // 内部では10倍の整数で持ち、0.1刻みで動かす
    expect(slider.step).toBe("1");
    expect(slider.min).toBe("10");
    expect(slider.max).toBe("30");
    expect(slider.value).toBe("14");

    const section = screen
      .getByRole("heading", { name: "何がこの変化を起こしたか" })
      .closest("section")!;
    expect(section.textContent).toContain("修正サンラグ式（÷1.4,3,5…）");

    // 1.0 にすると純粋なサンラグ式と同じ結果になる
    fireEvent.change(slider, { target: { value: "10" } });
    await waitFor(() => {
      expect(screen.getByLabelText<HTMLInputElement>("修正サンラグの第1除数").value).toBe("10");
    });
    const modifiedAt10 = readTotals().proposal;

    await user.click(screen.getByRole("button", { name: "サンラグ式" }));
    await waitFor(() => expect(readTotals().proposal).toBe(modifiedAt10));
  });

  it("修正サンラグ（参考）のプリセットが選べる", async () => {
    const { user } = await setup();

    await user.click(presetTab("修正サンラグ（参考）"));

    await waitFor(() => {
      expect(screen.getByLabelText<HTMLInputElement>("修正サンラグの第1除数").value).toBe("14");
      // 定数は現行のまま
      expect(readTotals().proposal).toBe(465);
    });
  });

  it("連用制を選ぶと自民の議席が大きく減り、総定数は変わらない", async () => {
    const { user } = await setup();

    await user.click(presetTab("連用制"));

    await waitFor(() => {
      expect(readTotals().proposal).toBe(465);
      expect(readParty("自由民主党")).toEqual({ baseline: 315, proposal: 250 });
    });
  });

  it("併用制は総定数固定だと連用制と同じ結果になり、その旨の警告が出る", async () => {
    const { user } = await setup();

    await user.click(presetTab("連用制"));
    await waitFor(() => expect(readTotals().proposal).toBe(465));
    const renyo = readParty("自由民主党");

    await user.click(presetTab("併用制"));
    await waitFor(() => {
      expect(screen.getByText(/連用制と数学的に同一の制度です/)).toBeDefined();
      expect(readParty("自由民主党")).toEqual(renyo);
    });
  });

  it("超過議席を認めると定数が増え、連用制と結果が分かれる", async () => {
    const { user } = await setup();

    await user.click(presetTab("併用制"));
    await waitFor(() => expect(readTotals().proposal).toBe(465));

    await user.click(screen.getByRole("button", { name: "定数が増えるのを認める" }));

    await waitFor(() => {
      // 第51回は 465 → 519（超過54議席）
      expect(readTotals().proposal).toBe(519);
      expect(screen.queryByText(/連用制と数学的に同一の制度です/)).toBeNull();
      expect(screen.getByText("法定定数").parentElement!.textContent).toContain("519");
    });
  });

  it("RCVを選ぶと警告が出て、確定議席と実際に動いた議席が併記される", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: /^RCV/ }));

    await waitFor(() => {
      expect(screen.getByText("⚠ これは仮想のペルソナが生む数字です")).toBeDefined();
      // 第51回は 156議席が第1選好で確定、38議席が入れ替わる
      expect(screen.getByText("仮定によらず確定").parentElement!.textContent).toContain("156");
      expect(screen.getByText("実際に動いた").parentElement!.textContent).toContain("38");
    });
    // 選挙区ごとの途中経過も出る
    expect(screen.getByRole("heading", { name: "選挙区ごとの途中経過" })).toBeDefined();
  });

  it("RCVは案を切り替えても保たれ、現行制度の値に戻すでも消えない", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: /^RCV/ }));
    await waitFor(() => expect(screen.getByText("⚠ これは仮想のペルソナが生む数字です")).toBeDefined());

    await user.click(presetTab("現行制度"));
    expect(screen.getByText("⚠ これは仮想のペルソナが生む数字です")).toBeDefined();

    await user.click(screen.getByRole("button", { name: "現行制度の値に戻す" }));
    expect(screen.getByText("⚠ これは仮想のペルソナが生む数字です")).toBeDefined();
  });

  it("順序を持たない政党がある選挙回では、その旨と得票が出る", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: /^RCV/ }));
    await waitFor(() => expect(screen.getByText("⚠ これは仮想のペルソナが生む数字です")).toBeDefined());

    // 第51回で順序を持たないのは諸派だけなので、赤い警告は出ない
    expect(
      screen.queryByText("この選挙回には、選好順序を持たない大きな政党があります")
    ).toBeNull();
    expect(screen.getAllByText(/選好順序を持たない諸派/).length).toBeGreaterThan(0);

    // 第47回（2014）は民主党・維新の党が調査に無いので警告が出る
    await user.selectOptions(screen.getByLabelText("選挙回"), "h26-12-14");
    await waitFor(
      () => {
        const box = screen
          .getByText("この選挙回には、選好順序を持たない大きな政党があります")
          .parentElement!;
        expect(box.textContent).toContain("民主党");
        expect(box.textContent).toContain("維新の党");
      },
      { timeout: 15000 }
    );
  }, 30000);

  it("選挙回を切り替えると定数が変わる", async () => {
    const { user } = await setup();

    await user.click(screen.getByRole("button", { name: "現行制度の値に戻す" }));
    await user.selectOptions(screen.getByLabelText("選挙回"), "h26-12-14");

    // 第47回は0増5減の前で475議席
    await waitFor(() => expect(readTotals().proposal).toBe(475));
  });
});

describe("検証ページ", () => {
  it("全選挙回で現行制度の再計算が実際の結果と一致する", async () => {
    render(<Verify />);

    await waitFor(
      () => {
        const hits = screen.getAllByText("✓ 完全一致");
        expect(hits.length).toBe(5);
      },
      { timeout: 15000 }
    );

    expect(screen.getByText(/全ての選挙回で、ブロック×党派の議席数と比例当選者の顔ぶれが/)).toBeDefined();
    expect(screen.queryByText(/✗ 不一致/)).toBeNull();
  });
});

async function setup() {
  const { default: userEvent } = await import("@testing-library/user-event");
  const user = userEvent.setup();
  render(<Home />);
  await waitFor(() => expect(screen.getByText("議員数の合計")).toBeDefined());
  return { user };
}
