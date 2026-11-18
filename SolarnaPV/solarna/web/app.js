(() => {
  "use strict";

  const runtimeConfig = window.SOLARNA_CONFIG || {};
  const i18n = window.SOLARNA_I18N;
  const systemConfig = window.SOLARNA_SYSTEM;
  const resultSummary = window.SOLARNA_RESULT_SUMMARY;
  const installSupport = window.SOLARNA_INSTALL;
  const cloudStorage = window.SOLARNA_CLOUD;
  const supabaseLibrary = window.SOLARNA_SUPABASE;
  const nativeShell = runtimeConfig.nativeShell === true;
  const allowInsecureApi = runtimeConfig.allowInsecureApi === true;
  document.body.classList.toggle("native-shell", nativeShell);
  document.body.classList.toggle("web-shell", !nativeShell);
  const draftStorageKey = "solarna:form-v2";
  const draftFields = [
    "preset",
    "name",
    "latitude",
    "longitude",
    "elevation-mode",
    "altitude",
    "inverter-model",
    "panel-model",
    "system-size-mode",
    "panel-count",
    "panel-power",
    "capacity",
    "inverter-ac-rating",
    "temperature-model",
    "analysis-profile",
    "albedo",
    "loss-mode",
    "loss-preset",
    "losses",
    "loss-soiling",
    "loss-shading",
    "loss-mismatch",
    "loss-wiring",
    "loss-availability",
    "loss-quality",
    "gamma-pdc",
    "inverter-efficiency",
    "coarse-step",
    "fine-step",
    "timing-sensitivity",
    "period-analysis",
    "pvgis-benchmark",
    "historical-range",
    "existing-orientation-enabled",
    "existing-tilt",
    "existing-azimuth",
    ...Array.from({ length: 12 }, (_, index) => `period-month-${index + 1}`)
  ];

  function normalizeApiBase(value) {
    const text = typeof value === "string" ? value.trim() : "";
    if (!text) return "";
    const parsed = new URL(text);
    if (!["http:", "https:"].includes(parsed.protocol) ||
        parsed.username || parsed.password || parsed.search || parsed.hash ||
        !parsed.hostname || parsed.pathname !== "/") {
      throw new Error(t("server_origin_error"));
    }
    if (nativeShell && parsed.protocol !== "https:" && !allowInsecureApi) {
      throw new Error(t("mobile_https_error"));
    }
    return parsed.origin;
  }

  function storedApiBase() {
    try {
      return localStorage.getItem("solarna:api-base") || "";
    } catch {
      return "";
    }
  }

  function storedSessionToken() {
    try {
      return sessionStorage.getItem("solarna:session-token") || "";
    } catch {
      return "";
    }
  }

  let apiBaseUrl = "";
  try {
    apiBaseUrl = normalizeApiBase(
      nativeShell ? storedApiBase() || runtimeConfig.apiBaseUrl : runtimeConfig.apiBaseUrl
    );
  } catch {
    apiBaseUrl = "";
  }
  let sessionToken = storedSessionToken();
  let serverAuthRequired = false;
  let serverAuthMode = "none";
  let supabaseClient = null;
  let supabaseConfigKey = "";
  let currentUserId = "";

  function loginPageUrl() {
    return new URL("login.html", window.location.href).href;
  }

  function redirectToLogin() {
    try {
      sessionStorage.removeItem("solarna:session-token");
    } catch {
    }
    window.location.replace(loginPageUrl());
  }

  async function configureSupabase(health) {
    if (health.authentication_mode !== "supabase") return;
    if (!supabaseLibrary ||
        typeof supabaseLibrary.createClient !== "function" ||
        typeof health.supabase_url !== "string" ||
        typeof health.supabase_publishable_key !== "string") {
      throw new Error(t("login_config_error"));
    }
    const configKey =
      `${health.supabase_url}\n${health.supabase_publishable_key}`;
    if (!supabaseClient || supabaseConfigKey !== configKey) {
      supabaseClient = supabaseLibrary.createClient(
        health.supabase_url,
        health.supabase_publishable_key,
        {
          auth: {
            persistSession: true,
            autoRefreshToken: true,
            detectSessionInUrl: true
          }
        }
      );
      supabaseConfigKey = configKey;
      supabaseClient.auth.onAuthStateChange((event, session) => {
        sessionToken = session?.access_token || "";
        currentUserId = session?.user?.id || "";
        if (event === "SIGNED_OUT" && serverAuthRequired) redirectToLogin();
      });
    }
    const { data, error } = await supabaseClient.auth.getSession();
    if (error) throw error;
    sessionToken = data.session?.access_token || "";
    currentUserId = data.session?.user?.id || "";
  }

  const presets = {
    ariana: ["Ariana (governorate capital)", 36.8625, 10.19556, 0],
    beja: ["Beja (governorate capital)", 36.73333, 9.18333, 0],
    "ben-arous": ["Ben Arous (governorate capital)", 36.75333, 10.2222, 0],
    bizerte: ["Bizerte (governorate capital)", 37.29, 9.87, 0],
    gabes: ["Gabes (governorate capital)", 33.88333, 10.11667, 0],
    gafsa: ["Gafsa (governorate capital)", 34.425, 8.78417, 0],
    jendouba: ["Jendouba (governorate capital)", 36.50111, 8.77944, 0],
    kairouan: ["Kairouan (governorate capital)", 35.68, 10.1, 0],
    kasserine: ["Kasserine (governorate capital)", 35.18, 8.83, 0],
    kebili: ["Kebili (governorate capital)", 33.70194, 8.97361, 0],
    "le-kef": ["Le Kef (governorate capital)", 36.19, 8.71, 0],
    mahdia: ["Mahdia (governorate capital)", 35.52, 11.07, 0],
    manouba: ["Manouba (governorate capital)", 36.80778, 10.10111, 0],
    medenine: ["Medenine (governorate capital)", 33.35, 10.49, 0],
    monastir: ["Monastir (governorate capital)", 35.79, 10.82, 0],
    nabeul: ["Nabeul (governorate capital)", 36.45, 10.73333, 0],
    sfax: ["Sfax (governorate capital)", 34.74056, 10.76028, 0],
    "sidi-bouzid": ["Sidi Bouzid (governorate capital)", 35.04028, 9.49361, 0],
    siliana: ["Siliana (governorate capital)", 36.08333, 9.36667, 0],
    sousse: ["Sousse (governorate capital)", 35.82556, 10.64111, 0],
    tataouine: ["Tataouine (governorate capital)", 32.93333, 10.45, 0],
    tozeur: ["Tozeur (governorate capital)", 33.93, 8.13, 0],
    tunis: ["Tunis (governorate capital)", 36.80278, 10.17972, 0],
    zaghouan: ["Zaghouan (governorate capital)", 36.4, 10.14, 0],
    djerba: ["Djerba (illustrative location)", 33.8076, 10.8451, 0],
  };

  const byId = id => document.getElementById(id);
  const form = byId("optimizer-form");
  const runButton = byId("run-button");
  const statusBox = byId("job-status");
  const results = byId("results");
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }
  let currentReport = null;
  let currentProjectId = "";
  let currentProductionRecords = [];
  let savedReportSource = "server";
  let savedProjects = new Map();
  let cloudStorageAvailable = false;
  let deferredInstall = null;
  let iosInstallAvailable = false;

  const create = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };

  const t = (key, values) => i18n?.t(key, values) || key;
  const formatNumber = (value, digits = 1) =>
    i18n?.formatNumber(value, digits) ??
    new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(value);

  function populateEquipmentSelect(
    selectId, presets, defaultValue, customTranslation
  ) {
    const select = byId(selectId);
    const previousValue = select.value || defaultValue;
    const groups = new Map();
    Object.entries(presets || {}).forEach(([value, preset]) => {
      if (!groups.has(preset.manufacturer)) {
        groups.set(preset.manufacturer, []);
      }
      groups.get(preset.manufacturer).push([value, preset]);
    });
    select.replaceChildren();
    [...groups.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .forEach(([manufacturer, entries]) => {
        const group = document.createElement("optgroup");
        group.label = manufacturer;
        entries
          .sort(([, left], [, right]) =>
            left.model.localeCompare(right.model, undefined, { numeric: true }))
          .forEach(([value, preset]) => {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = `${preset.manufacturer} ${preset.model}`;
            group.append(option);
          });
        select.append(group);
      });
    const custom = document.createElement("option");
    custom.value = "custom";
    custom.textContent = t(customTranslation);
    select.append(custom);
    select.value = [...select.options].some(
      option => option.value === previousValue
    ) ? previousValue : defaultValue;
  }

  function populateEquipmentSelects() {
    populateEquipmentSelect(
      "inverter-model",
      systemConfig?.INVERTER_PRESETS,
      "sungrow-sg4rs",
      "custom_inverter"
    );
    populateEquipmentSelect(
      "panel-model",
      systemConfig?.PANEL_PRESETS,
      "custom",
      "custom_panel"
    );
  }

  function saveFormDraft() {
    const draft = {};
    draftFields.forEach(id => {
      const node = byId(id);
      draft[id] = node.type === "checkbox" ? node.checked : node.value;
    });
    try {
      localStorage.setItem(draftStorageKey, JSON.stringify(draft));
    } catch {
      return;
    }
  }

  function restoreFormDraft() {
    let draft;
    try {
      draft = JSON.parse(localStorage.getItem(draftStorageKey) || "null");
    } catch {
      return;
    }
    if (!draft || typeof draft !== "object" || Array.isArray(draft)) return;
    draftFields.forEach(id => {
      const node = byId(id);
      if (!node || !Object.hasOwn(draft, id)) return;
      if (node.type === "checkbox") {
        node.checked = draft[id] === true;
      } else if (node.tagName === "SELECT") {
        const value = String(draft[id]);
        if ([...node.options].some(option => option.value === value)) node.value = value;
      } else if (typeof draft[id] === "string" || typeof draft[id] === "number") {
        node.value = String(draft[id]);
      }
    });
    if (!Object.hasOwn(draft, "loss-preset") && Number(byId("losses").value) > 0) {
      byId("loss-preset").value = "custom";
    }
  }

  const analysisProfiles = Object.freeze({
    quick: Object.freeze({
      coarseStep: "15",
      fineStep: "1",
      timingSensitivity: false,
      pvgisBenchmark: true,
      historicalRange: false
    }),
    standard: Object.freeze({
      coarseStep: "10",
      fineStep: "1",
      timingSensitivity: false,
      pvgisBenchmark: true,
      historicalRange: false
    }),
    detailed: Object.freeze({
      coarseStep: "5",
      fineStep: "0.5",
      timingSensitivity: true,
      pvgisBenchmark: true,
      historicalRange: false
    }),
    historical: Object.freeze({
      coarseStep: "5",
      fineStep: "0.5",
      timingSensitivity: true,
      pvgisBenchmark: true,
      historicalRange: true
    })
  });

  function applyAnalysisProfile() {
    const profile = analysisProfiles[byId("analysis-profile").value];
    if (!profile) return;
    byId("coarse-step").value = profile.coarseStep;
    byId("fine-step").value = profile.fineStep;
    byId("timing-sensitivity").checked = profile.timingSensitivity;
    byId("pvgis-benchmark").checked = profile.pvgisBenchmark;
    byId("historical-range").checked = profile.historicalRange;
  }

  function applyLossPreset() {
    const value = byId("loss-preset").value;
    const custom = value === "custom";
    byId("losses-field").classList.toggle("hidden", !custom);
    if (!custom) byId("losses").value = value;
  }

  const engineeringLossFields = Object.freeze({
    soiling: "loss-soiling",
    shading: "loss-shading",
    mismatch: "loss-mismatch",
    wiring: "loss-wiring",
    availability: "loss-availability",
    quality: "loss-quality"
  });

  function engineeringLosses() {
    const values = {};
    let retention = 1;
    Object.entries(engineeringLossFields).forEach(([key, id]) => {
      const value = Number(byId(id).value);
      values[key] = Number.isFinite(value) ? value : 0;
      retention *= 1 - values[key] / 100;
    });
    return {
      values,
      combinedPercent: 100 * (1 - retention)
    };
  }

  function updateLossSummary() {
    const detailed = byId("loss-mode").value === "engineering";
    const summary = byId("loss-summary");
    summary.classList.toggle("hidden", !detailed);
    if (!detailed) return;
    const losses = engineeringLosses();
    byId("losses").value = conciseNumber(losses.combinedPercent, 4);
    summary.textContent = t("combined_loss", {
      value: formatNumber(losses.combinedPercent, 2)
    });
  }

  function applyLossMode() {
    const detailed = byId("loss-mode").value === "engineering";
    byId("engineering-loss-fields").classList.toggle("hidden", !detailed);
    byId("loss-preset-field").classList.toggle("hidden", detailed);
    if (detailed) {
      byId("losses-field").classList.add("hidden");
    } else {
      applyLossPreset();
    }
    updateLossSummary();
  }

  function selectedInverterPreset() {
    return systemConfig?.INVERTER_PRESETS?.[byId("inverter-model").value] || null;
  }

  function selectedPanelPreset() {
    return systemConfig?.PANEL_PRESETS?.[byId("panel-model").value] || null;
  }

  function equipmentName(preset, fallback) {
    return preset ? `${preset.manufacturer} ${preset.model}` : fallback;
  }

  function updateDatasheetLink(linkId, sourceUrl) {
    const link = byId(linkId);
    link.classList.toggle("hidden", !sourceUrl);
    if (sourceUrl) link.href = sourceUrl;
  }

  function renderEquipmentCards() {
    const panel = selectedPanelPreset();
    byId("panel-spec-title").textContent = equipmentName(
      panel, t("custom_panel")
    );
    byId("panel-spec-details").textContent = panel
      ? [
          `${formatNumber(panel.powerW, 0)} W`,
          `${formatNumber(panel.gammaPercentPerC, 2)}%/°C`,
          t(panel.construction),
          panel.series
        ].join(" · ")
      : t("custom_panel_help");
    updateDatasheetLink("panel-datasheet-link", panel?.sourceUrl);

    const inverter = selectedInverterPreset();
    byId("inverter-spec-title").textContent = equipmentName(
      inverter, t("custom_inverter")
    );
    byId("inverter-spec-details").textContent = inverter
      ? [
          `${formatNumber(inverter.acRatingKw, 2)} kW AC`,
          `${formatNumber(inverter.efficiencyPercent, 1)}% ${t(
            inverter.efficiencyType === "european"
              ? "european_efficiency"
              : "nominal_efficiency"
          )}`,
          inverter.recommendedMaxPvInputKw
            ? t("maximum_pv_input", {
                value: formatNumber(inverter.recommendedMaxPvInputKw, 2)
              })
            : null
        ].filter(Boolean).join(" · ")
      : t("custom_inverter_help");
    updateDatasheetLink("inverter-datasheet-link", inverter?.sourceUrl);
  }

  function applyPanelPreset() {
    const preset = selectedPanelPreset();
    const power = byId("panel-power");
    const gamma = byId("gamma-pdc");
    power.readOnly = Boolean(preset);
    gamma.readOnly = Boolean(preset);
    if (preset) {
      power.value = preset.powerW;
      gamma.value = preset.gammaPercentPerC;
    }
    renderEquipmentCards();
    updateSystemSizing();
  }

  function applyInverterPreset() {
    const preset = selectedInverterPreset();
    const rating = byId("inverter-ac-rating");
    const efficiency = byId("inverter-efficiency");
    rating.readOnly = Boolean(preset);
    efficiency.readOnly = Boolean(preset);
    if (preset) {
      rating.value = preset.acRatingKw;
      efficiency.value = preset.efficiencyPercent;
    }
    renderEquipmentCards();
    updateSystemSizing();
  }

  function conciseNumber(value, digits = 3) {
    return Number(value.toFixed(digits)).toString();
  }

  function currentSizingMode() {
    const mode = byId("system-size-mode").value;
    return ["panels", "capacity", "normalized"].includes(mode)
      ? mode
      : "panels";
  }

  function applySizingMode() {
    const mode = currentSizingMode();
    const panelDetails = mode === "panels";
    const directCapacity = mode === "capacity";
    const normalized = mode === "normalized";
    byId("panel-count-field").classList.toggle("hidden", !panelDetails);
    byId("panel-power-field").classList.toggle("hidden", !panelDetails);
    byId("capacity-field").classList.toggle("hidden", normalized);
    byId("inverter-model-field").classList.toggle("hidden", normalized);
    byId("inverter-ac-rating-field").classList.toggle("hidden", normalized);
    byId("inverter-spec-card").classList.toggle("hidden", normalized);
    byId("panel-count").required = panelDetails;
    byId("panel-power").required = panelDetails;
    byId("capacity").readOnly = !directCapacity;
    byId("capacity").placeholder = directCapacity ? "e.g. 4.5" : "";
    if (normalized) {
      byId("capacity").value = systemConfig.NORMALIZED_CAPACITY_KW;
    }
    updateSystemSizing();
  }

  function applyExistingOrientationMode() {
    const enabled = byId("existing-orientation-enabled").checked;
    byId("existing-tilt-field").classList.toggle("hidden", !enabled);
    byId("existing-azimuth-field").classList.toggle("hidden", !enabled);
    byId("existing-tilt").required = enabled;
    byId("existing-azimuth").required = enabled;
  }

  function applyElevationMode() {
    const manual = byId("elevation-mode").value === "manual";
    byId("altitude-field").classList.toggle("hidden", !manual);
    byId("altitude").required = manual;
  }

  function selectedPeriodMonths() {
    return Array.from({ length: 12 }, (_, index) => index + 1)
      .filter(month => byId(`period-month-${month}`).checked);
  }

  function applyPeriodAnalysis() {
    const custom = byId("period-analysis").value === "custom";
    byId("custom-months-field").classList.toggle("hidden", !custom);
    const selected = selectedPeriodMonths();
    byId("period-analysis").setCustomValidity(
      custom && selected.length === 0 ? t("select_month_error") : ""
    );
  }

  function updateSystemSizing() {
    const mode = currentSizingMode();
    const count = byId("panel-count");
    const power = byId("panel-power");
    const capacity = byId("capacity");
    const inverterRating = byId("inverter-ac-rating");
    const summary = byId("system-size-summary");
    count.setCustomValidity("");
    power.setCustomValidity("");
    capacity.setCustomValidity("");
    inverterRating.setCustomValidity("");
    summary.classList.remove("invalid");

    if (mode === "normalized") {
      capacity.value = systemConfig.NORMALIZED_CAPACITY_KW;
      summary.textContent = t("normalized_summary");
      return;
    }

    try {
      const capacityKw = systemConfig.systemCapacityKw(
        mode, count.value, power.value, capacity.value
      );
      if (mode === "panels") capacity.value = conciseNumber(capacityKw);
      const ratio = systemConfig.dcAcRatio(
        capacityKw, inverterRating.value
      );
      const preset = selectedInverterPreset();
      const recommendedMax = preset?.recommendedMaxPvInputKw;
      const sizingTarget = mode === "capacity" ? capacity : power;
      if (recommendedMax && capacityKw > recommendedMax) {
        sizingTarget.setCustomValidity(
          t("panel_capacity_error", { limit: recommendedMax })
        );
        summary.textContent =
          t("panel_limit", {
            dc: conciseNumber(capacityKw),
            limit: recommendedMax
          });
        summary.classList.add("invalid");
      } else if (ratio < 0.5 || ratio > 3) {
        const ratioTarget = preset ? sizingTarget : inverterRating;
        ratioTarget.setCustomValidity(
          t("ratio_error")
        );
        summary.textContent =
          t("sizing_summary", {
            dc: conciseNumber(capacityKw),
            ac: conciseNumber(Number(inverterRating.value)),
            ratio: ratio.toFixed(2)
          });
        summary.classList.add("invalid");
      } else {
        summary.textContent =
          t("sizing_summary", {
            dc: conciseNumber(capacityKw),
            ac: conciseNumber(Number(inverterRating.value)),
            ratio: ratio.toFixed(2)
          });
      }
    } catch {
      if (mode === "panels") {
        capacity.value = "";
        if (count.value &&
            (!Number.isInteger(Number(count.value)) || Number(count.value) <= 0)) {
          count.setCustomValidity(t("panel_count_error"));
        }
        if (power.value &&
            (!Number.isFinite(Number(power.value)) || Number(power.value) <= 0)) {
          power.setCustomValidity(t("panel_power_error"));
        }
        summary.textContent =
          count.value || power.value ? t("complete_panels") : "";
      } else {
        if (capacity.value) {
          capacity.setCustomValidity(t("dc_capacity_error"));
        }
        summary.textContent = "";
      }
    }
  }

  function reportFilename(extension) {
    const slug = currentReport.site.name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "report";
    return `solarna-${slug}.${extension}`;
  }

  function downloadBlob(blob, filename) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  function safeCsvCell(value) {
    const userText = typeof value === "string";
    let text = value === null || value === undefined ? "" : String(value);
    if (userText && /^[=+\-@]/.test(text)) text = `'${text}`;
    return `"${text.replaceAll('"', '""')}"`;
  }

  function reportCsv(report) {
    const rows = [["category", "metric", "value", "unit"]];
    const add = (category, metric, value, unit = "") =>
      rows.push([category, metric, value, unit]);
    add("site", "name", report.site.name);
    add("site", "latitude", report.site.latitude, "degrees");
    add("site", "longitude", report.site.longitude, "degrees");
    add("site", "altitude", report.site.altitude_m, "m");
    add(
      "site",
      "elevation_source",
      report.site_elevation?.source || "not recorded"
    );
    add("system", "dc_capacity", report.system.dc_capacity_kw, "kWp");
    add("system", "dc_ac_ratio", report.system.dc_ac_ratio);
    add(
      "system",
      "capacity_basis",
      report.application_request?.normalized_capacity === true
        ? "normalized_1_kwp"
        : "installed_capacity"
    );
    add("system", "temperature_model", report.system.temperature_model || "");
    add(
      "system",
      "combined_engineering_loss",
      Number(report.system.other_dc_loss_fraction || 0) * 100,
      "%"
    );
    const engineeringLosses =
      report.application_request?.engineering_losses_percent;
    if (engineeringLosses && typeof engineeringLosses === "object") {
      Object.entries(engineeringLosses).forEach(([key, value]) => {
        add("engineering_loss", key, value, "%");
      });
    }
    add("annual", "best_tilt", report.best.tilt_deg, "degrees");
    add("annual", "best_azimuth_true_north", report.best.azimuth_deg, "degrees");
    add("annual", "ac_energy", report.best.annual_ac_kwh, "kWh");
    add(
      "annual",
      "average_daily_ac_energy",
      report.best.average_daily_ac_kwh ?? report.best.annual_ac_kwh / 365,
      "kWh/day"
    );
    add("annual", "specific_yield", report.best.specific_yield_kwh_per_kwp, "kWh/kWp");
    if (Number(report.best.annual_poa_kwh_m2) > 0) {
      add(
        "annual",
        "estimated_performance_ratio",
        100 * report.best.specific_yield_kwh_per_kwp /
          report.best.annual_poa_kwh_m2,
        "%"
      );
    }
    const accuracy = resultSummary?.estimateAccuracy?.(report);
    if (accuracy) {
      add(
        "accuracy",
        "national_mean_absolute_yield_difference",
        accuracy.nationalValidation.meanAbsoluteYieldDifferencePercent,
        "%"
      );
      add(
        "accuracy",
        "national_maximum_absolute_yield_difference",
        accuracy.nationalValidation.maximumAbsoluteYieldDifferencePercent,
        "%"
      );
      if (accuracy.siteBenchmarkAvailable) {
        add(
          "accuracy",
          "site_absolute_yield_difference_vs_pvgis",
          accuracy.yieldDifferencePercent,
          "%"
        );
        add(
          "accuracy",
          "site_absolute_tilt_difference_vs_pvgis",
          accuracy.tiltDifferenceDeg,
          "degrees"
        );
        add(
          "accuracy",
          "site_absolute_azimuth_difference_vs_pvgis",
          accuracy.azimuthDifferenceDeg,
          "degrees"
        );
      }
    }
    if (report.practical_recommendation) {
      add(
        "practical",
        "tilt",
        report.practical_recommendation.tilt_deg,
        "degrees"
      );
      add(
        "practical",
        "azimuth_true_north",
        report.practical_recommendation.azimuth_deg,
        "degrees"
      );
      add(
        "practical",
        "retained_energy",
        report.practical_recommendation.retained_energy_percent,
        "%"
      );
    }
    Object.entries(report.best.monthly_ac_kwh)
      .sort((a, b) => Number(a[0]) - Number(b[0]))
      .forEach(([month, energy]) => add("monthly", `month_${month}`, energy, "kWh"));
    if (report.period_analysis) {
      const period = report.period_analysis;
      add("period", "label", period.label);
      add("period", "months", period.months.join(" "));
      add("period", "best_tilt", period.best.tilt_deg, "degrees");
      add("period", "best_azimuth_true_north", period.best.azimuth_deg, "degrees");
      add("period", "selected_month_energy", period.best.period_ac_kwh, "kWh");
      add("period", "annual_energy_tradeoff", period.annual_energy_tradeoff_kwh, "kWh");
    }
    if (report.pvgis_benchmark?.status === "available") {
      const pvgis = report.pvgis_benchmark.pvgis_result;
      const comparison = report.pvgis_benchmark.comparison;
      add("pvgis", "best_tilt", pvgis.tilt_deg, "degrees");
      add("pvgis", "best_azimuth_true_north", pvgis.azimuth_deg_true_north, "degrees");
      add("pvgis", "specific_yield", pvgis.annual_ac_kwh_per_kwp, "kWh/kWp");
      add("pvgis", "solarna_yield_delta", comparison.specific_yield_delta_percent_of_pvgis, "%");
    }
    if (report.historical_range?.status === "available") {
      const history = report.historical_range;
      const optimum = history.orientations.tmy_optimum;
      add("historical", "start_year", history.start_year);
      add("historical", "end_year", history.end_year);
      add("historical", "year_count", history.year_count);
      add(
        "historical",
        "tmy_optimum_p10_specific_yield",
        optimum.p10_specific_yield_kwh_per_kwp,
        "kWh/kWp"
      );
      add(
        "historical",
        "tmy_optimum_median_specific_yield",
        optimum.median_specific_yield_kwh_per_kwp,
        "kWh/kWp"
      );
      add(
        "historical",
        "tmy_optimum_p90_specific_yield",
        optimum.p90_specific_yield_kwh_per_kwp,
        "kWh/kWp"
      );
      Object.entries(optimum.annual_specific_yield_kwh_per_kwp_by_year)
        .sort((a, b) => Number(a[0]) - Number(b[0]))
        .forEach(([year, energy]) =>
          add("historical_year", year, energy, "kWh/kWp"));
    }
    if (report.existing_orientation) {
      const existing = report.existing_orientation;
      add("current", "tilt", existing.tilt_deg, "degrees");
      add("current", "azimuth_true_north", existing.azimuth_deg, "degrees");
      add("current", "ac_energy", existing.annual_ac_kwh, "kWh");
      add("current", "specific_yield", existing.specific_yield_kwh_per_kwp, "kWh/kWp");
      add("current", "optimized_gain", existing.gain_of_best_kwh, "kWh");
      add("current", "optimized_gain_percent", existing.gain_of_best_percent, "%");
    }
    return "\ufeff" + rows.map(row => row.map(safeCsvCell).join(",")).join("\r\n");
  }

  function setConnection(online, text) {
    const node = byId("connection-status");
    node.textContent = text;
    node.classList.toggle("online", online);
    node.classList.toggle("offline", !online);
    node.setAttribute(
      "aria-label",
      `Connection status: ${text}`
    );
  }

  async function jsonRequest(url, options, authenticate = true) {
    if (nativeShell && !apiBaseUrl) {
      throw new Error(t("server_required_error"));
    }
    const headers = new Headers(options?.headers || {});
    if (authenticate && sessionToken) {
      headers.set("Authorization", `Bearer ${sessionToken}`);
    }
    const response = await fetch(`${apiBaseUrl}${url}`, {
      ...(options || {}),
      headers
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = { error: `Server returned ${response.status}` };
    }
    if (!response.ok) {
      if (response.status === 401) {
        if (authenticate) {
          sessionToken = "";
          try {
            sessionStorage.removeItem("solarna:session-token");
          } catch {
          }
          if (supabaseClient) {
            await supabaseClient.auth.signOut({ scope: "local" });
          }
        }
        throw new Error(payload.error || "Login required.");
      }
      throw new Error(payload.error || `Request failed (${response.status})`);
    }
    return payload;
  }

  function missingCloudSchema(error) {
    const code = String(error?.code || "");
    const message = String(error?.message || "").toLowerCase();
    return code === "42P01" || code === "PGRST205" ||
      message.includes("solarna_projects") &&
      (message.includes("not find") || message.includes("does not exist"));
  }

  function setStorageStatus(message, warning = false) {
    const node = byId("project-storage-status");
    node.textContent = message;
    node.classList.toggle("warning", warning);
  }

  function projectOptionLabel(project) {
    const report = project.report || {};
    const generated = new Date(
      project.updated_at || report.generated_at_utc || ""
    );
    const date = Number.isNaN(generated.getTime())
      ? ""
      : generated.toLocaleString();
    const tilt = Number(report.best?.tilt_deg);
    const azimuth = Number(report.best?.azimuth_deg);
    const orientation = Number.isFinite(tilt) && Number.isFinite(azimuth)
      ? ` · ${formatNumber(tilt, 1)}° / ${formatNumber(azimuth, 1)}°`
      : "";
    return `${project.site_name || project.name}${orientation}${date ? ` · ${date}` : ""}`;
  }

  async function saveReportToCloud(report) {
    if (!supabaseClient || !currentUserId || !cloudStorage) {
      setStorageStatus(t("project_saved_server"), true);
      return false;
    }
    const { data, error } = await supabaseClient
      .from("solarna_projects")
      .insert(cloudStorage.projectFromReport(report, currentUserId))
      .select("id,name,site_name,updated_at,report")
      .single();
    if (error) {
      cloudStorageAvailable = false;
      setStorageStatus(
        t(missingCloudSchema(error)
          ? "project_storage_unavailable"
          : "project_saved_server"),
        true
      );
      return false;
    }
    currentProjectId = data.id;
    cloudStorageAvailable = true;
    setStorageStatus(t("project_saved_cloud"));
    return true;
  }

  async function loadProductionRecords() {
    currentProductionRecords = [];
    if (!supabaseClient || !currentProjectId || !cloudStorageAvailable) {
      renderProductionComparison();
      return;
    }
    const { data, error } = await supabaseClient
      .from("solarna_production_records")
      .select("period_start,period_type,actual_kwh")
      .eq("project_id", currentProjectId)
      .order("period_start", { ascending: true });
    if (error) {
      renderProductionComparison();
      return;
    }
    currentProductionRecords = Array.isArray(data) ? data : [];
    renderProductionComparison();
  }

  function productionPeriodLabel(row) {
    const year = row.period.slice(0, 4);
    return `${i18n?.monthShort(row.month) || row.month} ${year}`;
  }

  function renderProductionComparison(statusMessage = "") {
    const summary = byId("production-summary");
    const chart = byId("production-chart");
    const details = byId("production-table-details");
    const clearButton = byId("production-clear-button");
    summary.classList.add("hidden");
    chart.classList.add("hidden");
    details.classList.add("hidden");
    chart.replaceChildren();
    byId("production-table").replaceChildren();
    clearButton.classList.add("hidden");
    byId("production-import-button").disabled =
      !currentProjectId || !cloudStorageAvailable;

    if (!currentProjectId || !cloudStorageAvailable) {
      byId("production-status").textContent =
        t("production_cloud_required");
      return;
    }
    if (!currentProductionRecords.length) {
      byId("production-status").textContent =
        statusMessage || t("production_empty");
      return;
    }

    let comparison;
    try {
      comparison = cloudStorage.compareProduction(
        currentReport, currentProductionRecords
      );
    } catch (error) {
      byId("production-status").textContent = error.message;
      return;
    }
    byId("production-status").textContent =
      statusMessage || t("production_months", {
        count: comparison.monthCount
      });
    byId("production-actual").textContent =
      `${formatNumber(comparison.actualKwh, 1)} kWh`;
    byId("production-estimated").textContent =
      `${formatNumber(comparison.estimatedKwh, 1)} kWh`;
    const varianceSign = comparison.varianceKwh > 0 ? "+" : "";
    const percentSign = comparison.variancePercent > 0 ? "+" : "";
    byId("production-variance").textContent =
      `${varianceSign}${formatNumber(comparison.varianceKwh, 1)} kWh` +
      (comparison.variancePercent === null
        ? ""
        : ` · ${percentSign}${formatNumber(comparison.variancePercent, 1)}%`);
    byId("production-coverage").textContent =
      t("production_months", { count: comparison.monthCount });

    const maximum = Math.max(
      1,
      ...comparison.rows.flatMap(row => [row.actualKwh, row.estimatedKwh])
    );
    comparison.rows.forEach(row => {
      const item = create("div", undefined, "production-month");
      item.append(create(
        "span", productionPeriodLabel(row), "production-month-label"
      ));
      const bars = create("div", undefined, "production-bars");
      const actualTrack = create("div", undefined, "production-track");
      const actualBar = create("div", undefined, "production-bar actual");
      actualBar.style.width = `${row.actualKwh / maximum * 100}%`;
      actualBar.title = `${t("actual")}: ${formatNumber(row.actualKwh, 1)} kWh`;
      actualTrack.append(actualBar);
      const estimatedTrack = create("div", undefined, "production-track");
      const estimatedBar = create(
        "div", undefined, "production-bar estimated"
      );
      estimatedBar.style.width = `${row.estimatedKwh / maximum * 100}%`;
      estimatedBar.title =
        `${t("estimated")}: ${formatNumber(row.estimatedKwh, 1)} kWh`;
      estimatedTrack.append(estimatedBar);
      bars.append(actualTrack, estimatedTrack);
      item.append(
        bars,
        create(
          "span",
          `${formatNumber(row.actualKwh, 0)} / ` +
            `${formatNumber(row.estimatedKwh, 0)} kWh`,
          "production-month-value"
        )
      );
      chart.append(item);
    });
    const legend = create("div", undefined, "production-legend");
    const actualLegend = create("span");
    actualLegend.append(
      create("i", undefined, "actual"),
      document.createTextNode(t("actual"))
    );
    const estimatedLegend = create("span");
    estimatedLegend.append(
      create("i", undefined, "estimated"),
      document.createTextNode(t("estimated"))
    );
    legend.append(actualLegend, estimatedLegend);
    chart.append(legend);

    const table = create("table");
    const head = create("thead");
    const headRow = create("tr");
    [t("months"), t("actual_energy"), t("estimated_energy"), t("variance")]
      .forEach(label => {
        const cell = create("th", label);
        cell.scope = "col";
        headRow.append(cell);
      });
    head.append(headRow);
    table.append(head);
    const body = create("tbody");
    comparison.rows.forEach(row => {
      const tr = create("tr");
      const period = create("th", productionPeriodLabel(row));
      period.scope = "row";
      tr.append(
        period,
        create("td", formatNumber(row.actualKwh, 1)),
        create("td", formatNumber(row.estimatedKwh, 1)),
        create(
          "td",
          `${row.varianceKwh > 0 ? "+" : ""}` +
            formatNumber(row.varianceKwh, 1)
        )
      );
      body.append(tr);
    });
    table.append(body);
    byId("production-table").append(table);
    summary.classList.remove("hidden");
    chart.classList.remove("hidden");
    details.classList.remove("hidden");
    clearButton.classList.remove("hidden");
  }

  function directionFromSouth(azimuth) {
    const delta = ((azimuth - 180 + 540) % 360) - 180;
    if (Math.abs(delta) < 0.05) return t("due_south");
    return t(delta > 0 ? "west_south" : "east_south", {
      value: formatNumber(Math.abs(delta), 1)
    });
  }

  function degreeRange(start, end) {
    if (Math.abs(start - end) < 0.05) return `${formatNumber(start, 1)}°`;
    return `${formatNumber(start, 1)}–${formatNumber(end, 1)}°`;
  }

  function renderPracticalRange(report) {
    const node = byId("practical-range");
    node.textContent = "";
    try {
      const range = resultSummary.summarizeNearOptimal(
        report.search.near_optimal_sampled_orientations,
        report.search.near_optimal_fraction
      );
      if (!range) return;
      const tilt = degreeRange(range.tiltMinDeg, range.tiltMaxDeg);
      let direction;
      if (range.azimuth.spanDeg > 359.95) {
        direction = t("any_direction");
      } else {
        direction = degreeRange(range.azimuth.startDeg, range.azimuth.endDeg);
        if (range.azimuth.crossesNorth) direction += ` ${t("across_north")}`;
      }
      node.textContent = t("within_maximum", {
        threshold: formatNumber(range.thresholdPercent, 1),
        tilt,
        direction
      });
    } catch {
      node.textContent = "";
    }
  }

  function renderHeatmap(report) {
    const canvas = byId("heatmap");
    const context = canvas.getContext("2d");
    const grid = report.search.coarse_grid;
    const rows = grid.annual_ac_kwh;
    const flat = rows.flat();
    const low = Math.min(...flat);
    const high = Math.max(...flat);
    const left = 62;
    const top = 18;
    const width = 800;
    const height = 300;
    const cellWidth = width / grid.azimuth_deg.length;
    const cellHeight = height / grid.tilt_deg.length;

    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = "#f5f8f7";
    context.fillRect(0, 0, canvas.width, canvas.height);
    rows.forEach((row, rowIndex) => {
      row.forEach((energy, columnIndex) => {
        const ratio = high === low ? 1 : (energy - low) / (high - low);
        const hue = 215 - 175 * ratio;
        const light = 28 + 29 * ratio;
        context.fillStyle = `hsl(${hue} 74% ${light}%)`;
        context.fillRect(
          left + columnIndex * cellWidth,
          top + rowIndex * cellHeight,
          cellWidth + 0.3,
          cellHeight + 0.3
        );
      });
    });

    context.strokeStyle = "rgba(255,255,255,.9)";
    context.lineWidth = 3;
    const bestX = left + (report.best.azimuth_deg / 360) * width;
    const bestY = top + (report.best.tilt_deg / 90) * height;
    context.beginPath();
    context.arc(bestX, bestY, 7, 0, Math.PI * 2);
    context.stroke();

    context.fillStyle = "#173b43";
    context.font = "13px system-ui";
    context.textAlign = "center";
    [[0, "N 0°"], [90, "E 90°"], [180, "S 180°"], [270, "W 270°"], [355, "355°"]]
      .forEach(([angle, label]) => {
        const x = left + (angle / 360) * width;
        context.fillText(label, x, top + height + 24);
      });
    context.textAlign = "right";
    [[0, "0°"], [45, "45°"], [90, "90°"]].forEach(([tilt, label]) => {
      const y = top + (tilt / 90) * height;
      context.fillText(label, left - 8, y + 4);
    });
    context.save();
    context.translate(15, top + height / 2);
    context.rotate(-Math.PI / 2);
    context.textAlign = "center";
    context.fillText("Tilt from horizontal", 0, 0);
    context.restore();
    context.textAlign = "center";
    context.fillText("Azimuth clockwise from true north", left + width / 2, 378);

    const table = create("table");
    const caption = create("caption", "Annual AC energy in kWh. Rows are tilt; columns are azimuth.");
    table.append(caption);
    const head = create("thead");
    const headRow = create("tr");
    const corner = create("th", "Tilt");
    corner.scope = "col";
    headRow.append(corner);
    grid.azimuth_deg.forEach(azimuth => {
      const cell = create("th", `${azimuth}°`);
      cell.scope = "col";
      headRow.append(cell);
    });
    head.append(headRow);
    table.append(head);
    const body = create("tbody");
    rows.forEach((row, index) => {
      const tr = create("tr");
      const rowHead = create("th", `${grid.tilt_deg[index]}°`);
      rowHead.scope = "row";
      tr.append(rowHead);
      row.forEach(energy => tr.append(create("td", formatNumber(energy, 1))));
      body.append(tr);
    });
    table.append(body);
    byId("heatmap-table").replaceChildren(table);
  }

  function energyPresentation(report) {
    const normalized =
      report.application_request?.normalized_capacity === true;
    const capacity = Number(report.system.dc_capacity_kw);
    return {
      normalized,
      unit: normalized ? "kWh/kWp" : "kWh",
      annualUnit: normalized ? "kWh/kWp" : "kWh/year",
      value: energy => normalized ? Number(energy) / capacity : Number(energy)
    };
  }

  function renderMonthly(report) {
    const chart = byId("monthly-chart");
    chart.replaceChildren();
    const presentation = energyPresentation(report);
    byId("monthly-title").textContent =
      presentation.normalized ? t("annual_yield") : t("monthly_energy");
    chart.setAttribute(
      "aria-label",
      presentation.normalized
        ? "Monthly specific yield bar chart"
        : "Monthly AC energy bar chart"
    );
    const months = Object.entries(report.best.monthly_ac_kwh)
      .map(([month, energy]) => [
        Number(month),
        presentation.value(energy)
      ])
      .sort((a, b) => a[0] - b[0]);
    const maximum = Math.max(...months.map(item => item[1]));
    months.forEach(([month, energy]) => {
      const item = create("div", undefined, "month");
      const bar = create("div", undefined, "month-bar");
      bar.style.height = `${Math.max(2, energy / maximum * 220)}px`;
      bar.title = `${formatNumber(energy, 1)} ${presentation.unit}`;
      const value = create("b", formatNumber(energy, 0));
      const label = create("span", i18n?.monthShort(month) || String(month));
      item.append(bar, value, label);
      chart.append(item);
    });
  }

  function renderLossDiagram(report) {
    const chart = byId("loss-chart");
    chart.replaceChildren();
    const request = report.application_request || {};
    const configured = request.engineering_losses_percent;
    const labelKeys = {
      soiling: "soiling_loss",
      shading: "shading_loss",
      mismatch: "mismatch_loss",
      wiring: "wiring_loss",
      availability: "availability_loss",
      quality: "quality_loss"
    };
    const losses = configured && typeof configured === "object"
      ? Object.entries(labelKeys).map(([key, label]) => ({
        label: t(label),
        value: Number(configured[key] || 0)
      }))
      : [{
        label: t("additional_losses"),
        value: Number(report.system.other_dc_loss_fraction || 0) * 100
      }];
    losses.push({
      label: t("inverter_efficiency"),
      value: Math.max(0, 100 - Number(report.system.inverter_efficiency || 1) * 100)
    });
    const maximum = Math.max(5, ...losses.map(item => item.value));
    losses.forEach(loss => {
      const row = create("div", undefined, "loss-row");
      const heading = create("div", undefined, "loss-row-heading");
      heading.append(
        create("span", loss.label),
        create("strong", `${formatNumber(loss.value, 1)}%`)
      );
      const track = create("div", undefined, "loss-track");
      const bar = create("div", undefined, "loss-bar");
      bar.style.width = `${Math.max(0, loss.value / maximum * 100)}%`;
      track.append(bar);
      row.append(heading, track);
      chart.append(row);
    });
    const poa = Number(report.best.annual_poa_kwh_m2);
    const specificYield = Number(report.best.specific_yield_kwh_per_kwp);
    const performanceRatio = poa > 0 ? 100 * specificYield / poa : null;
    byId("performance-ratio").textContent = performanceRatio === null
      ? "—"
      : `${formatNumber(performanceRatio, 1)}%`;
  }

  function renderTiming(report) {
    const container = byId("timing-details");
    container.replaceChildren();
    const offset = report.timing.irradiance_time_offset_hours;
    container.append(create(
      "p",
      `Solar timing correction: ${formatNumber(offset * 60, 1)} minutes.`
    ));
    if (report.timing_sensitivity) {
      const old = report.timing_sensitivity.zero_offset_best;
      container.append(create(
        "p",
        `Timing comparison: ${formatNumber(old.tilt_deg, 1)}° tilt, ` +
        `${formatNumber(old.azimuth_deg, 1)}° direction. Change: ` +
        `${formatNumber(report.timing_sensitivity.tilt_change_deg, 1)}° tilt and ` +
        `${formatNumber(report.timing_sensitivity.azimuth_change_deg, 1)}° azimuth.`
      ));
    }
    if (report.period_analysis) {
      const period = report.period_analysis;
      const periodBest = period.best;
      const presentation = energyPresentation(report);
      container.append(create("h4", period.label));
      container.append(
        create(
          "p",
          `${formatNumber(periodBest.tilt_deg, 1)}° tilt, ` +
          `${formatNumber(periodBest.azimuth_deg, 1)}° direction, ` +
          `${formatNumber(presentation.value(periodBest.period_ac_kwh), 1)} ` +
          `${presentation.unit}. Annual trade-off: ` +
          `${formatNumber(presentation.value(period.annual_energy_tradeoff_kwh), 1)} ` +
          `${presentation.unit}.`
        )
      );
    }
    const history = report.historical_range;
    if (history) {
      container.append(create("h4", t("historical_heading")));
      if (history.status !== "available") {
        container.append(
          create("p", history.note || t("historical_unavailable")),
          create("p", history.error || "", "muted")
        );
      } else {
        const optimum = history.orientations.tmy_optimum;
        container.append(
          create(
            "p",
            t("historical_summary", {
              start: history.start_year,
              end: history.end_year,
              median: formatNumber(
                optimum.median_specific_yield_kwh_per_kwp, 1
              ),
              p10: formatNumber(
                optimum.p10_specific_yield_kwh_per_kwp, 1
              ),
              p90: formatNumber(
                optimum.p90_specific_yield_kwh_per_kwp, 1
              )
            })
          ),
          create("p", t("historical_note"), "muted")
        );
        const existingComparison =
          history.comparisons.tmy_optimum_minus_existing_installation;
        if (existingComparison) {
          container.append(create(
            "p",
            t("historical_gain", {
              value: formatNumber(existingComparison.median_gain_percent, 2)
            }),
            "muted"
          ));
        }
      }
    }
    const benchmark = report.pvgis_benchmark;
    if (benchmark) {
      container.append(create("h4", t("pvgis_heading")));
    }
    if (benchmark?.status !== "available" && benchmark) {
      container.append(
        create("p", benchmark.note || t("benchmark_unavailable")),
        create("p", benchmark.error || "", "muted")
      );
    } else if (benchmark) {
      const pvgis = benchmark.pvgis_result;
      const comparison = benchmark.comparison;
      container.append(
        create(
          "p",
          t("pvgis_summary", {
            tilt: formatNumber(pvgis.tilt_deg, 1),
            direction: formatNumber(pvgis.azimuth_deg_true_north, 1),
            yield: formatNumber(pvgis.annual_ac_kwh_per_kwp, 1)
          })
        ),
        create(
          "p",
          t("benchmark_difference", {
            tilt: formatNumber(comparison.tilt_delta_deg, 1),
            direction: formatNumber(comparison.azimuth_delta_deg, 1),
            yield: formatNumber(
              comparison.specific_yield_delta_percent_of_pvgis, 2
            ),
            variation: formatNumber(pvgis.interannual_sd_percent, 1)
          }),
          "muted"
        ),
        create("p", t("model_comparison"), "muted")
      );
    }
  }

  function renderAccuracy(report) {
    const estimate = resultSummary.estimateAccuracy(report);
    const national = estimate.nationalValidation;
    byId("model-agreement").textContent = estimate.agreementLabel;
    byId("model-agreement-detail").textContent = estimate.siteBenchmarkAvailable
      ? `${formatNumber(estimate.yieldDifferencePercent, 2)}% yield difference`
      : `${formatNumber(national.meanAbsoluteYieldDifferencePercent, 2)}% national mean`;

    byId("accuracy-summary").textContent = estimate.siteBenchmarkAvailable
      ? t("accuracy_site", {
          yield: formatNumber(estimate.yieldDifferencePercent, 2),
          tilt: formatNumber(estimate.tiltDifferenceDeg, 1),
          direction: formatNumber(estimate.azimuthDifferenceDeg, 1),
          sites: national.siteCount,
          mean: formatNumber(
            national.meanAbsoluteYieldDifferencePercent, 2
          ),
          maximum: formatNumber(
            national.maximumAbsoluteYieldDifferencePercent, 2
          )
        })
      : t("accuracy_national", {
          sites: national.siteCount,
          mean: formatNumber(
            national.meanAbsoluteYieldDifferencePercent, 2
          ),
          maximum: formatNumber(
            national.maximumAbsoluteYieldDifferencePercent, 2
          )
        });

    const history = estimate.historicalRange;
    byId("planning-range").textContent = history &&
      history.p10SpecificYieldKwhPerKwp !== null &&
      history.p90SpecificYieldKwhPerKwp !== null
      ? t("planning_history", {
          p10: formatNumber(history.p10SpecificYieldKwhPerKwp, 0),
          p90: formatNumber(history.p90SpecificYieldKwhPerKwp, 0)
        })
      : t("planning_basic");

    const mountingNote = byId("mounting-accuracy-note");
    if (report.system.temperature_model === "insulated_back_glass_polymer") {
      mountingNote.textContent = t("mounting_limited");
      mountingNote.classList.remove("hidden");
    } else {
      mountingNote.textContent = "";
      mountingNote.classList.add("hidden");
    }

    const list = byId("improvement-suggestions");
    list.replaceChildren();
    resultSummary.improvementSuggestions(report).forEach(item => {
      list.append(create("li", item));
    });
  }

  function renderTunisiaStudyComparison(report) {
    const best = report.best;
    const pvgis = report.pvgis_benchmark?.status === "available"
      ? report.pvgis_benchmark.pvgis_result
      : null;
    const pvgisText = pvgis
      ? t("pvgis_run", {
        tilt: formatNumber(pvgis.tilt_deg, 1),
        azimuth: formatNumber(pvgis.azimuth_deg_true_north, 1)
      })
      : "";
    byId("tunisia-site-comparison").textContent =
      t("site_run", {
        tilt: formatNumber(best.tilt_deg, 1),
        azimuth: formatNumber(best.azimuth_deg, 1)
      }) + pvgisText;
  }

  function renderReport(report, sourceLabel = "Result", scrollToResult = true) {
    currentReport = report;
    localStorage.setItem("solarna:last-report", JSON.stringify(report));
    const site = report.site;
    const best = report.best;
    const presentation = energyPresentation(report);
    byId("results-kicker").textContent = sourceLabel;
    byId("results-title").textContent = site.name;
    byId("results-location").textContent =
      `${formatNumber(site.latitude, 4)}°, ${formatNumber(site.longitude, 4)}° · ` +
      `${formatNumber(site.altitude_m, 0)} m · ` +
      (presentation.normalized
        ? "normalized per kWp"
        : `${formatNumber(report.system.dc_capacity_kw, 2)} kWp`);
    byId("best-tilt").textContent = `${formatNumber(best.tilt_deg, 1)}°`;
    byId("best-azimuth").textContent = `${formatNumber(best.azimuth_deg, 1)}°`;
    byId("azimuth-description").textContent = directionFromSouth(best.azimuth_deg);
    byId("annual-energy-label").textContent =
      presentation.normalized ? t("annual_yield") : t("annual_energy");
    byId("annual-energy").textContent =
      `${formatNumber(presentation.value(best.annual_ac_kwh), 1)} ${presentation.unit}`;
    const averageDailyEnergy = presentation.value(
      best.average_daily_ac_kwh ?? best.annual_ac_kwh / 365
    );
    byId("specific-yield").textContent = presentation.normalized
      ? `${formatNumber(averageDailyEnergy, 2)} kWh/kWp/day · ${t("annual_average")}`
      : `${formatNumber(averageDailyEnergy, 1)} kWh/day · ${t("annual_average")} · ` +
        `${formatNumber(best.specific_yield_kwh_per_kwp, 1)} kWh/kWp`;
    byId("daily-energy").textContent =
      `${formatNumber(
        averageDailyEnergy, presentation.normalized ? 2 : 1
      )} ${presentation.normalized ? "kWh/kWp/day" : "kWh/day"}`;
    byId("daily-energy-detail").textContent =
      t("daily_varies");

    const practicalRecommendation = report.practical_recommendation;
    if (practicalRecommendation) {
      byId("practical-orientation").textContent =
        `${formatNumber(practicalRecommendation.tilt_deg, 0)}° / ` +
        `${formatNumber(practicalRecommendation.azimuth_deg, 0)}°`;
      byId("practical-retention").textContent =
        t("retained", {
          value: formatNumber(practicalRecommendation.retained_energy_percent, 2)
        });
    } else {
      byId("practical-orientation").textContent = "—";
      byId("practical-retention").textContent = t("not_available");
    }

    let practical;
    if (practicalRecommendation) {
      practical = t("use_setting", {
        tilt: formatNumber(practicalRecommendation.tilt_deg, 0),
        direction: directionFromSouth(practicalRecommendation.azimuth_deg),
        loss: formatNumber(
          practicalRecommendation.loss_from_numerical_best_percent, 3
        )
      });
    } else {
      practical = t("use_optimum");
    }
    byId("practical-summary").textContent = practical;
    renderPracticalRange(report);
    const existingSummary = byId("existing-orientation-summary");
    if (report.existing_orientation) {
      const existing = report.existing_orientation;
      const gainPercent = existing.gain_of_best_percent === null
        ? ""
        : ` (${formatNumber(existing.gain_of_best_percent, 2)}%)`;
      existingSummary.textContent = t("current_summary", {
        tilt: formatNumber(existing.tilt_deg, 1),
        azimuth: formatNumber(existing.azimuth_deg, 1),
        energy: formatNumber(presentation.value(existing.annual_ac_kwh), 1),
        unit: presentation.annualUnit,
        daily: formatNumber(
          presentation.value(
            existing.average_daily_ac_kwh ?? existing.annual_ac_kwh / 365
          ), presentation.normalized ? 2 : 1
        ),
        dailyUnit: presentation.normalized ? "kWh/kWp/day" : "kWh/day",
        gain: formatNumber(
          presentation.value(existing.gain_of_best_kwh), 1
        ),
        percent: gainPercent
      });
      existingSummary.classList.remove("hidden");
    } else {
      existingSummary.textContent = "";
      existingSummary.classList.add("hidden");
    }

    renderAccuracy(report);
    renderTunisiaStudyComparison(report);
    renderHeatmap(report);
    renderMonthly(report);
    renderLossDiagram(report);
    renderProductionComparison();
    renderTiming(report);
    const limitations = byId("limitations");
    limitations.replaceChildren();
    report.assumptions_and_limitations.forEach(item => limitations.append(create("li", item)));
    byId("provenance").textContent = JSON.stringify({
      weather_source: report.weather_source,
      system: report.system,
      search: {
        coarse_step_deg: report.search.coarse_step_deg,
        fine_step_deg: report.search.fine_step_deg,
        candidate_count: report.search.candidate_count
      },
      software: report.software,
      angle_convention: report.angle_convention,
      site_elevation: report.site_elevation || null,
      practical_recommendation: report.practical_recommendation || null,
      pvgis_benchmark: report.pvgis_benchmark ? {
        status: report.pvgis_benchmark.status,
        source: report.pvgis_benchmark.source,
        request: report.pvgis_benchmark.request,
        provider_context: report.pvgis_benchmark.provider_context,
        pvgis_result: report.pvgis_benchmark.pvgis_result,
        comparison: report.pvgis_benchmark.comparison
      } : null,
      historical_range: report.historical_range || null,
      existing_orientation: report.existing_orientation || null
    }, null, 2);
    results.classList.remove("hidden");
    if (scrollToResult) {
      results.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function payloadFromForm() {
    const mode = currentSizingMode();
    const normalized = mode === "normalized";
    const capacity = systemConfig.systemCapacityKw(
      mode,
      byId("panel-count").value,
      byId("panel-power").value,
      byId("capacity").value
    );
    const inverterAcRating = Number(byId("inverter-ac-rating").value);
    const elevationMode = byId("elevation-mode").value;
    const periodAnalysis = byId("period-analysis").value;
    const detailedLosses = byId("loss-mode").value === "engineering"
      ? engineeringLosses()
      : null;
    return {
      name: byId("name").value.trim(),
      latitude: Number(byId("latitude").value),
      longitude: Number(byId("longitude").value),
      elevation_mode: elevationMode,
      altitude_m: elevationMode === "manual"
        ? Number(byId("altitude").value)
        : null,
      capacity_kw: capacity,
      dc_ac_ratio: normalized
        ? systemConfig.NORMALIZED_DC_AC_RATIO
        : systemConfig.dcAcRatio(capacity, inverterAcRating),
      normalized_capacity: normalized,
      albedo: Number(byId("albedo").value),
      loss_model: detailedLosses ? "engineering" : "simple",
      engineering_losses_percent: detailedLosses
        ? detailedLosses.values
        : null,
      other_dc_loss_percent: detailedLosses
        ? detailedLosses.combinedPercent
        : Number(byId("losses").value),
      gamma_pdc_percent_per_c: Number(byId("gamma-pdc").value),
      inverter_efficiency_percent: Number(byId("inverter-efficiency").value),
      temperature_model: byId("temperature-model").value,
      panel_model: equipmentName(selectedPanelPreset(), "Custom"),
      inverter_model: normalized
        ? null
        : equipmentName(selectedInverterPreset(), "Custom"),
      coarse_step: Number(byId("coarse-step").value),
      fine_step: Number(byId("fine-step").value),
      timing_sensitivity: byId("timing-sensitivity").checked,
      period_analysis: periodAnalysis,
      period_months: periodAnalysis === "custom"
        ? selectedPeriodMonths()
        : null,
      pvgis_benchmark: byId("pvgis-benchmark").checked,
      historical_range: byId("historical-range").checked,
      existing_tilt_deg: byId("existing-orientation-enabled").checked
        ? Number(byId("existing-tilt").value)
        : null,
      existing_azimuth_deg: byId("existing-orientation-enabled").checked
        ? Number(byId("existing-azimuth").value)
        : null
    };
  }

  function validateSystemSizing() {
    updateSystemSizing();
    updateLossSummary();
    applyPeriodAnalysis();
  }

  function setJobState(job) {
    statusBox.classList.remove("hidden");
    statusBox.classList.toggle("failed", job.status === "failed");
    byId("job-message").textContent = job.message;
    byId("job-percent").textContent = `${Math.round(job.progress * 100)}%`;
    byId("job-progress").value = job.progress;
    byId("job-detail").textContent =
      job.phase.replaceAll("_", " ");
  }

  async function pollJob(job) {
    let state = job;
    while (state.status === "queued" || state.status === "running") {
      setJobState(state);
      await new Promise(resolve => window.setTimeout(resolve, 900));
      state = await jsonRequest(`/api/jobs/${state.id}`);
    }
    setJobState(state);
    if (state.status === "failed") {
      throw new Error(state.error || t("optimization_failed"));
    }
    const report = await jsonRequest(`/api/jobs/${state.id}/report`);
    renderReport(report, t("new_result"));
    await saveReportToCloud(report);
    await refreshSavedReports();
    renderProductionComparison();
  }

  async function refreshSavedReports(strict = false) {
    const container = byId("saved-reports");
    const select = byId("saved-report-select");
    savedProjects = new Map();
    if (supabaseClient && currentUserId) {
      const { data, error } = await supabaseClient
        .from("solarna_projects")
        .select("id,name,site_name,updated_at,report")
        .order("updated_at", { ascending: false });
      if (error) {
        cloudStorageAvailable = false;
        select.replaceChildren();
        select.disabled = true;
        byId("load-saved-report").disabled = true;
        setStorageStatus(t("project_storage_unavailable"), true);
        container.classList.remove("hidden");
        return;
      }
      cloudStorageAvailable = true;
      savedReportSource = "cloud";
      select.disabled = false;
      select.replaceChildren();
      (Array.isArray(data) ? data : []).forEach(project => {
        savedProjects.set(project.id, project);
        const option = create("option", projectOptionLabel(project));
        option.value = project.id;
        select.append(option);
      });
      if (currentProjectId && savedProjects.has(currentProjectId)) {
        select.value = currentProjectId;
      }
      const hasProjects = savedProjects.size > 0;
      container.classList.toggle("hidden", !hasProjects);
      byId("load-saved-report").disabled = !hasProjects;
      return;
    }
    try {
      const payload = await jsonRequest("/api/reports");
      const reports = Array.isArray(payload.reports) ? payload.reports : [];
      savedReportSource = "server";
      select.replaceChildren();
      reports.forEach(report => {
        const option = create("option");
        option.value = report.name;
        const generated = new Date(report.generated_at_utc);
        const date = Number.isNaN(generated.getTime())
          ? report.generated_at_utc
          : generated.toLocaleString();
        option.textContent =
          `${report.site_name} · ${formatNumber(report.tilt_deg, 1)}° / ` +
          `${formatNumber(report.azimuth_deg, 1)}° · ${date}`;
        select.append(option);
      });
      container.classList.toggle("hidden", reports.length === 0);
      byId("load-saved-report").disabled = reports.length === 0;
      setStorageStatus(t("project_saved_server"));
    } catch (error) {
      container.classList.add("hidden");
      select.replaceChildren();
      if (strict) throw error;
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    validateSystemSizing();
    if (!form.reportValidity()) return;
    currentProjectId = "";
    currentProductionRecords = [];
    renderProductionComparison();
    runButton.disabled = true;
    runButton.textContent = t("running");
    statusBox.classList.remove("failed");
    try {
      const job = await jsonRequest("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadFromForm())
      });
      await pollJob(job);
    } catch (error) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("failed");
      byId("job-message").textContent = t("analysis_failed");
      byId("job-percent").textContent = "";
      byId("job-detail").textContent = error.message;
    } finally {
      runButton.disabled = false;
      runButton.textContent = t("run_optimization");
    }
  });

  ["panel-count", "panel-power", "capacity", "inverter-ac-rating"].forEach(id => {
    byId(id).addEventListener("input", updateSystemSizing);
  });

  byId("system-size-mode").addEventListener("change", () => {
    applySizingMode();
    saveFormDraft();
  });

  byId("existing-orientation-enabled").addEventListener("change", () => {
    applyExistingOrientationMode();
    saveFormDraft();
  });

  byId("elevation-mode").addEventListener("change", () => {
    applyElevationMode();
    saveFormDraft();
  });

  byId("period-analysis").addEventListener("change", () => {
    applyPeriodAnalysis();
    saveFormDraft();
  });

  byId("analysis-profile").addEventListener("change", () => {
    applyAnalysisProfile();
    saveFormDraft();
  });

  [
    "coarse-step",
    "fine-step",
    "timing-sensitivity",
    "pvgis-benchmark",
    "historical-range"
  ].forEach(id => {
    byId(id).addEventListener("change", () => {
      byId("analysis-profile").value = "custom";
      saveFormDraft();
    });
  });

  byId("loss-preset").addEventListener("change", () => {
    applyLossPreset();
    saveFormDraft();
  });

  byId("loss-mode").addEventListener("change", () => {
    applyLossMode();
    saveFormDraft();
  });

  Object.values(engineeringLossFields).forEach(id => {
    byId(id).addEventListener("input", () => {
      updateLossSummary();
      saveFormDraft();
    });
  });

  Array.from({ length: 12 }, (_, index) => index + 1).forEach(month => {
    byId(`period-month-${month}`).addEventListener("change", () => {
      applyPeriodAnalysis();
      saveFormDraft();
    });
  });

  byId("preset").addEventListener("change", event => {
    const preset = presets[event.target.value];
    if (!preset) return;
    byId("name").value = preset[0];
    byId("latitude").value = preset[1];
    byId("longitude").value = preset[2];
    byId("elevation-mode").value = "pvgis";
    applyElevationMode();
    saveFormDraft();
  });

  byId("inverter-model").addEventListener("change", () => {
    applyInverterPreset();
    saveFormDraft();
  });

  byId("panel-model").addEventListener("change", () => {
    applyPanelPreset();
    saveFormDraft();
  });

  ["name", "latitude", "longitude"].forEach(id => {
    byId(id).addEventListener("input", () => {
      const selected = presets[byId("preset").value];
      if (!selected) return;
      if (byId("name").value !== selected[0] ||
          Number(byId("latitude").value) !== selected[1] ||
          Number(byId("longitude").value) !== selected[2]) {
        byId("preset").value = "custom";
      }
    });
  });

  byId("locate-button").addEventListener("click", () => {
    if (!navigator.geolocation) {
      byId("job-detail").textContent = t("geolocation_unsupported");
      statusBox.classList.remove("hidden");
      return;
    }
    byId("locate-button").disabled = true;
    navigator.geolocation.getCurrentPosition(
      position => {
        byId("preset").value = "custom";
        byId("name").value = t("selected_location");
        byId("latitude").value = position.coords.latitude.toFixed(6);
        byId("longitude").value = position.coords.longitude.toFixed(6);
        byId("elevation-mode").value = "pvgis";
        applyElevationMode();
        byId("locate-button").disabled = false;
        saveFormDraft();
      },
      error => {
        statusBox.classList.remove("hidden");
        byId("job-message").textContent = t("location_unavailable");
        byId("job-detail").textContent = error.message;
        byId("locate-button").disabled = false;
      },
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 300000 }
    );
  });

  byId("download-button").addEventListener("click", () => {
    if (!currentReport) return;
    downloadBlob(
      new Blob([JSON.stringify(currentReport, null, 2)], { type: "application/json" }),
      reportFilename("json")
    );
  });

  byId("csv-button").addEventListener("click", () => {
    if (!currentReport) return;
    downloadBlob(
      new Blob([reportCsv(currentReport)], { type: "text/csv;charset=utf-8" }),
      reportFilename("csv")
    );
  });

  byId("print-button").addEventListener("click", () => {
    if (currentReport) window.print();
  });

  byId("share-button").addEventListener("click", async () => {
    if (!currentReport || !navigator.share) return;
    const summary =
      `${currentReport.site.name}: ${formatNumber(currentReport.best.tilt_deg, 1)}° tilt, ` +
      `${formatNumber(currentReport.best.azimuth_deg, 1)}° azimuth, ` +
      `${formatNumber(currentReport.best.annual_ac_kwh, 1)} kWh/year modeled by Solarna.`;
    const json = JSON.stringify(currentReport, null, 2);
    const file = new File(
      [json], reportFilename("json"), { type: "application/json" });
    const shareData = { title: `Solarna · ${currentReport.site.name}`, text: summary };
    if (navigator.canShare?.({ files: [file] })) shareData.files = [file];
    try {
      await navigator.share(shareData);
    } catch (error) {
      if (error.name !== "AbortError") {
        statusBox.classList.remove("hidden");
        statusBox.classList.add("failed");
        byId("job-message").textContent = t("share_failed");
        byId("job-detail").textContent = error.message;
      }
    }
  });

  byId("load-saved-report").addEventListener("click", async () => {
    const name = byId("saved-report-select").value;
    if (!name) return;
    const button = byId("load-saved-report");
    button.disabled = true;
    try {
      let report;
      if (savedReportSource === "cloud") {
        const project = savedProjects.get(name);
        if (!project?.report) throw new Error(t("report_load_failed"));
        currentProjectId = project.id;
        currentProductionRecords = [];
        report = project.report;
      } else {
        currentProjectId = "";
        currentProductionRecords = [];
        report = await jsonRequest(`/api/reports/${encodeURIComponent(name)}`);
      }
      renderReport(report, t("saved_result"));
      if (savedReportSource === "cloud") await loadProductionRecords();
    } catch (error) {
      statusBox.classList.remove("hidden");
      statusBox.classList.add("failed");
      byId("job-message").textContent = t("report_load_failed");
      byId("job-detail").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  byId("production-import-button").addEventListener("click", () => {
    if (!currentProjectId || !cloudStorageAvailable) {
      byId("production-status").textContent =
        t("production_cloud_required");
      return;
    }
    byId("production-file").click();
  });

  byId("production-file").addEventListener("change", async event => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !currentProjectId || !currentUserId ||
        !supabaseClient || !cloudStorage) return;
    const button = byId("production-import-button");
    button.disabled = true;
    try {
      const generated = new Date(currentReport?.generated_at_utc || "");
      const defaultYear = Number.isNaN(generated.getTime())
        ? new Date().getFullYear()
        : generated.getFullYear();
      const records = cloudStorage.parseProductionCsv(
        await file.text(), { defaultYear }
      );
      const rows = records.map(record => ({
        user_id: currentUserId,
        project_id: currentProjectId,
        period_start: record.periodStart,
        period_type: record.periodType,
        actual_kwh: record.actualKwh,
        source: "csv"
      }));
      const { error } = await supabaseClient
        .from("solarna_production_records")
        .upsert(rows, {
          onConflict: "project_id,period_type,period_start"
        });
      if (error) throw error;
      await loadProductionRecords();
      renderProductionComparison(t("production_imported", {
        count: records.length
      }));
    } catch (error) {
      byId("production-status").textContent =
        `${t("production_import_failed")}: ${error.message}`;
    } finally {
      button.disabled = !currentProjectId || !cloudStorageAvailable;
    }
  });

  byId("production-clear-button").addEventListener("click", async () => {
    if (!currentProjectId || !supabaseClient ||
        !window.confirm(t("production_clear_confirm"))) return;
    const button = byId("production-clear-button");
    button.disabled = true;
    try {
      const { error } = await supabaseClient
        .from("solarna_production_records")
        .delete()
        .eq("project_id", currentProjectId);
      if (error) throw error;
      currentProductionRecords = [];
      renderProductionComparison(t("production_cleared"));
    } catch (error) {
      byId("production-status").textContent = error.message;
    } finally {
      button.disabled = false;
    }
  });

  window.addEventListener("beforeinstallprompt", event => {
    if (nativeShell) return;
    event.preventDefault();
    deferredInstall = event;
    byId("install-button").textContent = t("install_app");
    byId("install-button").classList.remove("hidden");
  });
  byId("install-button").addEventListener("click", async () => {
    if (deferredInstall) {
      deferredInstall.prompt();
      await deferredInstall.userChoice;
      deferredInstall = null;
      byId("install-button").classList.add("hidden");
      return;
    }
    if (!iosInstallAvailable) return;
    const dialog = byId("ios-install-dialog");
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      window.alert(
        `${t("install_step_1")} ${t("install_step_2")} ${t("install_step_3")}`
      );
    }
  });
  window.addEventListener("appinstalled", () => {
    deferredInstall = null;
    byId("install-button").classList.add("hidden");
  });

  function showStoredReport() {
    const stored = localStorage.getItem("solarna:last-report");
    if (!stored) return;
    try {
      renderReport(JSON.parse(stored), t("offline_result"), false);
      window.scrollTo(0, 0);
    } catch {
      localStorage.removeItem("solarna:last-report");
    }
  }

  async function connectAndLoad() {
    if (navigator.share) byId("share-button").classList.remove("hidden");
    const androidDownload = byId("android-download-link");
    androidDownload.classList.add("hidden");
    try {
      const health = await jsonRequest("/api/health", undefined, false);
      serverAuthRequired = health.authentication_required === true;
      serverAuthMode = typeof health.authentication_mode === "string"
        ? health.authentication_mode
        : serverAuthRequired ? "token" : "none";
      if (serverAuthMode === "supabase") {
        await configureSupabase(health);
      }
      if (!nativeShell && !iosInstallAvailable &&
          typeof health.android_download_url === "string") {
        androidDownload.href = health.android_download_url;
        androidDownload.classList.remove("hidden");
      }
      if (serverAuthRequired && !sessionToken) {
        redirectToLogin();
        return false;
      }
      await refreshSavedReports(true);
      if (!serverAuthRequired) {
        sessionToken = "";
        sessionStorage.removeItem("solarna:session-token");
      }
      setConnection(true, t("online"));
      byId("logout-button").classList.toggle("hidden", !serverAuthRequired);
      document.body.classList.remove("auth-pending");
      window.scrollTo(0, 0);
      return true;
    } catch (error) {
      if (serverAuthRequired) {
        redirectToLogin();
        return false;
      }
      setConnection(
        false,
        serverAuthRequired ? t("login_required") : t("offline")
      );
      document.body.classList.remove("auth-pending");
      showStoredReport();
      return false;
    }
  }

  byId("logout-button").addEventListener("click", async () => {
    try {
      if (serverAuthMode === "supabase" && supabaseClient) {
        await supabaseClient.auth.signOut({ scope: "local" });
      } else if (sessionToken) {
        await jsonRequest("/api/logout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}"
        });
      }
    } finally {
      redirectToLogin();
    }
  });

  async function initialize() {
    populateEquipmentSelects();
    restoreFormDraft();
    applyLossMode();
    applySizingMode();
    applyExistingOrientationMode();
    applyElevationMode();
    applyPeriodAnalysis();
    applyPanelPreset();
    applyInverterPreset();
    form.addEventListener("input", saveFormDraft);
    form.addEventListener("change", saveFormDraft);
    if (!nativeShell && "serviceWorker" in navigator) {
      navigator.serviceWorker.register("/service-worker.js?v=44").catch(() => {});
    }
    iosInstallAvailable = Boolean(
      installSupport &&
      installSupport.shouldOfferIosInstall(
        nativeShell,
        navigator,
        query => window.matchMedia(query)
      )
    );
    if (iosInstallAvailable) {
      byId("install-button").textContent = t("install_iphone");
      byId("install-button").classList.remove("hidden");
    }
    if (nativeShell && !apiBaseUrl) {
      redirectToLogin();
      return;
    }
    await connectAndLoad();
  }

  window.addEventListener("online", () => connectAndLoad());
  window.addEventListener("offline", () => {
    setConnection(false, t("offline"));
    document.body.classList.remove("auth-pending");
    showStoredReport();
  });
  window.addEventListener("solarna:languagechange", () => {
    populateEquipmentSelects();
    renderEquipmentCards();
    updateSystemSizing();
    updateLossSummary();
    if (currentReport) renderReport(currentReport, t("result"), false);
  });
  initialize();
})();
