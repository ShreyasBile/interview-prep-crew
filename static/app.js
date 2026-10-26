// Bootstrap: theme, model chip, sidebar counters and the router.
(async () => {
  const IPC = window.IPC;
  const { $ } = IPC;

  IPC.initTheme();
  try {
    const config = await IPC.api.get("/api/config");
    IPC.state.config = config;
    $("#modelName").textContent = IPC.shortModel(config.model);
    $("#modelChip small").textContent = `Model · ${config.provider[0].toUpperCase()}${config.provider.slice(1)}`;
    $("#modelChip").classList.toggle("ok", config.live_ready);
    $("#modelChip").classList.toggle("bad", !config.live_ready);
    $("#modelChip").title = config.live_reason;
    $("#versionLabel").textContent = `v${config.version}`;
    IPC.setHistoryCount(config.saved_runs);
  } catch (err) {
    $("#modelName").textContent = "Server not reachable";
    $("#modelChip").classList.add("bad");
  }
  await IPC.refreshCounts();
  await IPC.startRouter();
})();
