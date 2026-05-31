document.addEventListener("DOMContentLoaded", () => {
  let apiStarted = false;
  function waitForApi(cb) {
    function start() {
      if (apiStarted || !(window.pywebview && window.pywebview.api)) return;
      apiStarted = true;
      cb(window.pywebview.api);
    }
    window.addEventListener("pywebviewready", start, { once: true });
    (function poll() {
      if (apiStarted) return;
      if (window.pywebview && window.pywebview.api) start();
      else setTimeout(poll, 50);
    })();
  }

  waitForApi(async (api) => {
    const fixUwpBtn = document.getElementById("fix-uwp-btn");
    const uwpSuccess = document.getElementById("uwp-success");
    const uwpError = document.getElementById("uwp-error");
    const updateDbBtn = document.getElementById("update-db-btn");
    const uwpHint = document.getElementById("uwp-hint");
    const statusText = document.getElementById("status-text");
    const pulseDot = document.querySelector(".pulse-dot");
    const statusDetail = document.getElementById("status-detail");

    let settings = {};
    for (let i = 0; i < 20; i++) {
      try { settings = (await api.get_settings()) || {}; break; }
      catch (e) {
        if (i === 19) console.error("Failed to load settings:", e);
        await new Promise((r) => setTimeout(r, 100));
      }
    }
    function getSetting(key, def = null) {
      const v = settings[key];
      return (v === undefined || v === null) ? def : v;
    }
    function setSetting(key, value) {
      const v = String(value);
      settings[key] = v;
      api.set_setting(key, v).catch((e) => console.error("save setting failed:", key, e));
    }

    // Fix UWP Isolation
    async function checkUwpStatus() {
      try {
        const isFixedBackend = await api.check_uwp_status();
        const isFixedLocal = getSetting("uwp_fixed_v2") === "true";
        if (isFixedBackend || isFixedLocal) {
          fixUwpBtn.classList.add("hidden");
          if (uwpHint) uwpHint.classList.add("hidden");
          uwpSuccess.classList.remove("hidden");
          uwpSuccess.textContent = "Network already fixed";
          if (uwpError) uwpError.classList.add("hidden");
        }
      } catch (e) {
        console.error("Failed to check UWP status", e);
      }
    }
    checkUwpStatus();

    fixUwpBtn.addEventListener("click", async () => {
      fixUwpBtn.disabled = true;
      fixUwpBtn.textContent = "Fixing...";
      if (uwpSuccess) uwpSuccess.classList.add("hidden");
      if (uwpError) uwpError.classList.add("hidden");
      try {
        await api.fix_uwp_isolation();
        fixUwpBtn.textContent = "Fixed!";
        fixUwpBtn.classList.add("hidden");
        if (uwpHint) uwpHint.classList.add("hidden");
        uwpSuccess.classList.remove("hidden");
        uwpSuccess.textContent = "Network fixed";
        setSetting("uwp_fixed_v2", "true");
      } catch (error) {
        console.error(error);
        fixUwpBtn.textContent = "Error";
        setTimeout(() => { fixUwpBtn.textContent = "Fix Network"; fixUwpBtn.disabled = false; }, 3000);
      }
    });

    // Update DB 
    updateDbBtn.addEventListener("click", async () => {
      updateDbBtn.disabled = true;
      updateDbBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation: rotateBg 2s linear infinite;"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Checking...`;
      try {
        await api.check_db_updates();
        updateDbBtn.textContent = "Updated!";
        setTimeout(() => { updateDbBtn.textContent = "Update Cars"; updateDbBtn.disabled = false; }, 3000);
      } catch (error) {
        console.error(error);
        updateDbBtn.textContent = "Error";
        setTimeout(() => { updateDbBtn.textContent = "Update Cars"; updateDbBtn.disabled = false; }, 3000);
      }
    });

    // Start Minimized / Auto-update settings
    const startMinimizedCheck = document.getElementById("start-minimized-check");
    const autoUpdateCheck = document.getElementById("auto-update-check");

    const hasRunBefore = getSetting("has_run_before");
    let startMinimized = getSetting("start_minimized");
    if (startMinimized === null) { startMinimized = "true"; setSetting("start_minimized", "true"); }
    let autoUpdate = getSetting("auto_update");
    if (autoUpdate === null) { autoUpdate = "true"; setSetting("auto_update", "true"); }

    startMinimizedCheck.checked = startMinimized === "true";
    autoUpdateCheck.checked = autoUpdate === "true";

    if (!hasRunBefore) {
      setSetting("has_run_before", "true");
      api.show_window().catch(console.error);
    } else if (startMinimized !== "true") {
      api.show_window().catch(console.error);
    }

    if (autoUpdate === "true") { updateDbBtn.click(); }

    startMinimizedCheck.addEventListener("change", (e) => {
      setSetting("start_minimized", e.target.checked.toString());
    });
    autoUpdateCheck.addEventListener("change", (e) => {
      setSetting("auto_update", e.target.checked.toString());
    });

    // Status updates
    window.addEventListener("status_update", (e) => {
      const { status, game, details, presence } = e.detail;
      if (status === "connected") {
        pulseDot.classList.add("active", "active-pulse");
        pulseDot.style.animationName = "pulse-success";
        statusText.textContent = `${game}`;
        statusText.style.color = "var(--success-color)";
        statusDetail.textContent = details || "Broadcasting presence to Discord.";
        const presenceText = document.getElementById("presence-status-text");
        if (presence) {
          presenceText.textContent = presence;
          presenceText.style.color = "var(--success-color)";
        }
      } else {
        pulseDot.classList.remove("active", "active-pulse");
        pulseDot.style.animationName = "pulse";
        statusText.textContent = "Waiting...";
        statusText.style.color = "inherit";
        statusDetail.textContent = details || "Launch game to broadcast";
        const presenceText = document.getElementById("presence-status-text");
        presenceText.textContent = presence || "Waiting for game...";
        if (presence && (presence.includes("Error:") || presence.includes("error:"))) {
          presenceText.style.color = "var(--error-color)";
        } else {
          presenceText.style.color = "inherit";
        }
      }
    });

    let currentGameName = "Forza Horizon";
    window.addEventListener("status_update", (e) => {
      if (e.detail.game) currentGameName = e.detail.game;
    });

    // Telemetry port 
    const portInput = document.getElementById("telemetry-port");
    const portSavedIndicator = document.getElementById("port-saved-indicator");
    let savedPort = getSetting("telemetry_port", "8001");
    portInput.value = savedPort;

    portInput.addEventListener("blur", async () => {
      const portVal = parseInt(portInput.value) || 8001;
      const currentSavedPort = getSetting("telemetry_port", "8001");
      if (portVal.toString() !== currentSavedPort) {
        setSetting("telemetry_port", portVal.toString());
        try {
          await api.update_telemetry_port(portVal);
          portSavedIndicator.classList.add("visible");
          setTimeout(() => portSavedIndicator.classList.remove("visible"), 2000);
        } catch (err) { console.error("Failed to auto-save port:", err); }
      }
    });

    // UDP Forwarding Panel
    const udpForwardBtn = document.getElementById("udp-forward-btn");
    const udpForwardPanel = document.getElementById("udp-forward-panel");
    const relayActiveToggle = document.getElementById("relay-active");
    const relayIpInput = document.getElementById("relay-ip");
    const relayPortInput = document.getElementById("relay-port");
    const relaySavedIndicator = document.getElementById("relay-saved-indicator");

    const savedRelayIp = getSetting("relay_ip", "127.0.0.1");
    const savedRelayPort = getSetting("relay_port", "8000");
    const relayEnabled = getSetting("relay_enabled") === "true";
    const relayActive = getSetting("relay_active") === "true";

    relayIpInput.value = savedRelayIp;
    relayPortInput.value = savedRelayPort;
    relayActiveToggle.checked = relayActive;

    function updateFieldsState(active) {
      const rows = udpForwardPanel.querySelectorAll(".udp-forward-row");
      rows.forEach(row => {
        if (active) row.classList.remove("udp-fields-disabled");
        else row.classList.add("udp-fields-disabled");
      });
      if (active) udpForwardBtn.classList.add("active");
      else udpForwardBtn.classList.remove("active");
    }
    updateFieldsState(relayActive);

    const BASE_HEIGHT = 365;

    async function setWindowHeight(height) {
      try { await api.set_window_height(height); }
      catch (e) { console.error("Failed to resize window:", e); }
    }

    if (relayEnabled) {
      udpForwardPanel.classList.remove("hidden");
      requestAnimationFrame(() => {
        const panelH = udpForwardPanel.offsetHeight;
        setWindowHeight(BASE_HEIGHT + panelH + 25);
      });
    }

    udpForwardBtn.addEventListener("click", () => {
      const isOpen = !udpForwardPanel.classList.contains("hidden");
      if (isOpen) {
        setWindowHeight(BASE_HEIGHT).then(() => udpForwardPanel.classList.add("hidden"));
        setSetting("relay_enabled", "false");
      } else {
        udpForwardPanel.classList.remove("hidden");
        setSetting("relay_enabled", "true");
        requestAnimationFrame(() => {
          const panelH = udpForwardPanel.offsetHeight;
          setWindowHeight(BASE_HEIGHT + panelH + 25);
        });
      }
    });

    relayActiveToggle.addEventListener("change", () => {
      const active = relayActiveToggle.checked;
      setSetting("relay_active", active.toString());
      updateFieldsState(active);
      if (active) applyRelaySettings();
      else api.update_relay_ports([]).catch(console.error);
    });

    async function applyRelaySettings() {
      const ip = relayIpInput.value.trim() || "127.0.0.1";
      const port = parseInt(relayPortInput.value) || 8000;
      if (port < 1 || port > 65535) return;
      const telemetryPort = parseInt(portInput.value) || 8001;
      const isLocalhost = ip === "127.0.0.1" || ip === "localhost" || ip === "0.0.0.0";
      if (isLocalhost && port === telemetryPort) {
        relayPortInput.style.borderColor = "var(--error-color, #ff4d4d)";
        setTimeout(() => relayPortInput.style.borderColor = "", 2000);
        if (relayActiveToggle.checked) {
          relayActiveToggle.checked = false;
          setSetting("relay_active", "false");
          updateFieldsState(false);
          api.update_relay_ports([]).catch(console.error);
        }
        return;
      }
      try {
        await api.update_relay_ports([{ ip, port }]);
        relaySavedIndicator.classList.add("visible");
        setTimeout(() => relaySavedIndicator.classList.remove("visible"), 2000);
      } catch (err) { console.error("Failed to apply relay settings:", err); }
    }

    relayIpInput.addEventListener("blur", async () => {
      if (!udpForwardPanel.classList.contains("hidden") && relayActiveToggle.checked) {
        setSetting("relay_ip", relayIpInput.value.trim() || "127.0.0.1");
        await applyRelaySettings();
      }
    });
    relayPortInput.addEventListener("blur", async () => {
      if (!udpForwardPanel.classList.contains("hidden") && relayActiveToggle.checked) {
        setSetting("relay_port", relayPortInput.value.trim() || "8000");
        await applyRelaySettings();
      }
    });

    // Init backend
    api.ui_ready().catch(console.error);
    api.update_telemetry_port(parseInt(savedPort) || 8001).catch(console.error);
    if (relayActive) applyRelaySettings().catch(console.error);

    // Unknown car reporting
    const unknownCarSection = document.getElementById("unknown-car-section");
    const unknownCarWarning = document.getElementById("unknown-car-warning");
    const carNameInput = document.getElementById("car-name-input");
    const sendReportBtn = document.getElementById("send-report-btn");
    let currentUnknownCar = null;

    window.addEventListener("unknown_car", (e) => {
      const data = e.detail;
      if (data) {
        currentUnknownCar = data;
        unknownCarWarning.textContent = `Unknown car: ID ${data.id}`;
        unknownCarSection.classList.remove("invisible");
      } else {
        unknownCarSection.classList.add("invisible");
      }
    });

    sendReportBtn.addEventListener("click", async () => {
      const name = carNameInput.value.trim();
      if (!name || !currentUnknownCar) return;
      sendReportBtn.disabled = true;
      sendReportBtn.textContent = "Waiting...";
      try {
        const msg = await api.report_car_name(currentUnknownCar.id, name, currentGameName);
        carNameInput.value = "";
        unknownCarWarning.textContent = msg;
        setTimeout(() => unknownCarSection.classList.add("invisible"), 2000);
      } catch (err) {
        console.error(err);
        alert("Failed to send report: " + err);
      } finally {
        sendReportBtn.disabled = false;
        sendReportBtn.textContent = "Report";
      }
    });

    // External links 
    document.querySelectorAll('a[target="_blank"]').forEach(link => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        api.open_url(link.href).catch(console.error);
      });
    });
  });
});
