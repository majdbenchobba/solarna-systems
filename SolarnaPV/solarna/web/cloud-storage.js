(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SOLARNA_CLOUD = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const PERIOD_HEADERS = new Set([
    "date",
    "month",
    "period",
    "period_start",
    "timestamp",
    "year_month"
  ]);
  const ENERGY_HEADERS = new Set([
    "actual_kwh",
    "energy_kwh",
    "production_kwh",
    "yield_kwh",
    "kwh"
  ]);

  function normalizedHeader(value) {
    return String(value || "")
      .trim()
      .toLowerCase()
      .replace(/[\s-]+/g, "_")
      .replace(/[^a-z0-9_]/g, "");
  }

  function detectDelimiter(text) {
    const firstLine = String(text || "").replace(/^\ufeff/, "").split(/\r?\n/, 1)[0];
    const candidates = [",", ";", "\t"];
    return candidates
      .map(delimiter => ({
        delimiter,
        count: firstLine.split(delimiter).length - 1
      }))
      .sort((left, right) => right.count - left.count)[0].delimiter;
  }

  function parseRows(text, delimiter = detectDelimiter(text)) {
    const source = String(text || "").replace(/^\ufeff/, "");
    const rows = [];
    let row = [];
    let cell = "";
    let quoted = false;

    for (let index = 0; index < source.length; index += 1) {
      const character = source[index];
      if (character === '"') {
        if (quoted && source[index + 1] === '"') {
          cell += '"';
          index += 1;
        } else {
          quoted = !quoted;
        }
      } else if (character === delimiter && !quoted) {
        row.push(cell);
        cell = "";
      } else if ((character === "\n" || character === "\r") && !quoted) {
        if (character === "\r" && source[index + 1] === "\n") index += 1;
        row.push(cell);
        if (row.some(value => String(value).trim() !== "")) rows.push(row);
        row = [];
        cell = "";
      } else {
        cell += character;
      }
    }
    if (quoted) throw new Error("CSV contains an unclosed quoted value.");
    row.push(cell);
    if (row.some(value => String(value).trim() !== "")) rows.push(row);
    return rows;
  }

  function parseEnergy(value) {
    const text = String(value ?? "").trim().replace(/\s/g, "");
    if (!text) throw new Error("Actual energy is missing.");
    const normalized = /^-?\d+,\d+$/.test(text)
      ? text.replace(",", ".")
      : text.replace(/,/g, "");
    const number = Number(normalized);
    if (!Number.isFinite(number) || number < 0) {
      throw new Error(`Invalid actual energy: ${value}`);
    }
    return number;
  }

  function isoDate(year, month, day = 1) {
    const date = new Date(Date.UTC(year, month - 1, day));
    if (
      date.getUTCFullYear() !== year ||
      date.getUTCMonth() !== month - 1 ||
      date.getUTCDate() !== day
    ) {
      throw new Error("Invalid production date.");
    }
    return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
  }

  function parsePeriod(value, defaultYear = new Date().getUTCFullYear()) {
    const text = String(value || "").trim();
    let match = text.match(/^(\d{4})-(\d{1,2})$/);
    if (match) {
      return {
        periodStart: isoDate(Number(match[1]), Number(match[2])),
        periodType: "monthly"
      };
    }
    match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?$/);
    if (match) {
      return {
        periodStart: isoDate(
          Number(match[1]), Number(match[2]), Number(match[3])
        ),
        periodType: "daily"
      };
    }
    match = text.match(/^(\d{1,2})[/.](\d{1,2})[/.](\d{4})$/);
    if (match) {
      return {
        periodStart: isoDate(
          Number(match[3]), Number(match[2]), Number(match[1])
        ),
        periodType: "daily"
      };
    }
    match = text.match(/^(\d{1,2})$/);
    if (match) {
      return {
        periodStart: isoDate(Number(defaultYear), Number(match[1])),
        periodType: "monthly"
      };
    }
    const monthNames = [
      "jan", "feb", "mar", "apr", "may", "jun",
      "jul", "aug", "sep", "oct", "nov", "dec"
    ];
    const month = monthNames.findIndex(name =>
      text.toLowerCase().startsWith(name)
    );
    if (month >= 0) {
      const yearMatch = text.match(/\b(20\d{2}|19\d{2})\b/);
      return {
        periodStart: isoDate(
          yearMatch ? Number(yearMatch[1]) : Number(defaultYear),
          month + 1
        ),
        periodType: "monthly"
      };
    }
    throw new Error(`Invalid production date: ${value}`);
  }

  function parseProductionCsv(text, options = {}) {
    const rows = parseRows(text);
    if (rows.length < 2) throw new Error("CSV must include a header and data.");
    const headers = rows[0].map(normalizedHeader);
    const periodIndex = headers.findIndex(header => PERIOD_HEADERS.has(header));
    const energyIndex = headers.findIndex(header => ENERGY_HEADERS.has(header));
    if (periodIndex < 0 || energyIndex < 0) {
      throw new Error("CSV columns must include date and actual_kwh.");
    }
    const merged = new Map();
    rows.slice(1).forEach((row, rowIndex) => {
      try {
        const period = parsePeriod(row[periodIndex], options.defaultYear);
        const key = `${period.periodType}:${period.periodStart}`;
        const actualKwh = parseEnergy(row[energyIndex]);
        const previous = merged.get(key);
        merged.set(key, {
          ...period,
          actualKwh: actualKwh + (previous?.actualKwh || 0)
        });
      } catch (error) {
        throw new Error(`Row ${rowIndex + 2}: ${error.message}`);
      }
    });
    return [...merged.values()].sort((left, right) =>
      left.periodStart.localeCompare(right.periodStart)
    );
  }

  function monthlyActual(records) {
    const monthly = new Map();
    const daily = new Map();
    (records || []).forEach(record => {
      const periodStart = String(
        record.periodStart || record.period_start || ""
      );
      const periodType = record.periodType || record.period_type;
      const actualKwh = Number(
        record.actualKwh ?? record.actual_kwh
      );
      if (!/^\d{4}-\d{2}-\d{2}$/.test(periodStart) ||
          !Number.isFinite(actualKwh) || actualKwh < 0) return;
      const key = periodStart.slice(0, 7);
      if (periodType === "monthly") {
        const previous = monthly.get(key);
        monthly.set(key, {
          actualKwh: actualKwh + (previous?.actualKwh || 0),
          dayCount: null,
          periodType: "monthly"
        });
      } else if (periodType === "daily") {
        const previous = daily.get(key) || {
          actualKwh: 0,
          dates: new Set()
        };
        previous.actualKwh += actualKwh;
        previous.dates.add(periodStart);
        daily.set(key, previous);
      }
    });
    daily.forEach((value, key) => {
      if (!monthly.has(key)) {
        monthly.set(key, {
          actualKwh: value.actualKwh,
          dayCount: value.dates.size,
          periodType: "daily"
        });
      }
    });
    return monthly;
  }

  function compareProduction(report, records) {
    const modeled = report?.best?.monthly_ac_kwh;
    if (!modeled || typeof modeled !== "object") {
      throw new Error("The report does not include monthly energy.");
    }
    const actual = monthlyActual(records);
    const rows = [...actual.entries()].sort(([left], [right]) =>
      left.localeCompare(right)
    ).map(([period, actual]) => {
      const month = Number(period.slice(5, 7));
      const annualProfileKwh = Number(
        modeled[String(month)] ?? modeled[month]
      );
      if (!Number.isFinite(annualProfileKwh)) {
        throw new Error(`Modeled energy is missing for month ${month}.`);
      }
      const year = Number(period.slice(0, 4));
      const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
      const estimatedKwh = actual.periodType === "daily"
        ? annualProfileKwh * actual.dayCount / daysInMonth
        : annualProfileKwh;
      const actualKwh = actual.actualKwh;
      const varianceKwh = actualKwh - estimatedKwh;
      return {
        period,
        month,
        dayCount: actual.dayCount,
        periodType: actual.periodType,
        actualKwh,
        estimatedKwh,
        varianceKwh,
        variancePercent: estimatedKwh === 0
          ? null
          : varianceKwh / estimatedKwh * 100
      };
    });
    const actualKwh = rows.reduce((sum, row) => sum + row.actualKwh, 0);
    const estimatedKwh = rows.reduce((sum, row) => sum + row.estimatedKwh, 0);
    const varianceKwh = actualKwh - estimatedKwh;
    return {
      rows,
      monthCount: rows.length,
      actualKwh,
      estimatedKwh,
      varianceKwh,
      variancePercent: estimatedKwh === 0
        ? null
        : varianceKwh / estimatedKwh * 100
    };
  }

  function projectFromReport(report, userId) {
    if (!report?.site || !report?.system || !report?.best) {
      throw new Error("Invalid report.");
    }
    return {
      user_id: userId,
      name: String(report.site.name || "Solarna project").slice(0, 120),
      site_name: String(report.site.name || "Solarna project").slice(0, 120),
      latitude: Number(report.site.latitude),
      longitude: Number(report.site.longitude),
      system: report.system,
      report
    };
  }

  return Object.freeze({
    compareProduction,
    detectDelimiter,
    monthlyActual,
    parsePeriod,
    parseProductionCsv,
    parseRows,
    projectFromReport
  });
});
