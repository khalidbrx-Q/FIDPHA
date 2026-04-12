function getModalColors() {
    const isDark = document.documentElement.classList.contains("dark");
    return {
        bg: isDark ? "#1e293b" : "white",
        border: isDark ? "#334155" : "#e2e8f0",
        title: isDark ? "#f1f5f9" : "#1e293b",
        text: isDark ? "#94a3b8" : "#64748b",
        btnBg: isDark ? "#334155" : "#e2e8f0",
        btnColor: isDark ? "#f1f5f9" : "#1e293b",
    };
}

function toggleProductStatus(productId, newStatus) {
    fetch(`/api/product/${productId}/toggle/?status=${newStatus}`)
        .then(r => r.json())
        .then(data => {
            if (data.blocked) {
                const colors = getModalColors();

                let contractsList = data.contracts.map(c => `
                    <div style="padding: 10px 14px; border-radius: 8px; background-color: rgba(27,103,155,0.1); border: 1px solid rgba(27,103,155,0.2); margin-bottom: 8px;">
                        <a href="${c.url}" style="color: #1b679b; font-weight: 600; text-decoration: none; font-size: 0.9rem;">${c.title}</a>
                        <div style="font-size: 0.78rem; color: ${colors.text}; margin-top: 2px;">${c.account} &nbsp;·&nbsp; ${c.start_date} → ${c.end_date}</div>
                    </div>
                `).join("");

                document.getElementById("fidpha-modal-title").textContent = `Cannot deactivate "${data.product}"`;
                document.getElementById("fidpha-modal-title").style.color = colors.title;
                document.getElementById("fidpha-modal-body").innerHTML = `
                    <p style="color: ${colors.text}; font-size: 0.88rem; margin-bottom: 16px;">
                        This product is currently linked to the following active contracts. Please deactivate these contracts first.
                    </p>
                    ${contractsList}
                `;

                // update modal box colors
                const modalBox = document.querySelector("#fidpha-modal > div");
                modalBox.style.backgroundColor = colors.bg;
                modalBox.style.borderColor = colors.border;

                // update close button
                const closeBtn = document.querySelector("#fidpha-modal button");
                closeBtn.style.backgroundColor = colors.btnBg;
                closeBtn.style.color = colors.btnColor;

                document.getElementById("fidpha-modal").style.display = "flex";
            } else {
                window.location.reload();
            }
        })
        .catch(err => console.error(err));
}

function closeFidphaModal() {
    document.getElementById("fidpha-modal").style.display = "none";
}

document.addEventListener("DOMContentLoaded", function() {
    const modal = document.createElement("div");
    modal.id = "fidpha-modal";
    modal.style.cssText = `
        display: none;
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
            background-color: white;
            border: 1px solid #e2e8f0;
            border-radius: 12px;
            padding: 24px;
            max-width: 480px;
            width: 90%;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        ">
            <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 16px;">
                <span style="font-size: 22px;">⚠️</span>
                <h3 id="fidpha-modal-title" style="color: #1e293b; font-size: 1rem; font-weight: 600; margin: 0;"></h3>
            </div>
            <div id="fidpha-modal-body"></div>
            <div style="margin-top: 20px; text-align: right;">
                <button onclick="closeFidphaModal()" style="
                    padding: 8px 20px;
                    background-color: #e2e8f0;
                    color: #1e293b;
                    border: none;
                    border-radius: 8px;
                    font-size: 0.88rem;
                    font-weight: 600;
                    cursor: pointer;
                ">Close</button>
            </div>
        </div>
    `;
    modal.addEventListener("click", function(e) {
        if (e.target === modal) closeFidphaModal();
    });
    document.body.appendChild(modal);
});