const savedTheme = localStorage.getItem("fidpha-theme") || "dark";
applyTheme(savedTheme);

function applyTheme(theme) {
    const root = document.documentElement;
    const icon = document.getElementById("theme-icon");
    const label = document.getElementById("theme-label");

    if (theme === "light") {
        root.setAttribute("data-theme", "light");
        root.style.setProperty("--sidebar-bg", "#ffffff");
        root.style.setProperty("--sidebar-hover", "#f1f5f9");
        root.style.setProperty("--sidebar-active", "#e0f2fe");
        root.style.setProperty("--header-bg", "#ffffff");
        root.style.setProperty("--content-bg", "#f4f6f8");
        root.style.setProperty("--card-bg", "#ffffff");
        root.style.setProperty("--card-border", "#e2e8f0");
        root.style.setProperty("--text-primary", "#0f172a");
        root.style.setProperty("--text-secondary", "#64748b");
        if (icon) icon.textContent = "dark_mode";
        if (label) label.textContent = label.dataset.dark || "Dark mode";
    } else {
        root.setAttribute("data-theme", "dark");
        root.style.setProperty("--sidebar-bg", "#0f172a");
        root.style.setProperty("--sidebar-hover", "#1e293b");
        root.style.setProperty("--sidebar-active", "#1e3a5f");
        root.style.setProperty("--header-bg", "#0f172a");
        root.style.setProperty("--content-bg", "#0f172a");
        root.style.setProperty("--card-bg", "#1e293b");
        root.style.setProperty("--card-border", "#334155");
        root.style.setProperty("--text-primary", "#f1f5f9");
        root.style.setProperty("--text-secondary", "#94a3b8");
        if (icon) icon.textContent = "light_mode";
        if (label) label.textContent = label.dataset.light || "Light mode";
    }

    localStorage.setItem("fidpha-theme", theme);
}

function toggleTheme() {
    const current = localStorage.getItem("fidpha-theme") || "dark";
    applyTheme(current === "dark" ? "light" : "dark");
}

document.addEventListener("DOMContentLoaded", function () {
    applyTheme(localStorage.getItem("fidpha-theme") || "dark");
});