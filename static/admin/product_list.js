document.addEventListener("DOMContentLoaded", function () {

    // --------------------------------
    // 1. Dynamic search with focus restore
    // --------------------------------
    const searchInput = document.getElementById("searchbar");
    if (searchInput) {
        const savedSearch = sessionStorage.getItem("product_search_query");
        if (savedSearch !== null && searchInput.value === savedSearch) {
            searchInput.focus();
            searchInput.setSelectionRange(savedSearch.length, savedSearch.length);
        }

        let searchTimeout = null;
        searchInput.addEventListener("input", function () {
            sessionStorage.setItem("product_search_query", this.value);
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                this.closest("form").submit();
            }, 500);
        });
    }

    // --------------------------------
    // 2. Move Add button below search bar
    // --------------------------------
    const addButton = document.querySelector("a.addlink");
    const searchForm = document.getElementById("changelist-search");
    if (addButton && searchForm) {
        const addWrapper = document.createElement("div");
        addWrapper.style.cssText = "margin-top: 10px; margin-bottom: 4px;";

        const newAddBtn = document.createElement("a");
        newAddBtn.href = addButton.href;
        newAddBtn.style.cssText = `
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 8px 16px;
            background-color: #1b679b;
            color: white;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            text-decoration: none;
        `;
        newAddBtn.innerHTML = `
            <span class="material-symbols-outlined" style="font-size: 18px;">add_circle</span>
            Add Product
        `;

        addWrapper.appendChild(newAddBtn);
        searchForm.parentNode.insertBefore(addWrapper, searchForm.nextSibling);
        addButton.style.display = "none";
    }

    // --------------------------------
    // 3. Status filter next to Status header
    // --------------------------------
    const headers = document.querySelectorAll("th");
    let statusHeader = null;
    headers.forEach(th => {
        if (th.textContent.trim().startsWith("Status")) {
            statusHeader = th;
        }
    });

    if (statusHeader) {
        const urlParams = new URLSearchParams(window.location.search);
        const currentFilter = urlParams.get("status__exact") || "all";

        const filterGroup = document.createElement("div");
        filterGroup.style.cssText = `
            display: inline-flex;
            align-items: center;
            gap: 4px;
            margin-left: 8px;
            vertical-align: middle;
        `;

        ["all", "active", "inactive"].forEach(value => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = value.charAt(0).toUpperCase() + value.slice(1);
            const isActive = (value === "all" && !urlParams.get("status__exact")) || value === currentFilter;
            btn.style.cssText = `
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.7rem;
                font-weight: 600;
                cursor: pointer;
                border: 1px solid ${value === "active" ? "rgba(34,197,94,0.4)" : value === "inactive" ? "rgba(239,68,68,0.4)" : "rgba(100,116,139,0.4)"};
                background-color: ${isActive
                    ? value === "active" ? "rgba(34,197,94,0.2)"
                    : value === "inactive" ? "rgba(239,68,68,0.2)"
                    : "rgba(100,116,139,0.2)"
                    : "transparent"};
                color: ${value === "active" ? "#22c55e" : value === "inactive" ? "#ef4444" : "#64748b"};
            `;
            btn.addEventListener("click", () => {
                const params = new URLSearchParams(window.location.search);
                if (value === "all") {
                    params.delete("status__exact");
                } else {
                    params.set("status__exact", value);
                }
                window.location.search = params.toString();
            });
            filterGroup.appendChild(btn);
        });

        statusHeader.appendChild(filterGroup);
    }

    // --------------------------------
    // 4. Hide Filters button
    // --------------------------------
    const style = document.createElement("style");
    style.textContent = `
        button[x-on\\:click*="filterOpen"],
        [x-on\\:click*="filterOpen"],
        [\\@click*="filterOpen"] {
            display: none !important;
        }
    `;
    document.head.appendChild(style);

    // --------------------------------
    // 5. Replace action dropdown with buttons
    // --------------------------------
    function initActionButtons() {
        const actionBar = document.querySelector(".actions");
        if (!actionBar) return;

        // prevent double initialization
        if (actionBar.dataset.initialized) return;
        actionBar.dataset.initialized = "true";

        const actionSelect = actionBar.querySelector("select");
        const goButton = actionBar.querySelector("button[type='submit'], input[type='submit']");
        if (!actionSelect || !goButton) return;

        function isDark() {
            return document.documentElement.classList.contains("dark");
        }

        function updateActionBarColors() {
            actionBar.style.cssText = `
                background-color: ${isDark() ? "#1e293b" : "white"};
                border-top: 1px solid ${isDark() ? "#334155" : "#e2e8f0"};
                padding: 10px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
            `;
        }

        updateActionBarColors();

        const observer = new MutationObserver(() => updateActionBarColors());
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

        actionSelect.style.display = "none";
        goButton.style.display = "none";

        const resultList = document.querySelector(".results");
        if (resultList) resultList.style.paddingBottom = "60px";

        const btnGroup = document.createElement("div");
        btnGroup.style.cssText = "display: inline-flex; gap: 8px; align-items: center;";

        const actions = [
            { value: "activate_products", label: "✓ Activate", bg: "rgba(34,197,94,0.15)", color: "#22c55e", border: "rgba(34,197,94,0.3)" },
            { value: "deactivate_products", label: "✗ Deactivate", bg: "rgba(239,68,68,0.15)", color: "#ef4444", border: "rgba(239,68,68,0.3)" },
        ];

        actions.forEach(action => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.textContent = action.label;
            btn.style.cssText = `
                padding: 6px 14px;
                border-radius: 20px;
                font-size: 0.78rem;
                font-weight: 600;
                cursor: pointer;
                border: 1px solid ${action.border};
                background-color: ${action.bg};
                color: ${action.color};
            `;
            btn.addEventListener("click", () => {
                actionSelect.value = action.value;
                goButton.click();
            });
            btnGroup.appendChild(btn);
        });

        actionBar.appendChild(btnGroup);
    }

    setTimeout(initActionButtons, 300);
});