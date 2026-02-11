// ==========================
//      API CONFIG
// ==========================
const API_BASE = "http://127.0.0.1:8000/api";


// ==========================
//      TABS
// ==========================
const navButtons = document.querySelectorAll(".nav-btn");
const tabs = {
  extract: document.getElementById("tab-extract"),
  stamp: document.getElementById("tab-stamp"),
};

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const tab = btn.dataset.tab;
    if (!tab) return;

    navButtons.forEach((b) => b.classList.remove("nav-btn--active"));
    btn.classList.add("nav-btn--active");

    Object.entries(tabs).forEach(([key, el]) => {
      el.classList.toggle("tab--active", key === tab);
    });
  });
});


// ==========================
//     EXTRACT LOGIC
// ==========================
let selectedMode = null;

const modeButtons = document.querySelectorAll(".mode-btn");
const extractForm = document.getElementById("extract-form");
const extractPdfInput = document.getElementById("extract-pdf");
const extractStatus = document.getElementById("extract-status");
const includeCleanCheckbox = document.getElementById("include-clean");


modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    selectedMode = btn.dataset.mode;
    modeButtons.forEach((b) => b.classList.remove("mode-btn--active"));
    btn.classList.add("mode-btn--active");
  });
});


function setStatus(el, message, type = "") {
  el.textContent = message || "";
  el.classList.remove("status--error", "status--success");
  if (type === "error") el.classList.add("status--error");
  if (type === "success") el.classList.add("status--success");
}


function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


extractForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  if (!selectedMode) {
    setStatus(extractStatus, "Сначала выберите режим!", "error");
    return;
  }

  const file = extractPdfInput.files[0];
  if (!file) {
    setStatus(extractStatus, "Загрузите PDF.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("pdf", file);
  formData.append("mode", selectedMode);

  formData.append(
    "output_mode",
    extractForm.querySelector('input[name="output_mode"]:checked')?.value || "single"
  );

  formData.append(
    "include_clean",
    includeCleanCheckbox.checked ? "true" : "false"
  );

  setStatus(extractStatus, "Обработка PDF...");

  try {
    // ❗❗❗ ИСПРАВЛЕННЫЙ ПУТЬ
    const response = await fetch(`${API_BASE}/detect-filter`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      let message = "Ошибка обработки PDF.";

      try {
        const json = JSON.parse(text);
        if (json.error) message = json.error;
      } catch {}

      setStatus(extractStatus, message, "error");
      return;
    }

    const blob = await response.blob();

    const cd = response.headers.get("Content-Disposition") || "";
    let filename = "result.pdf";
    const m = cd.match(/filename="?(.*?)"?$/);
    if (m) filename = m[1];

    downloadBlob(blob, filename);
    setStatus(extractStatus, "Готово! Файл скачан.", "success");

  } catch (err) {
    console.error(err);
    setStatus(extractStatus, "Не удалось подключиться к серверу.", "error");
  }
});


// ==========================
//     STAMP LOGIC
// ==========================
const stampForm = document.getElementById("stamp-form");
const stampPdfInput = document.getElementById("stamp-pdf");
const stampImgInput = document.getElementById("stamp-img");
const signatureImgInput = document.getElementById("signature-img");
const qrImgInput = document.getElementById("qr-img");

const stampPagesInput = document.getElementById("stamp-pages");
const signaturePagesInput = document.getElementById("signature-pages");
const qrPagesInput = document.getElementById("qr-pages");

const positionSelect = document.getElementById("position");
const stampStatus = document.getElementById("stamp-status");


stampForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const pdf = stampPdfInput.files[0];
  if (!pdf) {
    setStatus(stampStatus, "Загрузите исходный PDF.", "error");
    return;
  }

  if (!stampImgInput.files[0] &&
      !signatureImgInput.files[0] &&
      !qrImgInput.files[0]) {
    setStatus(stampStatus, "Выберите хотя бы одно изображение.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("pdf", pdf);

  if (stampImgInput.files[0]) {
    formData.append("stamp", stampImgInput.files[0]);
    formData.append("stamp_pages", stampPagesInput.value);
  }
  if (signatureImgInput.files[0]) {
    formData.append("signature", signatureImgInput.files[0]);
    formData.append("signature_pages", signaturePagesInput.value);
  }
  if (qrImgInput.files[0]) {
    formData.append("qr", qrImgInput.files[0]);
    formData.append("qr_pages", qrPagesInput.value);
  }

  formData.append("position", positionSelect.value);

  setStatus(stampStatus, "Создаю PDF...");

  try {
    // ❗❗❗ ИСПРАВЛЕННЫЙ ПУТЬ
    const response = await fetch(`${API_BASE}/stamp`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const text = await response.text();
      let message = "Ошибка при добавлении элементов.";

      try {
        const json = JSON.parse(text);
        if (json.error) message = json.error;
      } catch {}

      setStatus(stampStatus, message, "error");
      return;
    }

    const blob = await response.blob();
    downloadBlob(blob, "stamped_document.pdf");
    setStatus(stampStatus, "Готово! Файл скачан.", "success");

  } catch (err) {
    console.error(err);
    setStatus(stampStatus, "Не удалось подключиться к серверу.", "error");
  }
});
