import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const summary = require("../../solarna/web/result-summary.js");

assert.deepEqual(
  summary.minimalCircularArc([170, 180, 190]),
  { startDeg: 170, endDeg: 190, spanDeg: 20, crossesNorth: false }
);
assert.deepEqual(
  summary.minimalCircularArc([350, 0, 10]),
  { startDeg: 350, endDeg: 10, spanDeg: 20, crossesNorth: true }
);
assert.deepEqual(
  summary.minimalCircularArc([181]),
  { startDeg: 181, endDeg: 181, spanDeg: 0, crossesNorth: false }
);

const practical = summary.summarizeNearOptimal([
  { tilt_deg: 23, azimuth_deg: 170 },
  { tilt_deg: 32, azimuth_deg: 181 },
  { tilt_deg: 40, azimuth_deg: 190 }
], 0.01);
assert.equal(practical.thresholdPercent, 1);
assert.equal(practical.tiltMinDeg, 23);
assert.equal(practical.tiltMaxDeg, 40);
assert.equal(practical.sampleCount, 3);
assert.equal(summary.summarizeNearOptimal([], 0.01), null);
assert.throws(() => summary.minimalCircularArc([]), RangeError);
assert.throws(
  () => summary.summarizeNearOptimal([{ tilt_deg: 20, azimuth_deg: 180 }], 1),
  RangeError
);

const accuracy = summary.estimateAccuracy({
  site: { name: "Sfax (governorate capital)" },
  system: { other_dc_loss_fraction: 0 },
  application_request: { normalized_capacity: true },
  pvgis_benchmark: {
    status: "available",
    comparison: {
      tilt_delta_deg: -1,
      azimuth_delta_deg: 1,
      specific_yield_delta_percent_of_pvgis: -1.5723
    }
  },
  historical_range: {
    status: "available",
    orientations: {
      tmy_optimum: {
        p10_specific_yield_kwh_per_kwp: 1800,
        median_specific_yield_kwh_per_kwp: 1900,
        p90_specific_yield_kwh_per_kwp: 2000
      }
    }
  }
});
assert.equal(accuracy.agreementLabel, "Close");
assert.equal(accuracy.yieldDifferencePercent, 1.5723);
assert.equal(accuracy.tiltDifferenceDeg, 1);
assert.equal(accuracy.azimuthDifferenceDeg, 1);
assert.equal(accuracy.historicalRange.medianSpecificYieldKwhPerKwp, 1900);
assert.equal(accuracy.nationalValidation.siteCount, 24);
assert.equal(
  Number(accuracy.nationalValidation.meanAbsoluteYieldDifferencePercent.toFixed(2)),
  1.37
);

const suggestions = summary.improvementSuggestions({
  site: { name: "Sfax (governorate capital)" },
  system: { other_dc_loss_fraction: 0 },
  application_request: { normalized_capacity: true },
  pvgis_benchmark: { status: "available" },
  historical_range: { status: "available" }
});
assert.equal(suggestions.length, 4);
assert.match(suggestions[0], /exact roof GPS/);
assert.match(suggestions[1], /actual panel count/);
assert.match(suggestions[3], /roof shading/);

console.log("Result summaries and accuracy estimates passed.");
