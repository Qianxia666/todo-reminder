const text = {
    loadingInitial: "\u6b63\u5728\u52a0\u8f7d\u4efb\u52a1...",
    loadingManual: "\u6b63\u5728\u5237\u65b0\u4efb\u52a1...",
    fetchError: "\u65e0\u6cd5\u83b7\u53d6\u4efb\u52a1\u5217\u8868",
    loadError: "\u52a0\u8f7d\u4efb\u52a1\u5931\u8d25",
    empty: "\u6682\u65e0\u4efb\u52a1\uff0c\u8bf7\u524d\u5f80\u4e3b\u63a7\u5236\u53f0\u521b\u5efa\u4efb\u52a1\u3002",
    startLabel: "\u5f00\u59cb",
    endLabel: "\u7ed3\u675f",
    endUnset: "\u672a\u8bbe\u7f6e",
    startSent: "\u5f00\u59cb\u63d0\u9192\u5df2\u53d1\u9001",
    startPending: "\u7b49\u5f85\u5f00\u59cb\u63d0\u9192",
    endSent: "\u7ed3\u675f\u63d0\u9192\u5df2\u53d1\u9001",
    endPending: "\u7b49\u5f85\u7ed3\u675f\u63d0\u9192",
    endMissing: "\u672a\u8bbe\u7f6e\u7ed3\u675f\u63d0\u9192",
    daily: "\u6bcf\u65e5\u63d0\u9192",
    single: "\u5355\u6b21\u63d0\u9192",
    allDay: "\u5168\u5929",
    notSet: "\u672a\u8bbe\u7f6e",
};

const state = {
    tasks: [],
};

const selectors = {
    list: document.getElementById("timeline-list"),
    status: document.getElementById("timeline-status"),
    count: document.getElementById("timeline-count"),
    refresh: document.getElementById("refresh-timeline"),
};

const BEIJING_TZ = "Asia/Shanghai";
const beijingDateFormatter = new Intl.DateTimeFormat("en-CA", {
    timeZone: BEIJING_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
});
const beijingTimeFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: BEIJING_TZ,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
});

init();

function init() {
    if (selectors.refresh) {
        selectors.refresh.addEventListener("click", () => loadTasks(true));
    }
    loadTasks(false);
}

async function loadTasks(isManual) {
    if (selectors.refresh) {
        selectors.refresh.disabled = true;
        selectors.refresh.setAttribute("aria-busy", "true");
    }
    setStatus(isManual ? text.loadingManual : text.loadingInitial, false);
    try {
        const response = await fetch("/api/tasks");
        if (!response.ok) throw new Error(text.fetchError);
        const data = await response.json();
        state.tasks = data.slice().sort(sortByStartDate);
        selectors.count.textContent = state.tasks.length;
        renderTimeline();
        hideStatus();
    } catch (error) {
        selectors.list.innerHTML = "";
        selectors.count.textContent = "0";
        setStatus(error.message || text.loadError, true);
    } finally {
        if (selectors.refresh) {
            selectors.refresh.disabled = false;
            selectors.refresh.removeAttribute("aria-busy");
        }
    }
}

function sortByStartDate(a, b) {
    const startA = parseDateValue(a.start_at);
    const startB = parseDateValue(b.start_at);
    if (startA !== startB) return startA - startB;
    const endA = parseDateValue(a.end_at || a.start_at);
    const endB = parseDateValue(b.end_at || b.start_at);
    if (endA !== endB) return endA - endB;
    return Number(a.id || 0) - Number(b.id || 0);
}

function parseDateValue(value) {
    if (!value) return Number.MAX_SAFE_INTEGER;
    const timestamp = new Date(value).getTime();
    return Number.isNaN(timestamp) ? Number.MAX_SAFE_INTEGER : timestamp;
}

function renderTimeline() {
    if (!state.tasks.length) {
        selectors.list.innerHTML = `
            <div class="timeline-empty" role="note">
                ${text.empty}
            </div>
        `;
        return;
    }
    selectors.list.innerHTML = state.tasks.map(renderTimelineItem).join("");
}

function renderTimelineItem(task) {
    const startLabel = formatDateDisplay(task.start_at, task.start_all_day);
    const endLabel = task.end_at ? formatDateDisplay(task.end_at, task.end_all_day) : text.endUnset;
    const description = task.description
        ? `<p class="timeline-description">${escapeHtml(task.description)}</p>`
        : "";
    const startBadge = task.start_notified
        ? `<span class="badge success">${text.startSent}</span>`
        : `<span class="badge pending">${text.startPending}</span>`;
    const endBadge = task.end_at
        ? task.end_notified
            ? `<span class="badge success">${text.endSent}</span>`
            : `<span class="badge pending">${text.endPending}</span>`
        : `<span class="badge muted">${text.endMissing}</span>`;
    const reminderLabel = task.daily_reminder ? text.daily : text.single;

    return `
        <article class="timeline-item" role="listitem">
            <header class="timeline-item-head">
                <div>
                    <p class="timeline-date">${startLabel}</p>
                    <h3 class="timeline-title">${escapeHtml(task.title)}</h3>
                </div>
                <span class="timeline-pill">${reminderLabel}</span>
            </header>
            ${description}
            <dl class="timeline-meta">
                <div>
                    <dt>${text.startLabel}</dt>
                    <dd>${startLabel}</dd>
                </div>
                <div>
                    <dt>${text.endLabel}</dt>
                    <dd>${endLabel}</dd>
                </div>
            </dl>
            <div class="timeline-badges">
                ${startBadge}${endBadge}
            </div>
        </article>
    `;
}

function formatDateDisplay(value, allDay) {
    if (!value) return text.notSet;
    const dateParts = getBeijingDateParts(value);
    if (!dateParts) return text.notSet;
    const base = `${dateParts.year}-${dateParts.month}-${dateParts.day}`;
    if (allDay) return `${base} ${text.allDay}`;
    const timeParts = getBeijingTimeParts(value);
    return timeParts ? `${base} ${timeParts.hour}:${timeParts.minute}` : base;
}

function getBeijingDateParts(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const parts = beijingDateFormatter.formatToParts(date);
    const year = parts.find((part) => part.type === "year")?.value;
    const month = parts.find((part) => part.type === "month")?.value;
    const day = parts.find((part) => part.type === "day")?.value;
    if (!year || !month || !day) return null;
    return { year, month, day };
}

function getBeijingTimeParts(value) {
    if (!value) return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const parts = beijingTimeFormatter.formatToParts(date);
    const hour = parts.find((part) => part.type === "hour")?.value;
    const minute = parts.find((part) => part.type === "minute")?.value;
    if (!hour || !minute) return null;
    return { hour, minute };
}

function escapeHtml(content) {
    return String(content)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function setStatus(message, isError) {
    if (!selectors.status) return;
    selectors.status.textContent = message;
    selectors.status.classList.toggle("error", Boolean(isError));
    selectors.status.classList.toggle("hidden", !message);
}

function hideStatus() {
    if (!selectors.status) return;
    selectors.status.textContent = "";
    selectors.status.classList.add("hidden");
    selectors.status.classList.remove("error");
}
