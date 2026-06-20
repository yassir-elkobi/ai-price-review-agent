const $ = (selector) => document.querySelector(selector);
const presetBox = $("#presets");
const scenarioNote = $("#scenarioNote");
let scenarios = [];

function difficultyLabel(level) {
    const labels = {
        easy: "facile",
        medium: "moyen",
        hard: "difficile",
        extreme: "extrême",
    };
    return labels[level] || level;
}

function showScenarioNote(scenario) {
    if (!scenario) {
        scenarioNote.classList.remove("show");
        scenarioNote.innerHTML = "";
        return;
    }
    let html = scenario.teaching_note_fr || scenario.teaching_note;
    const flipHint = scenario.live_flip_hint_fr || scenario.live_flip_hint;
    if (flipHint) {
        html += `<span class="flip">${flipHint}</span>`;
    }
    scenarioNote.innerHTML = html;
    scenarioNote.classList.add("show");
}

function renderPresets(list) {
    presetBox.innerHTML = "";
    list.forEach((scenario) => {
        const row = document.createElement("button");
        row.type = "button";
        row.className = "scenario-item";
        const note = scenario.teaching_note_fr || scenario.teaching_note;
        const label = scenario.title_fr || scenario.title;
        row.title = note;
        row.innerHTML =
            `<span class="label">${label}</span>` +
            `<span class="diff">${difficultyLabel(scenario.difficulty)}</span>`;
        row.onclick = () => {
            $("#q").value = scenario.query;
            showScenarioNote(scenario);
        };
        presetBox.appendChild(row);
    });
}

async function loadScenarios() {
    try {
        const response = await fetch("/scenarios");
        const data = await response.json();
        scenarios = data.scenarios || [];
        renderPresets(scenarios);
    } catch {
        presetBox.innerHTML = '<div class="presets-error">Impossible de charger les scénarios.</div>';
    }
}

async function loadRules() {
    try {
        const response = await fetch("/rules");
        const data = await response.json();
        $("#rules").value = data.rules || "";
    } catch {
        $("#rules").value = "(impossible de charger les règles)";
    }
}

function toolLabel(kind) {
    return kind === "call" ? "Call tool" : "Observe";
}

function badgeify(text) {
    return text
        .replace(/\bESCALATE\b/g, '<span class="badge b-esc">ESCALATE</span>')
        .replace(/\bREJECTED\b/g, '<span class="badge b-rej">REJECTED</span>')
        .replace(/\bAPPROVED\b/g, '<span class="badge b-ok">APPROVED</span>');
}

function verdictClass(text) {
    if (/\bREJECTED\b/.test(text)) return "has-rej";
    if (/\bESCALATE\b/.test(text)) return "has-esc";
    if (/\bAPPROVED\b/.test(text)) return "has-ok";
    return "";
}

async function renderSteps(steps) {
    const box = $("#trace");
    box.innerHTML = "";
    for (const step of steps) {
        const element = document.createElement("div");
        element.className = `step ${step.kind === "result" ? "result" : "call"}`;
        if (step.kind === "call") {
            const args = Object.keys(step.args || {}).length ? JSON.stringify(step.args) : "-";
            element.innerHTML = `<span class="node"></span>
                <div class="label">${toolLabel(step.kind)}</div>
                <div class="tool">${step.tool}()</div>
                <div class="args">args: ${args}</div>`;
        } else {
            const observation = (step.content || "").slice(0, 600);
            element.innerHTML = `<span class="node"></span>
                <div class="label">${toolLabel(step.kind)} · ${step.tool}</div>
                <div class="obs">${observation.replace(/</g, "&lt;")}</div>`;
        }
        box.appendChild(element);
        await new Promise((resolve) => setTimeout(resolve, 280));
    }
}

async function runReview() {
    const query = $("#q").value.trim();
    if (!query) {
        $("#q").focus();
        return;
    }

    $("#go").disabled = true;
    $("#status").textContent = "agent reasoning…";
    $("#answer").classList.remove("show");
    $("#trace").innerHTML = '<div class="tl-empty">Connecting to agent…</div>';

    try {
        const response = await fetch("/validate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({query}),
        });
        const data = await response.json();
        if (data.error) {
            $("#trace").innerHTML = `<div class="tl-empty">Error: ${data.error}</div>`;
            $("#status").textContent = "";
            return;
        }

        await renderSteps(data.steps || []);
        const answer = data.final_answer || "(no response)";
        $("#answerBody").innerHTML = badgeify(answer);
        $("#verdictBody").className = `verdict-body ${verdictClass(answer)}`;
        $("#answer").classList.add("show");
        $("#status").textContent = `${data.steps?.length || 0} steps · done`;
    } catch (error) {
        $("#trace").innerHTML = `<div class="tl-empty">Network error: ${error.message}</div>`;
        $("#status").textContent = "";
    } finally {
        $("#go").disabled = false;
    }
}

async function saveRules() {
    $("#rulesSaved").textContent = "…";
    try {
        await fetch("/rules", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({rules: $("#rules").value}),
        });
        $("#rulesSaved").textContent = "enregistré";
        setTimeout(() => {
            $("#rulesSaved").textContent = "";
        }, 2500);
    } catch {
        $("#rulesSaved").textContent = "erreur";
    }
}

$("#go").onclick = runReview;
$("#saveRules").onclick = saveRules;
loadScenarios();
loadRules();
