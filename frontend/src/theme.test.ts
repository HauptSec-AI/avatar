import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { currentTheme, setupThemeToggle } from "./theme";

function buildToggleButton(id: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.id = id;
  button.innerHTML = `<span class="theme-moon"></span><span class="theme-sun"></span>`;
  document.body.appendChild(button);
  return button;
}

beforeEach(() => {
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

afterEach(() => {
  document.body.innerHTML = "";
  document.documentElement.removeAttribute("data-theme");
  localStorage.clear();
});

describe("currentTheme", () => {
  it("defaults to dark when no data-theme attribute is set", () => {
    expect(currentTheme()).toBe("dark");
  });

  it("returns light only when the attribute is exactly 'light'", () => {
    document.documentElement.setAttribute("data-theme", "light");
    expect(currentTheme()).toBe("light");
  });

  it("treats any other value as dark", () => {
    document.documentElement.setAttribute("data-theme", "solarized");
    expect(currentTheme()).toBe("dark");
  });
});

describe("setupThemeToggle", () => {
  it("does nothing (no throw) if the button id doesn't exist", () => {
    expect(() => setupThemeToggle("does-not-exist")).not.toThrow();
  });

  it("toggles data-theme and persists it to localStorage on click", () => {
    buildToggleButton("themeToggle");
    setupThemeToggle("themeToggle");
    expect(currentTheme()).toBe("dark");

    document.getElementById("themeToggle")!.click();
    expect(currentTheme()).toBe("light");
    expect(localStorage.getItem("avatar-theme")).toBe("light");

    document.getElementById("themeToggle")!.click();
    expect(currentTheme()).toBe("dark");
    expect(localStorage.getItem("avatar-theme")).toBe("dark");
  });

  it("shows the moon icon in dark mode and the sun icon in light mode", () => {
    const button = buildToggleButton("themeToggle");
    setupThemeToggle("themeToggle");
    const moon = button.querySelector<HTMLElement>(".theme-moon")!;
    const sun = button.querySelector<HTMLElement>(".theme-sun")!;

    expect(moon.style.display).toBe("");
    expect(sun.style.display).toBe("none");

    button.click();
    expect(moon.style.display).toBe("none");
    expect(sun.style.display).toBe("");
  });
});
