import assert from "node:assert/strict";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const cloud = require(path.resolve(
  scriptDirectory, "..", "..", "solarna", "web", "cloud-storage.js"
));

const monthly = cloud.parseProductionCsv(
  "date,actual_kwh\n2026-01,520.4\n2026-02,610\n"
);
assert.deepEqual(monthly, [
  {
    periodStart: "2026-01-01",
    periodType: "monthly",
    actualKwh: 520.4
  },
  {
    periodStart: "2026-02-01",
    periodType: "monthly",
    actualKwh: 610
  }
]);

const daily = cloud.parseProductionCsv(
  "date;actual_kwh\n01/03/2026;12,5\n02/03/2026;13,5\n"
);
assert.equal(daily.length, 2);
assert.equal(daily[0].actualKwh, 12.5);

const report = {
  site: { name: "Sfax", latitude: 34.74, longitude: 10.76 },
  system: { dc_capacity_kw: 4.4 },
  best: {
    tilt_deg: 30,
    monthly_ac_kwh: { 1: 500, 2: 600, 3: 700 }
  }
};
const comparison = cloud.compareProduction(report, [
  ...monthly,
  ...daily,
  {
    periodStart: "2026-03-01",
    periodType: "monthly",
    actualKwh: 750
  }
]);
assert.equal(comparison.monthCount, 3);
assert.equal(comparison.actualKwh, 1880.4);
assert.equal(comparison.estimatedKwh, 1800);
assert.ok(Math.abs(comparison.variancePercent - 4.4666666667) < 1e-8);
assert.equal(comparison.rows[2].actualKwh, 750);

const partialMonth = cloud.compareProduction({
  ...report,
  best: {
    ...report.best,
    monthly_ac_kwh: { ...report.best.monthly_ac_kwh, 4: 600 }
  }
}, [
  {
    periodStart: "2026-04-01",
    periodType: "daily",
    actualKwh: 20
  },
  {
    periodStart: "2026-04-02",
    periodType: "daily",
    actualKwh: 22
  }
]);
assert.equal(partialMonth.rows[0].dayCount, 2);
assert.equal(partialMonth.estimatedKwh, 40);
assert.equal(partialMonth.actualKwh, 42);

const project = cloud.projectFromReport(report, "user-1");
assert.equal(project.user_id, "user-1");
assert.equal(project.name, "Sfax");
assert.equal(project.report, report);

assert.throws(
  () => cloud.parseProductionCsv("month,value\n2026-01,10\n"),
  /date and actual_kwh/
);
assert.throws(
  () => cloud.parseProductionCsv("date,actual_kwh\n2026-01,-2\n"),
  /Row 2/
);

console.log("Cloud project and production import helpers passed.");
