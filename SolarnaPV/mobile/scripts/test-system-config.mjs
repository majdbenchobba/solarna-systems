import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const system = require("../../solarna/web/system-config.js");

assert.equal(system.panelCapacityKw(10, 450), 4.5);
assert.equal(system.systemCapacityKw("panels", 10, 450, ""), 4.5);
assert.equal(system.systemCapacityKw("capacity", "", "", 4.5), 4.5);
assert.equal(system.systemCapacityKw("normalized", "", "", ""), 1);
assert.equal(system.NORMALIZED_CAPACITY_KW, 1);
assert.equal(system.NORMALIZED_DC_AC_RATIO, 1.2);
assert.equal(system.dcAcRatio(4.5, 4), 1.125);
const jinko550 = system.PANEL_PRESETS["jinko-jkm550m-72hl4-v"];
assert.equal(jinko550.manufacturer, "JinkoSolar");
assert.equal(jinko550.model, "JKM550M-72HL4-V");
assert.equal(jinko550.powerW, 550);
assert.equal(jinko550.gammaPercentPerC, -0.35);
assert.equal(jinko550.construction, "glass_backsheet");
const longi585 = system.PANEL_PRESETS["longi-lr5-72hth-585m"];
assert.equal(longi585.manufacturer, "LONGi");
assert.equal(longi585.powerW, 585);
assert.equal(longi585.gammaPercentPerC, -0.28);
const ja565 = system.PANEL_PRESETS["ja-jam72s30-565-mr"];
assert.equal(ja565.manufacturer, "JA Solar");
assert.equal(ja565.powerW, 565);
const trina550 = system.PANEL_PRESETS["trina-deg19c20-550"];
assert.equal(trina550.manufacturer, "Trina Solar");
assert.equal(trina550.construction, "glass_glass");
const canadian555 = system.PANEL_PRESETS["canadian-cs6w-555ms"];
assert.equal(canadian555.model, "CS6W-555MS");
const risen560 = system.PANEL_PRESETS["risen-rsm110-8-560m"];
assert.equal(risen560.powerW, 560);
assert.equal(Object.keys(system.PANEL_PRESETS).length, 30);
const sungrowSg4rs = system.INVERTER_PRESETS["sungrow-sg4rs"];
assert.equal(sungrowSg4rs.manufacturer, "Sungrow");
assert.equal(sungrowSg4rs.model, "SG4.0RS");
assert.equal(sungrowSg4rs.acRatingKw, 4);
assert.equal(sungrowSg4rs.efficiencyPercent, 97.2);
assert.equal(sungrowSg4rs.efficiencyType, "european");
assert.equal(sungrowSg4rs.maxEfficiencyPercent, 97.9);
assert.equal(sungrowSg4rs.recommendedMaxPvInputKw, 7.2);
const huawei4 = system.INVERTER_PRESETS["huawei-sun2000-4ktl-l1"];
assert.equal(huawei4.acRatingKw, 4);
assert.equal(huawei4.efficiencyPercent, 97.5);
assert.equal(huawei4.recommendedMaxPvInputKw, 6);
const goodwe42 = system.INVERTER_PRESETS["goodwe-gw4-2k-dns-g40"];
assert.equal(goodwe42.acRatingKw, 4.2);
assert.equal(goodwe42.efficiencyPercent, 97.3);
assert.equal(goodwe42.maxEfficiencyPercent, 98.1);
assert.equal(
  system.INVERTER_PRESETS["sungrow-sg6rs-l2"].recommendedMaxPvInputKw,
  9
);
assert.equal(
  system.INVERTER_PRESETS["growatt-min-4200tl-x"].acRatingKw,
  4.2
);
assert.equal(
  system.INVERTER_PRESETS["solis-s6-gr1p6k-s"].recommendedMaxPvInputKw,
  10.8
);
assert.equal(
  system.INVERTER_PRESETS["deye-sun-4k-g04p1-eu-am1"].efficiencyPercent,
  97.3
);
assert.equal(
  system.INVERTER_PRESETS["sma-sunny-boy-5"].model,
  "Sunny Boy 5.0"
);
assert.equal(
  system.INVERTER_PRESETS["fronius-primo-gen24-6-plus"].acRatingKw,
  6
);
assert.equal(Object.keys(system.INVERTER_PRESETS).length, 45);
assert.throws(() => system.panelCapacityKw(2.5, 450), RangeError);
assert.throws(() => system.panelCapacityKw(10, 0), RangeError);
assert.throws(() => system.systemCapacityKw("capacity", "", "", 0), RangeError);
assert.throws(() => system.systemCapacityKw("unknown", 10, 450, 4.5), RangeError);
assert.throws(() => system.dcAcRatio(4.5, 0), RangeError);

console.log("PV system sizing calculations passed.");
