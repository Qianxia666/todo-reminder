const state = {
    tasks: [],
    editingId: null,
    settings: {
        webhook_url: "",
        daily_reminder_time: "09:00",
    },
};

const selectors = {
    title: document.getElementById("title"),
    description: document.getElementById("description"),
    startDateTime: document.getElementById("start-datetime"),
    startDate: document.getElementById("start-date"),
    endDateTime: document.getElementById("end-datetime"),
    endDate: document.getElementById("end-date"),
    taskStatus: document.getElementById("task-status"),
    settingsStatus: document.getElementById("settings-status"),
    deadline: document.getElementById("deadline-minutes"),
    webhook: document.getElementById("webhook"),
    dailyReminder: document.getElementById("daily-reminder"),
    dailyReminderTime: document.getElementById("daily-reminder-time"),
    cancelEdit: document.getElementById("cancel-edit"),
    submitTask: document.getElementById("submit-task"),
    testWebhook: document.getElementById("test-webhook"),
    tableBody: document.getElementById("task-table-body"),
    metricTotalTasks: document.getElementById("metric-total-tasks"),
    metricPendingStart: document.getElementById("metric-pending-start"),
    metricPendingEnd: document.getElementById("metric-pending-end"),
    metricWebhookState: document.getElementById("metric-webhook-state"),
    metricDailyTime: document.getElementById("metric-daily-time"),
    taskHeading: document.querySelector("#task-panel h2"),
    saveSettings: document.getElementById("save-settings"),
};

const startModeRadios = document.querySelectorAll('input[name="start-mode"]');
const endModeRadios = document.querySelectorAll('input[name="end-mode"]');

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


const uiText = {
    table: {
        empty: "暂无任务，请先创建提醒",
        task: "任务",
        start: "开始",
        end: "结束",
        status: "提醒状态",
        reminder: "提醒类型",
        actions: "操作",
        edit: "编辑",
        delete: "删除",
    },
    badges: {
        startDone: "已推送开始提醒",
        startPending: "等待开始提醒",
        endDone: "已推送结束提醒",
        endPending: "等待结束提醒",
        endMissing: "未设结束提醒",
    },
    reminderModes: {
        daily: "每日提醒",
        single: "单次提醒",
    },
};


init();

function parseSortTime(value) {
    if (!value) return Number.MAX_SAFE_INTEGER;
    const timestamp = new Date(value).getTime();
    return Number.isNaN(timestamp) ? Number.MAX_SAFE_INTEGER : timestamp;
}

function sortTasks(a, b) {
    const startDiff = parseSortTime(a.start_at) - parseSortTime(b.start_at);
    if (startDiff !== 0) return startDiff;
    const endDiff = parseSortTime(a.end_at || a.start_at) - parseSortTime(b.end_at || b.start_at);
    if (endDiff !== 0) return endDiff;
    return Number(a.id || 0) - Number(b.id || 0);
}

function formatApiErrorDetail(detail) {
    if (Array.isArray(detail)) {
        return detail
            .map((item) => {
                if (typeof item === "string") return item;
                if (!item || typeof item !== "object") return String(item ?? "");
                const path = Array.isArray(item.loc) ? item.loc.filter((segment) => segment !== "body").join(" / ") : "";
                const message = item.msg || item.message || "请求参数不合法";
                return path ? `${path}：${message}` : message;
            })
            .filter(Boolean)
            .join("；");
    }
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object") {
        return detail.message || detail.error || "请求失败";
    }
    return "";
}

async function readApiErrorMessage(response, fallbackMessage) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail ?? payload?.message ?? payload?.error;
    return formatApiErrorDetail(detail) || fallbackMessage;
}

function getErrorMessage(error, fallbackMessage) {
    return error instanceof Error && error.message ? error.message : fallbackMessage;
}

function updateOverviewMetrics() {
    if (!selectors.metricTotalTasks) return;
    const pendingStartCount = state.tasks.filter((task) => !task.start_notified).length;
    const pendingEndCount = state.tasks.filter((task) => task.end_at && !task.end_notified).length;
    const webhookConfigured = Boolean(state.settings.webhook_url?.trim());

    selectors.metricTotalTasks.textContent = String(state.tasks.length);
    selectors.metricPendingStart.textContent = String(pendingStartCount);
    selectors.metricPendingEnd.textContent = String(pendingEndCount);
    selectors.metricWebhookState.textContent = webhookConfigured ? "已启用" : "未配置";
    selectors.metricWebhookState.classList.toggle("is-muted", !webhookConfigured);
    selectors.metricDailyTime.textContent = `每日提醒时间：${state.settings.daily_reminder_time || "09:00"}`;
}

function init() {
    document.getElementById("task-form").addEventListener("submit", handleTaskSubmit);
    document.getElementById("settings-form").addEventListener("submit", handleSettingsSubmit);
    selectors.testWebhook.addEventListener("click", handleTestWebhook);
    selectors.cancelEdit.addEventListener("click", resetTaskForm);
    startModeRadios.forEach((radio) => radio.addEventListener("change", syncStartModeVisibility));
    endModeRadios.forEach((radio) => radio.addEventListener("change", syncEndModeVisibility));
    syncStartModeVisibility();
    syncEndModeVisibility();
    loadSettings();
    loadTasks();
}

function syncStartModeVisibility() {
    const mode = getSelectedRadioValue("start-mode");
    document.getElementById("start-datetime-field").classList.toggle("hidden", mode !== "minute");
    document.getElementById("start-date-field").classList.toggle("hidden", mode !== "day");
}

function syncEndModeVisibility() {
    const mode = getSelectedRadioValue("end-mode");
    document.getElementById("end-datetime-field").classList.toggle("hidden", mode !== "minute");
    document.getElementById("end-date-field").classList.toggle("hidden", mode !== "day");
}

function getSelectedRadioValue(name) {
    const checked = document.querySelector(`input[name="${name}"]:checked`);
    return checked ? checked.value : null;
}

async function loadTasks(options = {}) {
    const { preserveTaskStatus = false } = options;
    try {
        const response = await fetch("/api/tasks");
        if (!response.ok) throw new Error(await readApiErrorMessage(response, "无法获取任务"));
        state.tasks = (await response.json()).slice().sort(sortTasks);
        renderTasks();
        updateOverviewMetrics();
        if (!preserveTaskStatus) {
            setTaskStatus("", false);
        }
    } catch (error) {
        setTaskStatus(getErrorMessage(error, "加载任务失败"), true);
    }
}


function renderTasks() {
    if (!state.tasks.length) {
        selectors.tableBody.innerHTML = `<tr class="empty-row"><td colspan="6">${uiText.table.empty}</td></tr>`;
        return;
    }
    selectors.tableBody.innerHTML = state.tasks
        .map((task) => {
            const safeTitle = escapeHtml(task.title);
            const description = task.description ? `<div class="description">${escapeHtml(task.description)}</div>` : "";
            return `
            <tr>
                <td data-label="${uiText.table.task}" class="task-cell">
                    <div>${safeTitle}</div>
                    ${description}
                </td>
                <td data-label="${uiText.table.start}">${formatDateDisplay(task.start_at, task.start_all_day)}</td>
                <td data-label="${uiText.table.end}">${formatDateDisplay(task.end_at, task.end_all_day)}</td>
                <td data-label="${uiText.table.status}">${renderBadges(task)}</td>
                <td data-label="${uiText.table.reminder}">${renderReminderMode(task)}</td>
                <td class="actions" data-label="${uiText.table.actions}">
                    <button type="button" class="secondary" data-edit="${task.id}" aria-label="编辑${safeTitle}">${uiText.table.edit}</button>
                    <button type="button" class="danger" data-delete="${task.id}" aria-label="删除${safeTitle}">${uiText.table.delete}</button>
                </td>
            </tr>`;
        })
        .join("");
    selectors.tableBody.querySelectorAll("button[data-edit]").forEach((button) => {
        button.addEventListener("click", () => beginEditTask(Number(button.dataset.edit)));
    });
    selectors.tableBody.querySelectorAll("button[data-delete]").forEach((button) => {
        button.addEventListener("click", () => deleteTask(Number(button.dataset.delete)));
    });
}


function renderBadges(task) {
    const start = task.start_notified
        ? `<span class="badge success">${uiText.badges.startDone}</span>`
        : `<span class="badge pending">${uiText.badges.startPending}</span>`;
    let end = `<span class="badge muted">${uiText.badges.endMissing}</span>`;
    if (task.end_at) {
        end = task.end_notified
            ? `<span class="badge success">${uiText.badges.endDone}</span>`
            : `<span class="badge pending">${uiText.badges.endPending}</span>`;
    }
    return `${start}${end}`;
}

function renderReminderMode(task) {
    return task.daily_reminder
        ? `<span class="badge info">${uiText.reminderModes.daily}</span>`
        : `<span class="badge subtle">${uiText.reminderModes.single}</span>`;
}



function formatBeijingDate(value) {
    const parts = getBeijingDateParts(value);
    if (!parts) return "";
    return `${parts.year}-${parts.month}-${parts.day}`;
}

function formatBeijingTime(value) {
    const parts = getBeijingTimeParts(value);
    if (!parts) return "";
    return `${parts.hour}:${parts.minute}`;
}

function formatDateDisplay(value, allDay) {
    if (!value) return "--";
    const datePart = formatBeijingDate(value);
    if (!datePart) return "--";
    if (allDay) {
        return `${datePart} 全天`;
    }
    const timePart = formatBeijingTime(value);
    return timePart ? `${datePart} ${timePart}` : datePart;
}

function escapeHtml(text) {
    return String(text ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function toBeijingComparableTime(value, mode, isEnd) {
    if (!value) return null;
    const suffix = mode === "day"
        ? (isEnd ? "T23:59:00+08:00" : "T00:00:00+08:00")
        : ":00+08:00";
    const isoValue = mode === "day" ? `${value}${suffix}` : `${value}${suffix}`;
    const timestamp = new Date(isoValue).getTime();
    return Number.isNaN(timestamp) ? null : timestamp;
}

async function handleTaskSubmit(event) {
    event.preventDefault();
    setTaskStatus("", false);
    const payload = buildTaskPayload();
    if (!payload) return;
    const isEdit = Boolean(state.editingId);
    const url = isEdit ? `/api/tasks/${state.editingId}` : "/api/tasks";
    const method = isEdit ? "PUT" : "POST";
    selectors.submitTask.disabled = true;
    selectors.submitTask.setAttribute("aria-busy", "true");
    selectors.submitTask.textContent = isEdit ? "更新中..." : "保存中...";
    try {
        const response = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(await readApiErrorMessage(response, "保存失败"));
        }
        await response.json();
        resetTaskForm();
        setTaskStatus(isEdit ? "任务已更新" : "任务已创建");
        await loadTasks({ preserveTaskStatus: true });
    } catch (error) {
        setTaskStatus(getErrorMessage(error, "保存任务失败"), true);
    } finally {
        selectors.submitTask.disabled = false;
        selectors.submitTask.removeAttribute("aria-busy");
        selectors.submitTask.textContent = state.editingId ? "更新任务" : "保存任务";
    }
}

function buildTaskPayload() {
    const title = selectors.title.value.trim();
    if (!title) {
        setTaskStatus("请输入任务标题", true);
        return null;
    }
    const description = selectors.description.value.trim();
    const startMode = getSelectedRadioValue("start-mode");
    const startValue = startMode === "day" ? selectors.startDate.value : selectors.startDateTime.value;
    if (!startValue) {
        setTaskStatus("请选择开始时间", true);
        return null;
    }
    const endMode = getSelectedRadioValue("end-mode");
    const endRawValue = endMode === "day" ? selectors.endDate.value : selectors.endDateTime.value;
    const endValue = endRawValue || null;
    const endAllDay = Boolean(endValue) && endMode === "day";
    const startComparable = toBeijingComparableTime(startValue, startMode, false);
    const endComparable = endValue ? toBeijingComparableTime(endValue, endMode, true) : null;
    if (endComparable !== null && startComparable !== null && endComparable < startComparable) {
        setTaskStatus("结束时间不能早于开始时间", true);
        return null;
    }
    return {
        title,
        description: description || null,
        start_at: startValue,
        start_all_day: startMode === "day",
        end_at: endValue,
        end_all_day: endAllDay,
        daily_reminder: selectors.dailyReminder.checked,
    };
}

function resetTaskForm() {
    state.editingId = null;
    document.getElementById("task-form").reset();
    selectors.dailyReminder.checked = false;
    selectors.cancelEdit.classList.add("hidden");
    selectors.submitTask.textContent = "保存任务";
    selectors.taskHeading.textContent = "新建任务";
    setTaskStatus("", false);
    syncStartModeVisibility();
    syncEndModeVisibility();
}

function beginEditTask(taskId) {
    const task = state.tasks.find((item) => item.id === taskId);
    if (!task) return;
    setTaskStatus("", false);
    state.editingId = taskId;
    selectors.taskHeading.textContent = "编辑任务";
    selectors.title.value = task.title;
    selectors.description.value = task.description || "";

    setRadioValue("start-mode", task.start_all_day ? "day" : "minute");
    if (task.start_all_day) {
        selectors.startDate.value = formatInputDate(task.start_at);
        selectors.startDateTime.value = "";
    } else {
        selectors.startDateTime.value = formatInputDateTime(task.start_at);
        selectors.startDate.value = "";
    }

    if (task.end_at) {
        setRadioValue("end-mode", task.end_all_day ? "day" : "minute");
        if (task.end_all_day) {
            selectors.endDate.value = formatInputDate(task.end_at);
            selectors.endDateTime.value = "";
        } else {
            selectors.endDateTime.value = formatInputDateTime(task.end_at);
            selectors.endDate.value = "";
        }
    } else {
        setRadioValue("end-mode", "minute");
        selectors.endDate.value = "";
        selectors.endDateTime.value = "";
    }
    selectors.dailyReminder.checked = Boolean(task.daily_reminder);

    selectors.submitTask.textContent = "更新任务";
    selectors.cancelEdit.classList.remove("hidden");
    syncStartModeVisibility();
    syncEndModeVisibility();
    selectors.title.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setRadioValue(name, value) {
    const radios = document.querySelectorAll(`input[name="${name}"]`);
    radios.forEach((radio) => {
        radio.checked = radio.value === value;
    });
}

function formatInputDate(value) {
    return formatBeijingDate(value) || "";
}

function formatInputDateTime(value) {
    if (!value) return "";
    const datePart = formatBeijingDate(value);
    const timePart = formatBeijingTime(value);
    if (!datePart || !timePart) return "";
    return `${datePart}T${timePart}`;
}

async function deleteTask(taskId) {
    if (!confirm("确定删除该任务吗？")) return;
    const deleteButton = selectors.tableBody.querySelector(`button[data-delete="${taskId}"]`);
    if (deleteButton) {
        deleteButton.disabled = true;
        deleteButton.setAttribute("aria-busy", "true");
        deleteButton.textContent = "删除中...";
    }
    try {
        const response = await fetch(`/api/tasks/${taskId}`, { method: "DELETE" });
        if (!response.ok) throw new Error(await readApiErrorMessage(response, "删除失败"));
        await loadTasks();
        if (state.editingId === taskId) {
            resetTaskForm();
        }
        setTaskStatus("任务已删除");
    } catch (error) {
        setTaskStatus(getErrorMessage(error, "删除任务失败"), true);
    } finally {
        if (deleteButton?.isConnected) {
            deleteButton.disabled = false;
            deleteButton.removeAttribute("aria-busy");
            deleteButton.textContent = uiText.table.delete;
        }
    }
}

function setTaskStatus(message, isError = false) {
    selectors.taskStatus.textContent = message;
    selectors.taskStatus.classList.toggle("error", isError);
    selectors.taskStatus.classList.toggle("hidden", !message);
}

async function loadSettings() {
    try {
        const response = await fetch("/api/settings");
        if (!response.ok) throw new Error(await readApiErrorMessage(response, "无法获取设置"));
        const data = await response.json();
        state.settings = {
            webhook_url: data.webhook_url || "",
            daily_reminder_time: data.daily_reminder_time || "09:00",
        };
        selectors.deadline.value = data.deadline_notice_minutes;
        selectors.webhook.value = data.webhook_url;
        selectors.dailyReminderTime.value = data.daily_reminder_time || "09:00";
        updateOverviewMetrics();
        setSettingsStatus("", false);
    } catch (error) {
        setSettingsStatus(getErrorMessage(error, "加载设置失败"), true);
    }
}

async function handleSettingsSubmit(event) {
    event.preventDefault();
    setSettingsStatus("", false);
    const payload = {
        webhook_url: selectors.webhook.value.trim(),
        deadline_notice_minutes: Number(selectors.deadline.value) || 1,
        daily_reminder_time: selectors.dailyReminderTime.value || "09:00",
    };
    selectors.saveSettings.disabled = true;
    selectors.saveSettings.setAttribute("aria-busy", "true");
    selectors.saveSettings.textContent = "保存中...";
    try {
        const response = await fetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw new Error(await readApiErrorMessage(response, "保存失败"));
        }
        const data = await response.json();
        state.settings = {
            webhook_url: data.webhook_url || "",
            daily_reminder_time: data.daily_reminder_time || "09:00",
        };
        selectors.deadline.value = data.deadline_notice_minutes;
        selectors.webhook.value = data.webhook_url || "";
        selectors.dailyReminderTime.value = data.daily_reminder_time || "09:00";
        updateOverviewMetrics();
        setSettingsStatus("设置已保存");
    } catch (error) {
        setSettingsStatus(getErrorMessage(error, "保存设置失败"), true);
    } finally {
        selectors.saveSettings.disabled = false;
        selectors.saveSettings.removeAttribute("aria-busy");
        selectors.saveSettings.textContent = "保存设置";
    }
}

async function handleTestWebhook() {
    setSettingsStatus("", false);
    const webhookUrl = selectors.webhook.value.trim();
    if (!webhookUrl) {
        setSettingsStatus("请输入 Webhook 地址", true);
        return;
    }
    selectors.testWebhook.disabled = true;
    selectors.testWebhook.setAttribute("aria-busy", "true");
    selectors.testWebhook.textContent = "测试中...";
    setSettingsStatus("测试请求正在进行中……", false);
    try {
        const response = await fetch("/api/settings/test", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ webhook_url: webhookUrl }),
        });
        if (!response.ok) {
            throw new Error(await readApiErrorMessage(response, "连接测试失败"));
        }
        const data = await response.json().catch(() => ({}));
        setSettingsStatus(data.message || "连接测试成功");
    } catch (error) {
        setSettingsStatus(getErrorMessage(error, "连接测试失败"), true);
    } finally {
        selectors.testWebhook.disabled = false;
        selectors.testWebhook.removeAttribute("aria-busy");
        selectors.testWebhook.textContent = "测试推送";
    }
}

function setSettingsStatus(message, isError = false) {
    selectors.settingsStatus.textContent = message;
    selectors.settingsStatus.classList.toggle("error", isError);
    selectors.settingsStatus.classList.toggle("hidden", !message);
}
