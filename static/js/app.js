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

        const params = new URLSearchParams();
        if (s) params.append("search", s);
        if (src !== "all") params.append("source", src);
        if (ctry !== "all") params.append("country", ctry);
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
                .map(p => `<span class="pain-chip"><i data-lucide="alert-circle" style="width:12px;height:12px"></i> ${p}</span>`)
                .join("");

            const sourceLabels = {
                social_media: "Social & Founders 🌐",
                meta_ads: "Website Tech Revamp ⚡",
                job_intent: "E-Commerce Revamp 🛍️",
                new_business: "Zero Website (Hot Lead 🔥)",
                app_store: "Mobile App Overhaul 📱"
            };

            const webHtml = l.has_website && l.website 
                ? `<a href="${l.website}" target="_blank" class="lead-website"><i data-lucide="globe" style="width:14px;height:14px"></i> ${l.website.replace(/^https?:\/\/(www\.)?/, '')}</a>`
                : `<span class="lead-website no-site"><i data-lucide="alert-triangle" style="width:14px;height:14px"></i> Zero Website (High Priority)</span>`;

            card.innerHTML = `
                <div class="lead-main">
                    <div class="lead-top-row">
                        <span class="source-tag tag-${l.source}">${sourceLabels[l.source] || l.source}</span>
                        <h4 class="lead-title">${l.business_name}</h4>
                        ${webHtml}
                        <span class="status-badge status-${l.status}">${l.status}</span>
                    </div>

                    <div class="lead-pains">
                        ${painsHtml}
                    </div>

                    <div class="lead-contact-strip">
                        <span class="contact-item"><i data-lucide="map-pin" style="width:14px;height:14px"></i> ${l.location || 'Global'}</span>
                        ${l.email ? `<a href="mailto:${l.email}" class="contact-item" style="color:inherit;text-decoration:none;"><i data-lucide="mail" style="width:14px;height:14px"></i> ${l.email}</a>` : ''}
                        ${l.phone ? `
                            <span class="contact-item" style="color:var(--cyan);font-weight:600;display:inline-flex;align-items:center;gap:4px;">
                                <a href="tel:${l.phone.replace(/[^0-9+]/g, '')}" title="Click to dial in CallHippo" style="color:inherit;text-decoration:none;">
                                    <i data-lucide="phone-call" style="width:14px;height:14px"></i> ${l.phone}
                                </a>
                                <button class="btn-copy-mini" title="Copy clean 10-digit number for CallHippo" onclick="navigator.clipboard.writeText('${l.phone.replace(/[^0-9]/g, '').slice(-10)}'); this.innerText='✓'; setTimeout(()=>this.innerText='⧉', 1500);" style="background:transparent;border:none;color:var(--text-muted);cursor:pointer;font-size:12px;padding:0 2px;">⧉</button>
                            </span>
                        ` : ''}
                        <span class="contact-item" style="color:var(--emerald);font-weight:600;"><i data-lucide="dollar-sign" style="width:14px;height:14px"></i> ${l.budget_estimate || 'Active Budget'}</span>
                    </div>
                </div>

                <div class="lead-actions" style="display:flex; flex-direction:column; gap:8px;">
                    <button class="btn btn-primary view-pitch-btn" data-id="${l.id}">
                        <i data-lucide="sparkles" style="width:16px;height:16px"></i>
                        <span>AI Pitch & Details</span>
                    </button>
                    <div style="display:flex; gap:6px;">
                        ${(l.whatsapp || l.phone) ? `
                            <a href="https://wa.me/${(l.whatsapp || l.phone).replace(/[^0-9]/g, '')}?text=${encodeURIComponent(l.ai_pitch || 'Hi ' + l.business_name)}" 
                               target="_blank" class="btn btn-whatsapp" style="flex:1; justify-content:center; padding:8px 10px; font-size:0.8rem; text-decoration:none;">
                                <i data-lucide="message-circle" style="width:14px;height:14px"></i> WhatsApp
                            </a>
                        ` : ''}
                        ${l.email ? `
                            <a href="mailto:${l.email}?subject=${encodeURIComponent('Quick question regarding ' + l.business_name)}&body=${encodeURIComponent(l.ai_pitch || '')}" 
                               class="btn btn-outline" style="flex:1; justify-content:center; padding:8px 10px; font-size:0.8rem; text-decoration:none;">
                                <i data-lucide="mail" style="width:14px;height:14px"></i> Email
                            </a>
                        ` : ''}
                    </div>
                </div>
            `;

            // Attach event
            const btn = card.querySelector(".view-pitch-btn");
            btn.addEventListener("click", () => openPitchModal(l));

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
            .map(p => `<li>${p}</li>`)
            .join("");

        modalPitchText.value = lead.ai_pitch || "Generating customized pitch...";

        // Setup Email link
        const subject = encodeURIComponent(`Quick question regarding ${lead.business_name}`);
        const body = encodeURIComponent(lead.ai_pitch || "");
        modalEmailBtn.href = `mailto:${lead.email || ''}?subject=${subject}&body=${body}`;

        // Setup WhatsApp link
        let cleanPhone = (lead.whatsapp || lead.phone || "").replace(/[^0-9]/g, "");
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

        // Get selected sources
        const checkedSources = Array.from(document.querySelectorAll('input[name="source"]:checked')).map(cb => cb.value);
        if (checkedSources.length === 0) {
            alert("Please select at least one high-intent channel.");
            return;
        }

        const niche = document.getElementById("nicheInput").value;
        const country = document.getElementById("countryInput").value;
        const limit = parseInt(volumeSlider.value);
        const apiKey = document.getElementById("apiKeyInput").value;

        // UI state
        startScanBtn.disabled = true;
        startScanBtn.innerHTML = `<i data-lucide="loader-2" class="spin"></i> <span>Autonomous Scanning Active...</span>`;
        lucide.createIcons();

        addLog(`Initiating multi-channel scan for [${niche}] in [${country}]...`, "info");
        addLog(`Targeting channels: ${checkedSources.join(", ")}`, "normal");

        const progressMsgs = [
            "Connecting to public search registries & social endpoints...",
            "Discovering active businesses without websites...",
            "Running technical speed & mobile audits on candidate sites...",
            "Extracting verified WhatsApp numbers & business emails...",
            "Generating custom AI outreach pitches for verified leads..."
        ];
        let pIdx = 0;
        const progressTimer = setInterval(() => {
            if (pIdx < progressMsgs.length) {
                addLog(progressMsgs[pIdx], "normal");
                pIdx++;
            }
        }, 3000);

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 60000);

            const res = await fetch("/api/scan", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    sources: checkedSources,
                    niche: niche,
                    country: country,
                    limit: limit,
                    gemini_api_key: apiKey
                }),
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            const data = await res.json();
            if (data.success) {
                addLog(`Success! Extracted and enriched ${data.harvested_count} fresh high-intent leads.`, "success");
                
                // Sync filter with scanned country
                if (searchInput) searchInput.value = "";
                if (filterSource) filterSource.value = "all";
                if (filterCountry) filterCountry.value = (country || "ALL").toUpperCase() === "ALL" ? "all" : country.toUpperCase();
                if (filterService) filterService.value = "all";
                if (filterStatus) filterStatus.value = "all";

                await fetchLeads();

                if (data.stats) {
                    statTotal.textContent = data.stats.total_leads || 0;
                    statHighIntent.textContent = data.stats.high_intent_leads || 0;
                    statNoWebsite.textContent = data.stats.no_website_leads || 0;
                    statContacted.textContent = data.stats.contacted_leads || 0;
                } else {
                    await fetchStats();
                }
            } else {
                addLog(`Scan finished with warning: ${data.message || 'Unknown response'}`, "warn");
            }
        } catch (err) {
            if (err.name === 'AbortError') {
                addLog("Scan took too long to complete. Please try with fewer channels or a specific niche.", "warn");
            } else {
                addLog(`Connection notice: ${err.message}`, "warn");
            }
        } finally {
            clearInterval(progressTimer);
            startScanBtn.disabled = false;
            startScanBtn.innerHTML = `<i data-lucide="crosshair"></i> <span>Launch Autonomous Scan</span>`;
            lucide.createIcons();
        }
    });

    // Search & Filter change events
    let debounceTimer;
    searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(fetchLeads, 250);
    });

    filterSource.addEventListener("change", fetchLeads);
    if (filterCountry) filterCountry.addEventListener("change", fetchLeads);
    filterService.addEventListener("change", fetchLeads);
    filterStatus.addEventListener("change", fetchLeads);

    // Export CSV
    exportCsvBtn.addEventListener("click", () => {
        window.location.href = "/api/export";
    });

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
    fetchLeads();
    fetchStats();
});
