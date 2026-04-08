document.addEventListener("DOMContentLoaded", function () {

    // --------------------------------
    // Show/hide profile inline based on staff status
    // --------------------------------
    function initProfileToggle() {
        const staffToggle = document.getElementById("id_is_staff");
        const profileInline = document.getElementById("profile-data");

        if (!staffToggle || !profileInline) return;

        function toggleProfileInline() {
            if (staffToggle.checked) {
                profileInline.style.display = "none";
            } else {
                profileInline.style.display = "block";
            }
        }

        toggleProfileInline();
        staffToggle.addEventListener("change", toggleProfileInline);
    }

    setTimeout(initProfileToggle, 300);


    // --------------------------------
    // Password strength checker
    // --------------------------------
    const p1 = document.getElementById("id_password1");
    const p2 = document.getElementById("id_password2");

    if (p1 && p2) {
        const strengthContainer = document.createElement("div");
        strengthContainer.style.cssText = "margin-top: 8px;";
        strengthContainer.innerHTML = `
            <div style="height: 4px; background-color: #334155; border-radius: 4px; overflow: hidden; margin-bottom: 6px;">
                <div id="admin-strength-bar" style="height: 100%; width: 0%; border-radius: 4px; transition: all 0.3s;"></div>
            </div>
            <div id="admin-strength-text" style="font-size: 0.75rem; margin-bottom: 8px;"></div>
            <div id="admin-req-length"  style="font-size: 0.75rem; color: #888;">✗ At least 8 characters</div>
            <div id="admin-req-upper"   style="font-size: 0.75rem; color: #888;">✗ At least one uppercase letter</div>
            <div id="admin-req-number"  style="font-size: 0.75rem; color: #888;">✗ At least one number</div>
            <div id="admin-req-special" style="font-size: 0.75rem; color: #888;">✗ At least one special character</div>
        `;
        p1.parentNode.insertBefore(strengthContainer, p1.nextSibling);

        const matchDiv = document.createElement("div");
        matchDiv.id = "admin-match-text";
        matchDiv.style.cssText = "font-size: 0.75rem; margin-top: 6px;";
        p2.parentNode.insertBefore(matchDiv, p2.nextSibling);

        function updateReq(id, met) {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.color = met ? "#22c55e" : "#888";
            el.textContent = (met ? "✓" : "✗") + el.textContent.substring(1);
        }

        function checkStrength(pwd) {
            const hasLength  = pwd.length >= 8;
            const hasUpper   = /[A-Z]/.test(pwd);
            const hasNumber  = /[0-9]/.test(pwd);
            const hasSpecial = /[!@#$%^&*()_+\-=\[\]{}|;':",./<>?]/.test(pwd);

            updateReq("admin-req-length",  hasLength);
            updateReq("admin-req-upper",   hasUpper);
            updateReq("admin-req-number",  hasNumber);
            updateReq("admin-req-special", hasSpecial);

            const score = [hasLength, hasUpper, hasNumber, hasSpecial].filter(Boolean).length;
            const bar = document.getElementById("admin-strength-bar");
            const text = document.getElementById("admin-strength-text");

            const colors = ["#ef4444", "#f59e0b", "#3b82f6", "#22c55e"];
            const labels = ["Weak", "Fair", "Good", "Strong"];
            const widths = ["25%", "50%", "75%", "100%"];

            if (pwd.length === 0) {
                bar.style.width = "0%";
                text.textContent = "";
            } else {
                bar.style.backgroundColor = colors[score - 1];
                bar.style.width = widths[score - 1];
                text.style.color = colors[score - 1];
                text.textContent = labels[score - 1];
            }
        }

        function checkMatch() {
            const matchDiv = document.getElementById("admin-match-text");
            if (!matchDiv) return;
            if (p2.value.length === 0) {
                matchDiv.textContent = "";
                return;
            }
            if (p1.value === p2.value) {
                matchDiv.style.color = "#22c55e";
                matchDiv.textContent = "✓ Passwords match";
            } else {
                matchDiv.style.color = "#ef4444";
                matchDiv.textContent = "✗ Passwords don't match";
            }
        }

        p1.addEventListener("input", () => { checkStrength(p1.value); checkMatch(); });
        p2.addEventListener("input", checkMatch);
    }

});