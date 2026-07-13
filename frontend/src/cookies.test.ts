import { afterEach, describe, expect, it } from "vitest";
import { deleteCookie, getCookie, setCookie } from "./cookies";

afterEach(() => {
  // jsdom's cookie jar persists across tests in this file -- clear whatever
  // this file's tests may have set so they can't leak into one another.
  for (const name of ["avatar_test_a", "avatar_test_b", "avatar_test_roundtrip"]) {
    deleteCookie(name);
  }
});

describe("getCookie / setCookie / deleteCookie", () => {
  it("returns null for a cookie that was never set", () => {
    expect(getCookie("avatar_test_a")).toBeNull();
  });

  it("round-trips a plain value", () => {
    setCookie("avatar_test_a", "some-uuid-value");
    expect(getCookie("avatar_test_a")).toBe("some-uuid-value");
  });

  it("URL-encodes and decodes values with special characters", () => {
    setCookie("avatar_test_roundtrip", "a value; with special=chars&stuff");
    expect(getCookie("avatar_test_roundtrip")).toBe("a value; with special=chars&stuff");
  });

  it("deleteCookie removes a previously-set cookie", () => {
    setCookie("avatar_test_a", "temporary");
    expect(getCookie("avatar_test_a")).toBe("temporary");
    deleteCookie("avatar_test_a");
    expect(getCookie("avatar_test_a")).toBeNull();
  });

  it("distinguishes cookies with different names", () => {
    setCookie("avatar_test_a", "first");
    setCookie("avatar_test_b", "second");
    expect(getCookie("avatar_test_a")).toBe("first");
    expect(getCookie("avatar_test_b")).toBe("second");
  });
});
