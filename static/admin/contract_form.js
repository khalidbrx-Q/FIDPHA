document.addEventListener("DOMContentLoaded", function () {



    // replace three dots menu with eye icon
function updateProductMenus() {
    const group = document.getElementById("contract_product_set-group");
    if (!group) return;

    const menuWrappers = group.querySelectorAll("[x-data*='openRelatedWidgetWrapper']");
    menuWrappers.forEach(wrapper => {
        if (wrapper.dataset.menuChanged) return;
        wrapper.dataset.menuChanged = "true";

        // find the view link inside the template
        const template = wrapper.querySelector("template");
        if (!template) return;

        // get the view link href template
        const viewLink = template.content?.querySelector(".view-related");
        const hrefTemplate = viewLink?.dataset.hrefTemplate;

        // get the current selected product id from the select
        const select = wrapper.closest("td")?.querySelector("select");

        // replace the whole wrapper with a simple eye button
        const eyeBtn = document.createElement("a");
        eyeBtn.title = "View product";
        eyeBtn.target = "_blank";
        eyeBtn.style.cssText = `
            display: flex;
            align-items: center;
            justify-content: center;
            height: 38px;
            width: 38px;
            border-radius: 6px;
            border: 1px solid rgba(27,103,155,0.3);
            background-color: rgba(27,103,155,0.1);
            color: #1b679b;
            cursor: pointer;
            text-decoration: none;
            flex-shrink: 0;
            margin-left: 8px;
        `;
        eyeBtn.innerHTML = `<span class="material-symbols-outlined" style="font-size: 18px;">visibility</span>`;

        // update href when clicked based on current selected value
        eyeBtn.addEventListener("click", (e) => {
            if (select && hrefTemplate) {
                const productId = select.value;
                if (!productId) {
                    e.preventDefault();
                    return;
                }
                eyeBtn.href = hrefTemplate.replace("__fk__", productId);
            }
        });

        wrapper.replaceWith(eyeBtn);
    });
}

setTimeout(updateProductMenus, 600);

/// change trash icon to unlink icon
function updateDeleteIcons() {
    const group = document.getElementById("contract_product_set-group");
    if (!group) return;

    const deleteTds = group.querySelectorAll("td.delete");
    deleteTds.forEach(td => {
        if (td.dataset.iconChanged) return;
        td.dataset.iconChanged = "true";

        const label = td.querySelector("label");
        if (label) {
            // find the icon inside the label and replace it
            const icon = label.querySelector("span, svg");
            if (icon) {
                icon.textContent = "link_off";
                icon.className = "material-symbols-outlined";
                icon.style.cssText = "font-size: 18px; color: #f59e0b;";
            }
            label.title = "Unlink product from contract";
        }
    });
}

setTimeout(updateDeleteIcons, 600);


// change "deleted" text to "unlinked" text
function updateDeleteText() {
    const group = document.getElementById("contract_product_set-group");
    if (!group) return;

    const deleteMessages = group.querySelectorAll(".form-delete td, [class*='deleted'], .form-group");

    // watch for DOM changes to catch when delete is clicked
    const observer = new MutationObserver(() => {
        group.querySelectorAll("*").forEach(el => {
            if (el.childNodes.length === 1 &&
                el.childNodes[0].nodeType === 3 &&
                el.textContent.includes("This item will be deleted")) {
                el.textContent = el.textContent.replace(
                    "This item will be deleted.",
                    "This item will be unlinked from this contract."
                );
            }
        });
    });

    observer.observe(group, { childList: true, subtree: true, characterData: true });
}

updateDeleteText();

    function initProductSearch() {
        const group = document.getElementById("contract_product_set-group");
        if (!group) return;

        const formsetWrapper = group.querySelector(".formset-wrapper");
        if (!formsetWrapper) return;

        const wrapperParent = formsetWrapper.parentNode;

        function isDark() {
            return document.documentElement.classList.contains("dark");
        }

        function getColors() {
            const dark = isDark();
            return {
                bg: dark ? "#1e293b" : "#f8fafc",
                border: dark ? "#334155" : "#e2e8f0",
                inputBg: dark ? "#0f172a" : "white",
                text: dark ? "#f1f5f9" : "#1e293b",
                textSecondary: dark ? "#94a3b8" : "#64748b",
                btnBg: dark ? "#334155" : "#e2e8f0",
            };
        }

        // get contract id from URL
        const contractId = window.location.pathname.split("/").filter(Boolean).slice(-2, -1)[0];

        // hide original add button
        const addButton = group.querySelector(".add-row");
        if (addButton) addButton.style.display = "none";

        // create add button at top
        const addTop = document.createElement("button");
        addTop.type = "button";
        addTop.style.cssText = `
            display: inline-flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 12px;
            font-size: 0.85rem;
            font-weight: 600;
            color: white;
            cursor: pointer;
            background-color: #1b679b;
            border: none;
            padding: 8px 16px;
            border-radius: 8px;
        `;
        addTop.innerHTML = `
            <span class="material-symbols-outlined" style="font-size:18px;">add_circle</span>
            Add Product
        `;
        addTop.addEventListener("click", () => openAddProductModal(contractId));
        wrapperParent.insertBefore(addTop, formsetWrapper);

        // create search bar
        const searchBar = document.createElement("div");
        searchBar.id = "contract-product-search-wrapper";

        function updateSearchBarColors() {
            const c = getColors();
            searchBar.style.cssText = `
                padding: 10px 12px 8px 12px;
                background-color: ${c.bg};
                border: 1px solid ${c.border};
                border-radius: 8px;
                margin-bottom: 12px;
            `;
            const input = searchBar.querySelector("input");
            if (input) {
                input.style.backgroundColor = c.inputBg;
                input.style.borderColor = c.border;
                input.style.color = c.text;
            }
        }

        const c = getColors();
        searchBar.innerHTML = `
            <div style="position: relative;">
                <span style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 18px;" class="material-symbols-outlined">search</span>
                <input type="text" id="contract-product-search" placeholder="Search products by name or external designation..."
                    style="width: 100%; padding: 8px 14px 8px 36px; background-color: ${c.inputBg}; border: 1px solid ${c.border}; border-radius: 8px; font-size: 0.88rem; color: ${c.text}; box-sizing: border-box; outline: none;">
            </div>
            <div style="margin-top: 6px; font-size: 0.75rem; color: #1b679b; font-weight: 600; padding-left: 2px;">
                Showing <span id="product-count"></span> products
            </div>
        `;
        updateSearchBarColors();
        wrapperParent.insertBefore(searchBar, formsetWrapper);

        // watch for theme changes
        const observer = new MutationObserver(() => updateSearchBarColors());
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

        const searchInput = document.getElementById("contract-product-search");
        const countEl = document.getElementById("product-count");

        function updateCount() {
            const rows = formsetWrapper.querySelectorAll(".form-group:not(.empty-form)");
            const visible = [...rows].filter(r => r.style.display !== "none").length;
            if (countEl) countEl.textContent = visible;
        }

        function searchProducts() {
            const query = searchInput.value.toLowerCase().trim();
            const rows = formsetWrapper.querySelectorAll(".form-group:not(.empty-form)");
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = (!query || text.includes(query)) ? "" : "none";
            });
            updateCount();
        }

        searchInput.addEventListener("input", searchProducts);
        updateCount();
    }

    // --------------------------------
    // Add Product Modal
    // --------------------------------
    function openAddProductModal(contractId) {
        function isDark() { return document.documentElement.classList.contains("dark"); }
        const dark = isDark();
        const bg = dark ? "#1e293b" : "white";
        const border = dark ? "#334155" : "#e2e8f0";
        const textPrimary = dark ? "#f1f5f9" : "#1e293b";
        const textSecondary = dark ? "#94a3b8" : "#64748b";
        const inputBg = dark ? "#0f172a" : "#f8fafc";
        const btnBg = dark ? "#334155" : "#e2e8f0";

        fetch(`/api/contract/${contractId}/available-products/`)
            .then(r => r.json())
            .then(data => {
                const products = data.products || [];

                let existing = document.getElementById("add-product-modal");
                if (existing) existing.remove();

                const modal = document.createElement("div");
                modal.id = "add-product-modal";
                modal.style.cssText = `
                    display: flex;
                    position: fixed;
                    top: 0; left: 0;
                    width: 100%; height: 100%;
                    background-color: rgba(0,0,0,0.6);
                    z-index: 9999;
                    align-items: center;
                    justify-content: center;
                `;

                modal.innerHTML = `
                    <div style="
                        background-color: ${bg};
                        border: 1px solid ${border};
                        border-radius: 12px;
                        padding: 24px;
                        max-width: 500px;
                        width: 90%;
                        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
                    ">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span class="material-symbols-outlined" style="color: #1b679b; font-size: 22px;">add_circle</span>
                                <h3 style="color: ${textPrimary}; font-size: 1rem; font-weight: 600; margin: 0;">Add Product to Contract</h3>
                            </div>
                            <button type="button" onclick="document.getElementById('add-product-modal').remove()"
                                style="background:none;border:none;cursor:pointer;color:${textSecondary};font-size:20px;line-height:1;">✕</button>
                        </div>

                        <div style="margin-bottom: 16px;">
                            <label style="font-size: 0.82rem; color: ${textSecondary}; display: block; margin-bottom: 6px; font-weight: 500;">Search Product</label>
                            <div style="position: relative;">
                                <span style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); font-size: 18px;" class="material-symbols-outlined">search</span>
                                <input type="text" id="modal-product-search" placeholder="Type to search..."
                                    style="width: 100%; padding: 9px 14px 9px 36px; background-color: ${inputBg}; border: 1px solid ${border}; border-radius: 8px; font-size: 0.88rem; color: ${textPrimary}; box-sizing: border-box; outline: none;">
                            </div>
                        </div>

                        <div style="margin-bottom: 16px;">
                            <label style="font-size: 0.82rem; color: ${textSecondary}; display: block; margin-bottom: 6px; font-weight: 500;">Select Product</label>
                            <div id="modal-product-list" style="max-height: 200px; overflow-y: auto; border: 1px solid ${border}; border-radius: 8px; scrollbar-width: thin;">
                                ${products.length === 0
                                    ? `<div style="padding: 16px; text-align: center; color: ${textSecondary}; font-size: 0.88rem;">No available products</div>`
                                    : products.map(p => `
                                        <div class="modal-product-item"
                                            data-id="${p.id}"
                                            data-name="${p.designation.toLowerCase()}"
                                            data-code="${p.code.toLowerCase()}"
                                            onclick="selectProduct(this)"
                                            style="padding: 10px 14px; cursor: pointer; border-bottom: 1px solid ${border}; font-size: 0.88rem; color: ${textPrimary}; transition: background 0.15s;">
                                            <span style="font-weight: 600; color: #1b679b;">[${p.code}]</span> ${p.designation}
                                        </div>
                                    `).join("")
                                }
                            </div>
                            <div id="selected-product" style="margin-top: 6px; font-size: 0.78rem; color: #22c55e; font-weight: 600;"></div>
                        </div>

                        <div style="margin-bottom: 20px;">
                            <label style="font-size: 0.82rem; color: ${textSecondary}; display: block; margin-bottom: 6px; font-weight: 500;">
                                External Designation <span style="color:#ef4444;">*</span>
                            </label>
                            <input type="text" id="modal-ext-designation" placeholder="Enter external designation..."
                                style="width: 100%; padding: 9px 14px; background-color: ${inputBg}; border: 1px solid ${border}; border-radius: 8px; font-size: 0.88rem; color: ${textPrimary}; box-sizing: border-box; outline: none;">
                        </div>

                        <div id="modal-error" style="display:none; color: #ef4444; font-size: 0.82rem; margin-bottom: 12px; padding: 8px 12px; background-color: rgba(239,68,68,0.1); border-radius: 6px;"></div>

                        <div style="display: flex; gap: 10px; justify-content: flex-end;">
                            <button type="button" onclick="document.getElementById('add-product-modal').remove()"
                                style="padding: 9px 20px; background-color: ${btnBg}; color: ${textPrimary}; border: none; border-radius: 8px; font-size: 0.88rem; font-weight: 600; cursor: pointer;">
                                Cancel
                            </button>
                            <button type="button" onclick="submitAddProduct(${contractId})"
                                style="padding: 9px 20px; background-color: #1b679b; color: white; border: none; border-radius: 8px; font-size: 0.88rem; font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px;">
                                <span class="material-symbols-outlined" style="font-size: 16px;">add</span>
                                Add Product
                            </button>
                        </div>
                    </div>
                `;

                modal.addEventListener("click", function(e) {
                    if (e.target === modal) modal.remove();
                });

                document.body.appendChild(modal);

                document.getElementById("modal-product-search").addEventListener("input", function() {
                    const query = this.value.toLowerCase().trim();
                    document.querySelectorAll(".modal-product-item").forEach(item => {
                        const name = item.dataset.name;
                        const code = item.dataset.code;
                        item.style.display = (!query || name.includes(query) || code.includes(query)) ? "" : "none";
                    });
                });
            })
            .catch(err => console.error(err));
    }

    window.selectProduct = function(el) {
        document.querySelectorAll(".modal-product-item").forEach(item => {
            item.style.backgroundColor = "";
        });
        el.style.backgroundColor = "rgba(27,103,155,0.15)";
        document.getElementById("add-product-modal").setAttribute("data-selected-id", el.dataset.id);
        document.getElementById("selected-product").textContent = `✓ Selected: [${el.dataset.code.toUpperCase()}] ${el.dataset.name}`;
    };

    window.submitAddProduct = function(contractId) {
        const modal = document.getElementById("add-product-modal");
        const productId = modal.getAttribute("data-selected-id");
        const extDesignation = document.getElementById("modal-ext-designation").value.trim();
        const errorEl = document.getElementById("modal-error");

        if (!productId) {
            errorEl.textContent = "Please select a product.";
            errorEl.style.display = "block";
            return;
        }
        if (!extDesignation) {
            errorEl.textContent = "Please enter an external designation.";
            errorEl.style.display = "block";
            return;
        }

        errorEl.style.display = "none";

        fetch(`/api/contract/${contractId}/add-product/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ""
            },
            body: JSON.stringify({
                product_id: productId,
                external_designation: extDesignation
            })
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                modal.remove();
                window.location.reload();
            } else {
                errorEl.textContent = data.error || "Failed to add product.";
                errorEl.style.display = "block";
            }
        })
        .catch(() => {
            errorEl.textContent = "Network error. Please try again.";
            errorEl.style.display = "block";
        });
    };

    setTimeout(initProductSearch, 500);
});