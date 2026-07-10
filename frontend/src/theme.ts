// Flash-of-wrong-theme is avoided by an inline blocking script in <head> that sets
// data-theme from localStorage before CSS paints (see index.html / admin.html).
const STORAGE_KEY = "avatar-theme";

export function currentTheme(): "dark" | "light" {
  return document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
}

export function setupThemeToggle(buttonId: string): void {
  const root = document.documentElement;
  const button = document.getElementById(buttonId);
  if (!button) return;
  const moon = button.querySelector<HTMLElement>(".theme-moon");
  const sun = button.querySelector<HTMLElement>(".theme-sun");
  const sync = () => {
    const dark = currentTheme() === "dark";
    if (moon) moon.style.display = dark ? "" : "none";
    if (sun) sun.style.display = dark ? "none" : "";
  };
  sync();
  button.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem(STORAGE_KEY, next);
    sync();
  });
}
