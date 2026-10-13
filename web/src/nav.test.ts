import { describe, expect, it } from "vitest";

import { NAV, navFor, resolveNav, visibleNav } from "./nav";

const paths = (items: { path: string }[]) => items.map((item) => item.path);

describe("menu preference resolution", () => {
  it("keeps the default order with no preference", () => {
    expect(paths(visibleNav(navFor("member"), null))).toEqual(paths(navFor("member")));
  });

  it("puts Finanças on top and hides everything else", () => {
    const items = navFor("member");
    const pref = { order: ["/finance"], hidden: paths(items).filter((p) => p !== "/finance") };
    expect(paths(visibleNav(items, pref))).toEqual(["/finance"]);
  });

  it("appends items missing from the saved order and ignores unknown paths", () => {
    const pref = { order: ["/", "/gone", "/goals"], hidden: [] };
    const resolved = paths(resolveNav(navFor("member"), pref).map((entry) => entry.item));
    expect(resolved.slice(0, 2)).toEqual(["/", "/goals"]);
    expect(resolved).not.toContain("/gone");
    expect(resolved).toHaveLength(navFor("member").length);
    expect(resolved[2]).toBe("/finance"); // first remaining item in default order
  });

  it("never shows admin-only items to non-admins, whatever the preference", () => {
    const pref = { order: ["/admin"], hidden: [] };
    expect(paths(visibleNav(navFor("member"), pref))).not.toContain("/admin");
    expect(paths(visibleNav(navFor("admin"), pref))[0]).toBe("/admin");
    expect(NAV.some((item) => item.path === "/admin")).toBe(true);
  });
});
