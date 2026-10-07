import { describe, expect, it } from "vitest";

import { monthYearLabel, shiftMonth } from "./format";

describe("monthYearLabel", () => {
  it("formats the month in Portuguese with the year", () => {
    expect(monthYearLabel({ year: 2026, month: 10 })).toBe("Outubro de 2026");
    expect(monthYearLabel({ year: 2027, month: 3 })).toBe("Março de 2027");
  });
});

describe("shiftMonth", () => {
  it("moves within a year", () => {
    expect(shiftMonth({ year: 2026, month: 10 }, -1)).toEqual({ year: 2026, month: 9 });
    expect(shiftMonth({ year: 2026, month: 10 }, 1)).toEqual({ year: 2026, month: 11 });
  });

  it("wraps across year boundaries", () => {
    expect(shiftMonth({ year: 2026, month: 1 }, -1)).toEqual({ year: 2025, month: 12 });
    expect(shiftMonth({ year: 2026, month: 12 }, 1)).toEqual({ year: 2027, month: 1 });
    expect(shiftMonth({ year: 2026, month: 6 }, -18)).toEqual({ year: 2024, month: 12 });
  });
});
