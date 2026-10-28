document.addEventListener("DOMContentLoaded", () => {
    // Initialize icons
    lucide.createIcons();

    let currentLeads = [];
    let selectedLead = null;

    // Elements
    const scanForm = document.getElementById("scanForm");
    const volumeSlider = document.getElementById("volumeSlider");
    const volumeValue = document.getElementById("volumeValue");
    const startScanBtn = document.getElementById("startScanBtn");
    const terminalLogs = document.getElementById("terminalLogs");
    const leadsList = document.getElementById("leadsList");
    
    // Filters & Search
    const searchInput = document.getElementById("searchInput");
    const filterSource = document.getElementById("filterSource");
    const filterCountry = document.getElementById("filterCountry");
    const filterService = document.getElementById("filterService");
    const filterStatus = document.getElementById("filterStatus");

    // Stats
    const statTotal = document.getElementById("statTotal");
    const statHighIntent = document.getElementById("statHighIntent");
    const statNoWebsite = document.getElementById("statNoWebsite");
    const statContacted = document.getElementById("statContacted");

    // Modal
    const pitchModal = document.getElementById("pitchModal");
    const closeModalBtn = document.getElementById("closeModalBtn");
    const modalBusinessName = document.getElementById("modalBusinessName");
    const modalSourceBadge = document.getElementById("modalSourceBadge");
    const modalAuditScore = document.getElementById("modalAuditScore");
    const modalPainPoints = document.getElementById("modalPainPoints");
    const modalPitchText = document.getElementById("modalPitchText");
    const copyPitchBtn = document.getElementById("copyPitchBtn");
    const modalEmailBtn = document.getElementById("modalEmailBtn");
    const modalWhatsAppBtn = document.getElementById("modalWhatsAppBtn");
    const markContactedBtn = document.getElementById("markContactedBtn");

    // Global Buttons
    const exportCsvBtn = document.getElementById("exportCsvBtn");
    const clearAllBtn = document.getElementById("clearAllBtn");

    // Slider change
    volumeSlider.addEventListener("input", (e) => {
        volumeValue.textContent = `${e.target.value} Leads`;
    });

    // Lead data is scraped from third-party pages - escape it before putting it into HTML
    function esc(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }
    function safeUrl(url) {
        return /^https?:\/\//i.test(url || "") ? esc(url) : "#";
    }

    // States / provinces per country
    const countryInput = document.getElementById("countryInput");
    const regionInput = document.getElementById("regionInput");
    const filterRegion = document.getElementById("filterRegion");
    let regionsByCountry = {};

    function fillRegionSelect(select, country, allLabel) {
        const current = select.value;
        select.innerHTML = "";
        const all = document.createElement("option");
        all.value = "all";
        all.textContent = allLabel;
        select.appendChild(all);
        const list = (country && country.toUpperCase() !== "ALL") ? (regionsByCountry[country.toUpperCase()] || []) : [];
        list.forEach(r => {
            const o = document.createElement("option");
            o.value = r;
            o.textContent = r;
            select.appendChild(o);
        });
        select.disabled = list.length === 0;
        if (list.includes(current)) select.value = current;
    }

    async function loadRegions() {
        try {
            const res = await fetch("/api/regions");
            regionsByCountry = (await res.json()).regions || {};
        } catch (err) {
            console.error("Error loading regions:", err);
        }
        fillRegionSelect(regionInput, countryInput.value, "🔄 Rotate through all states (new ones every scan)");
        fillRegionSelect(filterRegion, filterCountry.value, "All States");
    }

    countryInput.addEventListener("change", () => {
        fillRegionSelect(regionInput, countryInput.value, "🔄 Rotate through all states (new ones every scan)");
    });

    // Logging helper
    function addLog(msg, type = "normal") {
        const line = document.createElement("div");
        line.className = `log-line ${type}`;
        const time = new Date().toLocaleTimeString();
        line.textContent = `[${time}] ${msg}`;
        terminalLogs.appendChild(line);
        terminalLogs.scrollTop = terminalLogs.scrollHeight;
    }

    // Load initial leads & stats
    async function fetchLeads() {
        const s = searchInput.value.trim();
        const src = filterSource.value;
        const ctry = filterCountry ? filterCountry.value : "all";
        const srv = filterService.value;
        const st = filterStatus.value;
        const rgn = filterRegion ? filterRegion.value : "all";

        const params = new URLSearchParams();
        if (s) params.append("search", s);
        if (src !== "all") params.append("source", src);
        if (ctry !== "all") params.append("country", ctry);
        if (rgn !== "all") params.append("region", rgn);
        if (srv !== "all") params.append("service", srv);
        if (st !== "all") params.append("status", st);

        try {
            const res = await fetch(`/api/leads?${params.toString()}`);
            const data = await res.json();
            currentLeads = data.leads || [];
            renderLeads(currentLeads);
        } catch (err) {
            console.error("Error fetching leads:", err);
        }
    }

    async function fetchStats() {
        try {
            const res = await fetch("/api/stats");
            const data = await res.json();
            statTotal.textContent = data.total_leads;
            statHighIntent.textContent = data.high_intent_leads;
            statNoWebsite.textContent = data.no_website_leads;
            statContacted.textContent = data.contacted_leads;
        } catch (err) {
            console.error("Error fetching stats:", err);
        }
    }

    // Render lead cards
    function renderLeads(leads) {
        leadsList.innerHTML = "";
        if (!leads || leads.length === 0) {
            leadsList.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="inbox"></i>
                    <h3>No Leads Found</h3>
                    <p>Adjust your search filters or click "Launch Autonomous Scan" to harvest new client opportunities.</p>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        leads.forEach((l) => {
            const card = document.createElement("div");
            card.className = "lead-card";

            const painsHtml = (l.pain_points || [])
                .slice(0, 3)
                .map(p => `<span class="pain-chip"><i data-lucide="alert-circle" style="width:12px;height:12px"></i> ${esc(p)}</span>`)
                .join("");

            const sourceLabels = {
                local_verified: "Verified Local ✅",
                social_media: "Social & Founders 🌐",
                meta_ads: "Website Tech Revamp ⚡",
                ecom_funnel: "E-Commerce Revamp 🛍️",
                job_intent: "Hiring Company 💼",
                new_business: "Zero Website (Hot Lead 🔥)",
                app_store: "Mobile App Overhaul 📱"
            };

            const webHtml = l.has_website && l.website
                ? `<a href="${safeUrl(l.website)}" target="_blank" rel="noopener noreferrer" class="lead-website"><i data-lucide="globe" style="width:14px;height:14px"></i> ${esc(l.website.replace(/^https?:\/\/(www\.)?/, ''))}</a>`
                : `<span class="lead-website no-site"><i data-lucide="alert-triangle" style="width:14px;height:14px"></i> No Website Found</span>`;

            const phoneDigits = (l.phone || "").replace(/[^0-9+]/g, "");
            const waDigits = (l.whatsapp || "").replace(/[^0-9]/g, "");
            const sourceTag = (l.source || "").replace(/[^a-z_]/g, "");
            const statusTag = (l.status || "").replace(/[^a-z_]/g, "");

            card.innerHTML = `
                <div class="lead-main">
                    <div class="lead-top-row">
                        <span class="source-tag tag-${sourceTag}">${esc(sourceLabels[l.source] || l.source)}</span>
                        <h4 class="lead-title">${esc(l.business_name)}</h4>
                        ${l.category ? `<span class="contact-item" style="font-size:0.8rem;opacity:0.8;">${esc(l.category)}</span>` : ''}
                        ${webHtml}
                        <span class="status-badge status-${statusTag}">${esc(l.status)}</span>
                    </div>

                    <div class="lead-pains">
                        ${painsHtml}
                    </div>

                    <div class="lead-contact-strip">
                        <span class="contact-item"><i data-lucide="map-pin" style="width:14px;height:14px"></i> ${esc(l.location || 'Global')}</span>
                        ${l.email ? `<a href="mailto:${esc(l.email)}" class="contact-item" style="color:inherit;text-decoration:none;"><i data-lucide="mail" style="width:14px;height:14px"></i> ${esc(l.email)}</a>` : ''}
                        ${l.phone ? `
                            <span class="contact-item" style="color:var(--cyan);font-weight:600;display:inline-flex;align-items:center;gap:4px;">
                                <a href="tel:${phoneDigits}" title="Click to dial in CallHippo" style="color:inherit;text-decoration:none;">
                                    <i data-lucide="phone-call" style="width:14px;height:14px"></i> ${esc(l.phone)}
                                </a>
                                <button class="btn-copy-mini copy-phone-btn" title="Copy number for CallHippo" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:12px;padding:0 2px;">⧉</button>
                            </span>
                        ` : ''}
                        <span class="contact-item" style="color:var(--emerald);font-weight:600;"><i data-lucide="dollar-sign" style="width:14px;height:14px"></i> ${esc(l.budget_estimate || 'Unknown')}</span>
                    </div>
                </div>

                <div class="lead-actions" style="display:flex; flex-direction:column; gap:8px;">
                    <button class="btn btn-primary view-pitch-btn">
                        <i data-lucide="sparkles" style="width:16px;height:16px"></i>
                        <span>AI Pitch & Details</span>
                    </button>
                    <div style="display:flex; gap:6px;">
                        ${waDigits ? `
                            <a href="https://wa.me/${waDigits}?text=${encodeURIComponent(l.ai_pitch || 'Hi ' + l.business_name)}"
                               target="_blank" rel="noopener noreferrer" class="btn btn-whatsapp" style="flex:1; justify-content:center; padding:8px 10px; font-size:0.8rem; text-decoration:none;">
                                <i data-lucide="message-circle" style="width:14px;height:14px"></i> WhatsApp
                            </a>
                        ` : ''}
                        ${l.email ? `
                            <a href="mailto:${esc(l.email)}?subject=${encodeURIComponent('Quick question regarding ' + l.business_name)}&body=${encodeURIComponent(l.ai_pitch || '')}"
                               class="btn btn-outline" style="flex:1; justify-content:center; padding:8px 10px; font-size:0.8rem; text-decoration:none;">
                                <i data-lucide="mail" style="width:14px;height:14px"></i> Email
                            </a>
                        ` : ''}
                    </div>
                </div>
            `;

            // Attach events
            const btn = card.querySelector(".view-pitch-btn");
            btn.addEventListener("click", () => openPitchModal(l));
            const copyBtn = card.querySelector(".copy-phone-btn");
            if (copyBtn) {
                copyBtn.addEventListener("click", () => {
                    // US/CA: 10-digit national number; other countries: full international digits
                    const digits = phoneDigits.replace(/\D/g, "");
                    navigator.clipboard.writeText(digits.startsWith("1") && digits.length === 11 ? digits.slice(1) : digits);
                    copyBtn.innerText = "✓";
                    setTimeout(() => copyBtn.innerText = "⧉", 1500);
                });
            }

            leadsList.appendChild(card);
        });

        lucide.createIcons();
    }

    // Modal logic
    function openPitchModal(lead) {
        selectedLead = lead;
        modalBusinessName.textContent = lead.business_name;
        modalSourceBadge.textContent = lead.source.replace("_", " ").toUpperCase();
        modalSourceBadge.className = `source-tag tag-${lead.source}`;
        modalAuditScore.textContent = `Audit Score: ${lead.audit_score}/100`;

        modalPainPoints.innerHTML = (lead.pain_points || [])
            .map(p => `<li>${esc(p)}</li>`)
            .join("") + (lead.audit_summary ? `<li style="opacity:0.7;list-style:none;margin-top:6px;">${esc(lead.audit_summary)}</li>` : "");

        modalPitchText.value = lead.ai_pitch || "Generating customized pitch...";

        // Setup Email link
        const subject = encodeURIComponent(`Quick question regarding ${lead.business_name}`);
        const body = encodeURIComponent(lead.ai_pitch || "");
        modalEmailBtn.href = `mailto:${lead.email || ''}?subject=${subject}&body=${body}`;

        // Setup WhatsApp link
        // Only numbers confirmed as mobile / published WhatsApp - landlines can't receive WhatsApp
        let cleanPhone = (lead.whatsapp || "").replace(/[^0-9]/g, "");
        if (cleanPhone) {
            modalWhatsAppBtn.style.display = "inline-flex";
            modalWhatsAppBtn.href = `https://wa.me/${cleanPhone}?text=${body}`;
        } else {
            modalWhatsAppBtn.style.display = "none";
        }

        markContactedBtn.innerHTML = lead.status === "contacted" 
            ? `<i data-lucide="check-check"></i> <span>Contacted</span>` 
            : `<i data-lucide="check"></i> <span>Mark as Contacted</span>`;

        pitchModal.classList.add("active");
        lucide.createIcons();
    }

    closeModalBtn.addEventListener("click", () => {
        pitchModal.classList.remove("active");
    });

    pitchModal.addEventListener("click", (e) => {
        if (e.target === pitchModal) pitchModal.classList.remove("active");
    });

    // Copy Pitch button
    copyPitchBtn.addEventListener("click", () => {
        navigator.clipboard.writeText(modalPitchText.value);
        copyPitchBtn.innerHTML = `<i data-lucide="check" style="width:14px;height:14px"></i> Copied!`;
        lucide.createIcons();
        setTimeout(() => {
            copyPitchBtn.innerHTML = `<i data-lucide="copy" style="width:14px;height:14px"></i> <span>Copy Text</span>`;
            lucide.createIcons();
        }, 2000);
    });

    // Mark Contacted
    markContactedBtn.addEventListener("click", async () => {
        if (!selectedLead) return;
        const newStatus = selectedLead.status === "contacted" ? "new" : "contacted";
        try {
            await fetch(`/api/leads/${selectedLead.id}/status`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ status: newStatus })
            });
            selectedLead.status = newStatus;
            markContactedBtn.innerHTML = `<i data-lucide="check-check"></i> <span>Updated</span>`;
            fetchLeads();
            fetchStats();
        } catch (err) {
            console.error(err);
        }
    });

    // Handle Form Submit (Launch Scan)
    scanForm.addEventListener("submit", async (e) => {
        e.preventDefault();

        // While a scan runs the button is a Stop button
        if (scanRunning) {
            startScanBtn.disabled = true;
            await fetch("/api/scan/stop", { method: "POST" });
            return;
        }

        // Get selected sources
        const checkedSources = Array.from(document.querySelectorAll('input[name="source"]:checked')).map(cb => cb.value);
        if (checkedSources.length === 0) {
            alert("Please select at least one high-intent channel.");
            return;
        }

        const niche = document.getElementById("nicheInput").value;
        const country = countryInput.value;
        const region = regionInput.value;
        const limit = parseInt(volumeSlider.value);
        const apiKey = document.getElementById("apiKeyInput").value;

        startScanBtn.disabled = true;
        try {
            const res = await fetch("/api/scan/start", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ sources: checkedSources, niche, country, region, limit, gemini_api_key: apiKey })
            });
            const data = await res.json();
            if (!data.success) addLog(data.message || "Could not start the scan.", "warn");
            logSeq = 0;
            lastRefreshAt = 0;
            setScanUi(true);
            startPolling();
        } catch (err) {
            addLog(`Notice: ${err.message}`, "warn");
            setScanUi(false);
        }
    });

    // ---- Background scan: runs on the server until the target number of NEW leads is reached ----
    const scanTimerBadge = document.getElementById("scanTimerBadge");
    const timeRemainingSpan = document.getElementById("timeRemaining");
    const scanProgressBar = document.getElementById("scanProgressBar");
    const progressBarFill = document.getElementById("progressBarFill");
    let scanRunning = false;
    let pollTimer = null;
    let logSeq = 0;          // last server log line already shown
    let lastRefreshAt = 0;   // lead count when the list was last refreshed

    function fmtDuration(sec) {
        sec = Math.max(0, Math.round(sec || 0));
        const m = Math.floor(sec / 60);
        return m ? `${m}m ${sec % 60}s` : `${sec}s`;
    }

    function setScanUi(running) {
        scanRunning = running;
        startScanBtn.disabled = false;
        startScanBtn.innerHTML = running
            ? `<i data-lucide="square"></i> <span>Stop Scan (leads found so far are kept)</span>`
            : `<i data-lucide="crosshair"></i> <span>Launch Autonomous Scan</span>`;
        if (running) {
            if (scanTimerBadge) scanTimerBadge.style.display = "inline-flex";
            if (scanProgressBar) scanProgressBar.style.display = "block";
        }
        lucide.createIcons();
    }

    function renderScanStatus(s) {
        (s.log || []).forEach(entry => {
            addLog(entry.text, entry.kind);
            logSeq = Math.max(logSeq, entry.seq);
        });
        const pct = s.target ? Math.round((s.found / s.target) * 100) : 0;
        if (progressBarFill) progressBarFill.style.width = `${Math.max(3, Math.min(100, pct))}%`;
        if (timeRemainingSpan) {
            timeRemainingSpan.textContent = s.state === "running"
                ? `${s.found}/${s.target} leads · ~${fmtDuration(s.eta_seconds)} left · ${fmtDuration(s.elapsed)} elapsed`
                : `${s.found}/${s.target} leads · finished in ${fmtDuration(s.elapsed)}`;
        }
    }

    async function pollScan() {
        try {
            const s = await (await fetch(`/api/scan/status?since=${logSeq}`)).json();
            if (s.state === "idle") {
                clearInterval(pollTimer);
                pollTimer = null;
                setScanUi(false);
                return;
            }
            renderScanStatus(s);
            if (s.found - lastRefreshAt >= 5) {  // show new leads in the list as they arrive
                lastRefreshAt = s.found;
                fetchLeads();
                fetchStats();
            }
            if (s.state !== "running") await finishScan(s);
        } catch (err) {
            console.error("Scan status error:", err);
        }
    }

    function startPolling() {
        if (!pollTimer) pollTimer = setInterval(pollScan, 2000);
        pollScan();
    }

    async function finishScan(s) {
        clearInterval(pollTimer);
        pollTimer = null;
        setScanUi(false);
        if (s.found) addLog(`"Export Last Scan" downloads only these ${s.found} new leads.`, "info");
        refreshExportLabel();

        // Show the full list (new leads are at the top)
        if (searchInput) searchInput.value = "";
        [filterSource, filterCountry, filterService, filterStatus].forEach(sel => { if (sel) sel.value = "all"; });
        if (filterRegion) {
            fillRegionSelect(filterRegion, "all", "All States");
            filterRegion.value = "all";
        }
        await fetchLeads();
        await fetchStats();
        setTimeout(() => {
            if (scanRunning) return;
            if (scanTimerBadge) scanTimerBadge.style.display = "none";
            if (scanProgressBar) scanProgressBar.style.display = "none";
        }, 15000);
    }

    // Reopened the page while a scan is running? Re-attach to it.
    (async () => {
        try {
            const s = await (await fetch("/api/scan/status")).json();
            if (s.state === "running") {
                addLog("A scan is running - showing its live progress.", "info");
                setScanUi(true);
                startPolling();
            }
        } catch (err) {
            console.error(err);
        }
    })();

    // Search & Filter change events
    let debounceTimer;
    searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchLeads, 250);
    });

    filterSource.addEventListener("change", fetchLeads);
    if (filterCountry) filterCountry.addEventListener("change", () => {
        fillRegionSelect(filterRegion, filterCountry.value, "All States");
        fetchLeads();
    });
    if (filterRegion) filterRegion.addEventListener("change", fetchLeads);
    filterService.addEventListener("change", fetchLeads);
    filterStatus.addEventListener("change", fetchLeads);

    // Export CSV: default = only the new leads from the most recent scan (never re-export leads already worked)
    const exportCsvLabel = document.getElementById("exportCsvLabel");
    async function refreshExportLabel() {
        try {
            const d = await (await fetch("/api/last-scan")).json();
            if (exportCsvLabel) exportCsvLabel.textContent = d.scan_id ? `Export Last Scan (${d.count})` : "Export Last Scan";
        } catch (err) {
            console.error(err);
        }
    }
    exportCsvBtn.addEventListener("click", () => {
        window.location.href = "/api/export?scope=last";
    });
    const exportAllBtn = document.getElementById("exportAllBtn");
    if (exportAllBtn) {
        exportAllBtn.addEventListener("click", () => {
            window.location.href = "/api/export?scope=all";
        });
    }

    // Clear DB
    clearAllBtn.addEventListener("click", async () => {
        if (confirm("Are you sure you want to clear all leads from the database?")) {
            await fetch("/api/clear", { method: "POST" });
            fetchLeads();
            fetchStats();
            addLog("Database cleared by user.", "warn");
        }
    });

    // Initial Fetch
    refreshExportLabel();
    loadRegions();
    fetchLeads();
    fetchStats();
});
