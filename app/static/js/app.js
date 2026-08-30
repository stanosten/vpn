// ==========================================
// NodeChecker PRO - Frontend Logic
// ==========================================

let evtSource = null;
let currentNodes = [];

// DOM Elements
const statTotal = document.getElementById("statTotal");
const statLive = document.getElementById("statLive");
const statDead = document.getElementById("statDead");
const statLatency = document.getElementById("statLatency");

const progressSection = document.getElementById("progressSection");
const progressBar = document.getElementById("progressBar");
const progressPercent = document.getElementById("progressPercent");
const progressCounts = document.getElementById("progressCounts");
const progressTime = document.getElementById("progressTime");
const progressMessage = document.getElementById("progressMessage");

const nodesTableBody = document.getElementById("nodesTableBody");
const searchInput = document.getElementById("searchInput");
const filterStatus = document.getElementById("filterStatus");
const filterProtocol = document.getElementById("filterProtocol");
const filterLatency = document.getElementById("filterLatency");

const btnStartCheck = document.getElementById("btnStartCheck");
const btnOpenImport = document.getElementById("btnOpenImport");
const btnClearDb = document.getElementById("btnClearDb");
const btnExportMenu = document.getElementById("btnExportMenu");
const exportMenu = document.getElementById("exportMenu");

// Modal Elements
const importModal = document.getElementById("importModal");
const btnCloseModal = document.getElementById("btnCloseModal");
const btnCancelModal = document.getElementById("btnCancelModal");
const modalOverlay = document.getElementById("modalOverlay");
const btnConfirmImport = document.getElementById("btnConfirmImport");
const modalTextInput = document.getElementById("modalTextInput");
const modalUrlInput = document.getElementById("modalUrlInput");
const chkUseDefault = document.getElementById("chkUseDefault");

// Initialize on Load
document.addEventListener("DOMContentLoaded", () => {
    initSSE();
    loadStats();
    loadNodes();
    setupEventListeners();
});

function setupEventListeners() {
    btnStartCheck.addEventListener("click", () => startBatchCheck());
    btnOpenImport.addEventListener("click", () => openModal());
    btnCloseModal.addEventListener("click", () => closeModal());
    btnCancelModal.addEventListener("click", () => closeModal());
    modalOverlay.addEventListener("click", () => closeModal());

    btnConfirmImport.addEventListener("click", () => {
        const rawText = modalTextInput.value.trim();
        const url = modalUrlInput.value.trim();
        const useDefault = chkUseDefault.checked;

        closeModal();
        startBatchCheck({
            raw_text: rawText || null,
            subscription_urls: url ? [url] : null,
            use_default_sources: useDefault,
        });
    });

    // Filters
    let searchDebounce = null;
    searchInput.addEventListener("input", () => {
        clearTimeout(searchDebounce);
        searchDebounce = setTimeout(loadNodes, 250);
    });

    filterStatus.addEventListener("change", loadNodes);
    filterProtocol.addEventListener("change", loadNodes);
    filterLatency.addEventListener("change", loadNodes);

    // Export dropdown toggle
    btnExportMenu.addEventListener("click", (e) => {
        e.stopPropagation();
        exportMenu.classList.toggle("show");
    });
    document.addEventListener("click", () => exportMenu.classList.remove("show"));

    // Clear DB
    btnClearDb.addEventListener("click", async () => {
        if (confirm("Are you sure you want to clear all nodes and statistics?")) {
            await fetch("/api/nodes", { method: "DELETE" });
            showToast("All nodes cleared.");
            loadStats();
            loadNodes();
        }
    });
}

function openModal() {
    importModal.classList.add("active");
}

function closeModal() {
    importModal.classList.remove("active");
}

// Real-time SSE Progress Listener
function initSSE() {
    if (evtSource) {
        evtSource.close();
    }
    evtSource = new EventSource("/api/check/progress");

    evtSource.addEventListener("init", (e) => {
        const progress = JSON.parse(e.data);
        updateProgressUI(progress);
    });

    evtSource.addEventListener("progress", (e) => {
        const progress = JSON.parse(e.data);
        updateProgressUI(progress);
    });

    evtSource.addEventListener("node_checked", (e) => {
        const payload = JSON.parse(e.data);
        updateProgressUI(payload.progress);
        // Dynamically prepend node or refresh table
        loadStats();
    });

    evtSource.addEventListener("complete", (e) => {
        const progress = JSON.parse(e.data);
        updateProgressUI(progress);
        showToast("✓ Validation batch completed!");
        loadStats();
        loadNodes();
        setTimeout(() => {
            if (!progress.is_running) {
                progressSection.style.display = "none";
            }
        }, 4000);
    });
}

function updateProgressUI(p) {
    if (!p) return;
    if (p.is_running) {
        progressSection.style.display = "block";
        progressBar.style.width = `${p.percent}%`;
        progressPercent.textContent = `${p.percent}%`;
        progressCounts.textContent = `${p.checked} / ${p.total}`;
        progressTime.textContent = `${p.elapsed_seconds}s`;
        progressMessage.textContent = `Scanning: ${p.live_count} Live, ${p.dead_count} Dead`;
        btnStartCheck.disabled = true;
        btnStartCheck.innerHTML = `<span class="spinner"></span> Scanning...`;
    } else {
        btnStartCheck.disabled = false;
        btnStartCheck.innerHTML = `<span class="icon">🚀</span> Run Check`;
    }
}

// API Calls
async function startBatchCheck(params = {}) {
    try {
        const payload = {
            raw_text: params.raw_text || null,
            subscription_urls: params.subscription_urls || null,
            use_default_sources: params.use_default_sources !== false,
            auto_export: true,
            auto_git_sync: false,
        };

        const res = await fetch("/api/check/run", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });

        if (res.ok) {
            const data = await res.json();
            showToast(`🚀 Started scanning ${data.total_nodes_queued} nodes!`);
            progressSection.style.display = "block";
        } else {
            const err = await res.json();
            showToast(`⚠️ ${err.detail || "Failed to start check"}`);
        }
    } catch (e) {
        showToast(`Error: ${e.message}`);
    }
}

async function loadStats() {
    try {
        const res = await fetch("/api/stats");
        if (res.ok) {
            const stats = await res.json();
            statTotal.textContent = stats.total_nodes || 0;
            statLive.textContent = stats.live_nodes || 0;
            statDead.textContent = stats.dead_nodes || 0;
            statLatency.textContent = `${stats.avg_latency_ms || 0} ms`;
        }
    } catch (e) {
        console.error("Failed to load stats", e);
    }
}

async function loadNodes() {
    try {
        const params = new URLSearchParams();
        const status = filterStatus.value;
        if (status === "alive") params.append("is_alive", "true");
        if (status === "dead") params.append("is_alive", "false");

        const proto = filterProtocol.value;
        if (proto) params.append("protocol", proto);

        const lat = filterLatency.value;
        if (lat) params.append("max_latency", lat);

        const search = searchInput.value.trim();
        if (search) params.append("search", search);

        params.append("limit", "200");

        const res = await fetch(`/api/nodes?${params.toString()}`);
        if (res.ok) {
            const data = await res.json();
            currentNodes = data.nodes || [];
            renderNodesTable(currentNodes);
        }
    } catch (e) {
        console.error("Failed to load nodes", e);
    }
}

function renderNodesTable(nodes) {
    if (!nodes || nodes.length === 0) {
        nodesTableBody.innerHTML = `
            <tr class="empty-row">
                <td colspan="8">No nodes found matching the selected filters.</td>
            </tr>
        `;
        return;
    }

    nodesTableBody.innerHTML = nodes.map(n => {
        const node = n.node;
        const geo = n.geo || {};
        const isAlive = n.is_alive;
        const latency = n.latency_ms;

        let latClass = "latency-dead";
        let latText = "Offline";
        if (isAlive) {
            if (latency < 150) latClass = "latency-fast";
            else if (latency < 400) latClass = "latency-med";
            else latClass = "latency-slow";
            latText = `${latency} ms`;
        }

        const protoClass = `proto-${node.protocol.toLowerCase()}`;
        const statusHtml = isAlive 
            ? `<span class="status-dot live">🟢 Live</span>`
            : `<span class="status-dot dead">🔴 Dead</span>`;

        return `
            <tr>
                <td>${statusHtml}</td>
                <td><span class="badge-proto ${protoClass}">${escapeHtml(node.protocol)}</span></td>
                <td><span class="endpoint-code">${escapeHtml(node.host)}:${node.port}</span></td>
                <td><span class="latency-badge ${latClass}">${latText}</span></td>
                <td>
                    <div class="geo-info">
                        <span class="country-flag">${geo.flag || "🌐"}</span>
                        <span>${escapeHtml(geo.country || "Unknown")}</span>
                    </div>
                </td>
                <td>
                    <div class="isp-text" title="${escapeHtml(geo.isp || '')}">${escapeHtml(geo.isp || "—")}</div>
                </td>
                <td style="color: var(--text-muted); font-size: 13px;">
                    ${escapeHtml(node.tag || "—")}
                </td>
                <td>
                    <button class="btn-icon" onclick="copyNode('${escapeHtml(node.raw_input)}')">📋 Copy</button>
                    <button class="btn-icon" onclick="recheckNode('${escapeHtml(node.raw_input)}')">🔄</button>
                </td>
            </tr>
        `;
    }).join("");
}

// Helper: Copy Node String
window.copyNode = (raw) => {
    navigator.clipboard.writeText(raw).then(() => {
        showToast("✓ Copied node to clipboard!");
    }).catch(() => {
        showToast("Error copying to clipboard");
    });
};

// Helper: Quick Re-check Single Node
window.recheckNode = async (raw) => {
    showToast(`Checking ${raw}...`);
    try {
        const res = await fetch("/api/check/single", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target: raw })
        });
        if (res.ok) {
            const data = await res.json();
            const status = data.is_alive ? `🟢 LIVE (${data.latency_ms}ms)` : `🔴 DEAD`;
            showToast(`Result for ${data.node.endpoint}: ${status}`);
            loadStats();
            loadNodes();
        }
    } catch (e) {
        showToast(`Error: ${e.message}`);
    }
};

function showToast(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 3000);
}

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
