const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

document.addEventListener("DOMContentLoaded", () => {
  const fixUwpBtn = document.getElementById("fix-uwp-btn");
  const uwpSuccess = document.getElementById("uwp-success");
  const uwpError = document.getElementById("uwp-error");

  const updateDbBtn = document.getElementById("update-db-btn");
  const dbSuccess = document.getElementById("db-success");

  const statusIndicator = document.getElementById("status-indicator");
  const statusText = document.getElementById("status-text");
  const pulseDot = document.querySelector(".pulse-dot");
  const statusDetail = document.getElementById("status-detail");

  // Fix UWP Isolation Button
  // Check if already fixed
  async function checkUwpStatus() {
    try {
      const isFixedBackend = await invoke("check_uwp_status");
      const isFixedLocal = localStorage.getItem("uwp_fixed") === "true";
      
      if (isFixedBackend || isFixedLocal) {
        fixUwpBtn.classList.add("hidden");
        uwpSuccess.classList.remove("hidden");
        uwpSuccess.textContent = "Network already fixed";
        uwpError.classList.add("hidden");
      }
    } catch (e) {
      console.error("Failed to check UWP status", e);
    }
  }

  checkUwpStatus();

  fixUwpBtn.addEventListener("click", async () => {
    fixUwpBtn.disabled = true;
    fixUwpBtn.textContent = "Fixing...";
    uwpSuccess.classList.add("hidden");
    uwpError.classList.add("hidden");

    try {
      // Call Rust backend command
      await invoke("fix_uwp_isolation");
      uwpSuccess.classList.remove("hidden");
      uwpSuccess.textContent = "Fixed successfully!";
      fixUwpBtn.classList.add("hidden");
      localStorage.setItem("uwp_fixed", "true");
    } catch (error) {
      console.error(error);
      uwpError.textContent = `Error: ${error}`;
      uwpError.classList.remove("hidden");
    } finally {
      fixUwpBtn.disabled = false;
      fixUwpBtn.textContent = "Fix Network";
    }
  });

  // Check DB Updates Button
  updateDbBtn.addEventListener("click", async () => {
    updateDbBtn.disabled = true;
    dbSuccess.classList.add("hidden");
    
    // Animate button
    updateDbBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation: rotateBg 2s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Checking...`;

    try {
      const result = await invoke("check_db_updates");
      dbSuccess.textContent = result;
      dbSuccess.classList.remove("hidden");
    } catch (error) {
      console.error(error);
      dbSuccess.textContent = `Error: ${error}`;
      dbSuccess.classList.remove("hidden");
      dbSuccess.style.color = "var(--error-color)";
    } finally {
      updateDbBtn.disabled = false;
      updateDbBtn.textContent = `Update Cars`;
    }
  });

  // Listen for status updates from Rust backend
  listen("status_update", (event) => {
    const { status, game, details } = event.payload;

    if (status === "connected") {
      pulseDot.classList.add("active");
      pulseDot.classList.add("active-pulse");
      pulseDot.style.animationName = "pulse-success";
      
      statusText.textContent = `Connected to ${game}`;
      statusText.style.color = "var(--success-color)";
      statusDetail.textContent = details || "Broadcasting presence to Discord.";
    } else {
      pulseDot.classList.remove("active");
      pulseDot.classList.remove("active-pulse");
      pulseDot.style.animationName = "pulse";

      statusText.textContent = "Waiting for Game...";
      statusText.style.color = "inherit";
      statusDetail.textContent = "Launch Forza Horizon 4 to begin broadcasting your presence.";
    }
  });

  // Tell backend we are ready to receive initial status
  invoke("ui_ready").catch(console.error);
});
