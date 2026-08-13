// Panel bez frameworka — vanilla JS, fetch API. Serwer nie trzyma stanu poza
// cache'em modelu; wynik wraca jako tekst CSV w odpowiedzi JSON, a "zapis
// lokalnie" to zwykłe pobranie pliku przez Blob — bez żadnych plików
// tymczasowych do sprzątania po stronie serwera.

const $ = (id) => document.getElementById(id);

// --- zakładki -----------------------------------------------------------

document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $(`panel-${btn.dataset.tab}`).classList.add("active");
  });
});

// --- status Ollamy --------------------------------------------------------

async function checkOllama() {
  const el = $("ollama-status");
  try {
    const res = await fetch("/api/health");
    const data = await res.json();
    el.querySelector(".dot").className = `dot ${data.ollama ? "ok" : "err"}`;
    el.querySelector("span:last-child").textContent = data.ollama
      ? `Ollama gotowa (${data.model})`
      : "Ollama niedostępna — działa tylko ścieżka regułowa";
  } catch {
    el.querySelector(".dot").className = "dot err";
    el.querySelector("span:last-child").textContent = "brak połączenia z panelem";
  }
}
checkOllama();

// --- pomocnicze -------------------------------------------------------

function showError(elId, message) {
  const el = $(elId);
  el.textContent = message;
  el.classList.remove("hidden");
}
function hideError(elId) {
  $(elId).classList.add("hidden");
}
function downloadCsv(text, filename) {
  const blob = new Blob([text], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
function withBusy(button, label, fn) {
  return async (...args) => {
    const original = button.textContent;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span>${label}`;
    try {
      await fn(...args);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  };
}

// --- kategoryzacja: podgląd kolumn ----------------------------------------

async function refreshColumns() {
  const file = $("cat-file").files[0];
  if (!file) return;
  const form = new FormData();
  form.append("file", file);
  form.append("sep", $("cat-sep").value || ";");
  try {
    const res = await fetch("/api/preview", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) {
      $("cat-preview-hint").textContent = data.detail || "Nie udało się odczytać pliku.";
      return;
    }
    const select = $("cat-column");
    select.innerHTML = "";
    for (const col of data.columns) {
      const opt = document.createElement("option");
      opt.value = col;
      opt.textContent = col;
      if (col === "kategoria") opt.selected = true;
      select.appendChild(opt);
    }
    $("cat-preview-hint").textContent = `${data.row_count} wierszy, ${data.columns.length} kolumn.`;
  } catch {
    $("cat-preview-hint").textContent = "Panel nie odpowiada.";
  }
}
$("cat-file").addEventListener("change", refreshColumns);
$("cat-sep").addEventListener("change", refreshColumns);

// --- kategoryzacja: tryb reguł ----------------------------------------

$("mode-manual").addEventListener("click", () => {
  $("mode-manual").classList.add("active");
  $("mode-ai").classList.remove("active");
  $("ai-controls").style.display = "none";
});
$("mode-ai").addEventListener("click", () => {
  $("mode-ai").classList.add("active");
  $("mode-manual").classList.remove("active");
  $("ai-controls").style.display = "block";
});

$("rules-file").addEventListener("change", async () => {
  const file = $("rules-file").files[0];
  if (!file) return;
  $("rules-json").value = await file.text();
});

$("btn-propose").addEventListener("click", withBusy($("btn-propose"), "Proponuję…", async () => {
  hideError("cat-error");
  const file = $("cat-file").files[0];
  if (!file) return showError("cat-error", "Wybierz najpierw plik CSV.");

  const form = new FormData();
  form.append("file", file);
  form.append("column", $("cat-column").value);
  form.append("sep", $("cat-sep").value || ";");
  form.append("target_count", $("target-count").value);

  const res = await fetch("/api/categorize/propose-rules", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) return showError("cat-error", data.detail || "Nie udało się zaproponować reguł.");

  $("rules-json").value = JSON.stringify(data.rules, null, 2);
  $("propose-summary").textContent =
    `${data.unique_categories} unikalnych kategorii → ${data.target_categories} grup. ` +
    (data.unmapped.length ? `Bez propozycji (${data.unmapped.length}): ${data.unmapped.slice(0, 5).join(", ")}${data.unmapped.length > 5 ? "…" : ""}` : "wszystkie przypisane.");
}));

// --- kategoryzacja: uruchomienie ----------------------------------------

let lastCategorizedCsv = null;

$("btn-categorize").addEventListener("click", withBusy($("btn-categorize"), "Kategoryzuję…", async () => {
  hideError("cat-error");
  $("cat-result").classList.add("hidden");
  const file = $("cat-file").files[0];
  if (!file) return showError("cat-error", "Wybierz plik CSV.");

  let rulesText = $("rules-json").value;
  try {
    JSON.parse(rulesText);
  } catch (e) {
    return showError("cat-error", `Reguły nie są poprawnym JSON-em: ${e.message}`);
  }

  const form = new FormData();
  form.append("file", file);
  form.append("column", $("cat-column").value);
  form.append("sep", $("cat-sep").value || ";");
  form.append("rules", rulesText);
  form.append("use_llm", $("use-llm").checked);

  const res = await fetch("/api/categorize/run", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) return showError("cat-error", data.detail || "Kategoryzacja nie powiodła się.");

  lastCategorizedCsv = data.csv;
  $("cat-stat-rules").textContent = data.summary.matched_by_rules;
  $("cat-stat-llm").textContent = data.summary.matched_by_llm;
  $("cat-stat-unresolved").textContent = data.summary.unresolved;
  $("cat-stat-llm-wrap").className = data.summary.matched_by_llm > 0 ? "stat ok" : "stat";
  $("cat-result").classList.remove("hidden");
}));

$("btn-download-cat").addEventListener("click", () => {
  if (lastCategorizedCsv) downloadCsv(lastCategorizedCsv, "skategoryzowane.csv");
});

// --- konsolidacja ---------------------------------------------------------

let lastConsolidatedCsv = null;

$("btn-consolidate").addEventListener("click", withBusy($("btn-consolidate"), "Konsoliduję…", async () => {
  hideError("con-error");
  $("con-result").classList.add("hidden");
  const file = $("con-file").files[0];
  if (!file) return showError("con-error", "Wybierz plik CSV.");

  const form = new FormData();
  form.append("file", file);
  form.append("fetch_images", $("fetch-images").checked);

  const res = await fetch("/api/consolidate/run", { method: "POST", body: form });
  const data = await res.json();
  if (!res.ok) return showError("con-error", data.detail || "Konsolidacja nie powiodła się.");

  lastConsolidatedCsv = data.csv;
  $("con-stat-groups").textContent = data.summary.groups_consolidated;
  $("con-stat-single").textContent = data.summary.groups_passthrough;
  $("con-stat-unresolved").textContent = data.unresolved.length;

  const unresolvedEl = $("con-unresolved");
  if (data.unresolved.length) {
    unresolvedEl.textContent = data.unresolved.join("\n");
    unresolvedEl.classList.remove("hidden");
  } else {
    unresolvedEl.classList.add("hidden");
  }
  $("con-result").classList.remove("hidden");
}));

$("btn-download-con").addEventListener("click", () => {
  if (lastConsolidatedCsv) downloadCsv(lastConsolidatedCsv, "skonsolidowane.csv");
});
