(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SOLARNA_SYSTEM = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function freezeEntries(entries) {
    return Object.freeze(Object.fromEntries(
      entries.map(([key, value]) => [key, Object.freeze(value)])
    ));
  }

  function panelFamily(options) {
    return options.powers.map(power => [
      options.keyForPower(power),
      {
        manufacturer: options.manufacturer,
        series: options.series,
        model: options.modelForPower(power),
        powerW: power,
        gammaPercentPerC: options.gammaPercentPerC,
        construction: options.construction,
        technology: options.technology,
        sourceUrl: options.sourceUrl
      }
    ]);
  }

  function inverterFamily(options) {
    return options.models.map(item => [
      `${options.keyPrefix}-${item.key}`,
      {
        manufacturer: options.manufacturer,
        model: item.model,
        acRatingKw: item.acRatingKw,
        efficiencyPercent: item.efficiencyPercent,
        efficiencyType: "european",
        maxEfficiencyPercent: item.maxEfficiencyPercent,
        ...(item.recommendedMaxPvInputKw
          ? { recommendedMaxPvInputKw: item.recommendedMaxPvInputKw }
          : {}),
        sourceUrl: item.sourceUrl || options.sourceUrl
      }
    ]);
  }

  const PANEL_PRESETS = freezeEntries([
    ...panelFamily({
      manufacturer: "JinkoSolar",
      series: "Tiger Pro 72HC",
      powers: [530, 540, 550],
      keyForPower: power => `jinko-jkm${power}m-72hl4-v`,
      modelForPower: power => `JKM${power}M-72HL4-V`,
      gammaPercentPerC: -0.35,
      construction: "glass_backsheet",
      technology: "Monocrystalline half-cell",
      sourceUrl: "https://www.jinkosolar.com/uploads/5ff587a0/JKM530-550M-72HL4-(V)-F1-EN.pdf"
    }),
    ...panelFamily({
      manufacturer: "LONGi",
      series: "Hi-MO 7",
      powers: [565, 575, 585],
      keyForPower: power => `longi-lr5-72hth-${power}m`,
      modelForPower: power => `LR5-72HTH-${power}M`,
      gammaPercentPerC: -0.28,
      construction: "glass_backsheet",
      technology: "HPDC monocrystalline",
      sourceUrl: "https://static.longi.com/L_Gi_LE_PM_T_PMD_059_F138_LR_5_72_HTH_565_585_M_V2_30_30_and_15_Frame_Explorer_V19_fb7474efd7.pdf"
    }),
    ...panelFamily({
      manufacturer: "JA Solar",
      series: "DeepBlue 3.0",
      powers: [540, 545, 550, 555, 560, 565],
      keyForPower: power => `ja-jam72s30-${power}-mr`,
      modelForPower: power => `JAM72S30-${power}/MR`,
      gammaPercentPerC: -0.35,
      construction: "glass_backsheet",
      technology: "P-type monocrystalline PERC",
      sourceUrl: "https://www.jasolar.eu/es/productos/jam72s30-mr"
    }),
    ...panelFamily({
      manufacturer: "Trina Solar",
      series: "Vertex DEG19C.20",
      powers: [530, 535, 540, 545, 550, 555],
      keyForPower: power => `trina-deg19c20-${power}`,
      modelForPower: power => `TSM-DEG19C.20 ${power}W`,
      gammaPercentPerC: -0.34,
      construction: "glass_glass",
      technology: "Bifacial monocrystalline PERC",
      sourceUrl: "https://www.trinasolar.com/au/Vertex/"
    }),
    ...panelFamily({
      manufacturer: "Canadian Solar",
      series: "HiKu6",
      powers: [530, 535, 540, 545, 550, 555],
      keyForPower: power => `canadian-cs6w-${power}ms`,
      modelForPower: power => `CS6W-${power}MS`,
      gammaPercentPerC: -0.34,
      construction: "glass_backsheet",
      technology: "Monocrystalline PERC",
      sourceUrl: "https://www.canadiansolar.com/downloads/"
    }),
    ...panelFamily({
      manufacturer: "Risen Energy",
      series: "Titan RSM110-8",
      powers: [535, 540, 545, 550, 555, 560],
      keyForPower: power => `risen-rsm110-8-${power}m`,
      modelForPower: power => `RSM110-8-${power}M`,
      gammaPercentPerC: -0.34,
      construction: "glass_backsheet",
      technology: "Monocrystalline PERC",
      sourceUrl: "https://en.risenenergy.com/"
    })
  ]);

  const INVERTER_PRESETS = freezeEntries([
    ["sungrow-sg4rs", {
      manufacturer: "Sungrow",
      model: "SG4.0RS",
      acRatingKw: 4,
      efficiencyPercent: 97.2,
      efficiencyType: "european",
      maxEfficiencyPercent: 97.9,
      recommendedMaxPvInputKw: 7.2,
      sourceUrl: "https://info-support.sungrowpower.com/application/pdf/2024/05/31/DS_20240528_SG3.6_4.0RS_JO_Datasheet_V1_EN.pdf"
    }],
    ...inverterFamily({
      keyPrefix: "sungrow",
      manufacturer: "Sungrow",
      sourceUrl: "https://info-support.sungrowpower.com/cms/af994f1d-bb0d-408a-b310-6ad732402c99/GUID-8BA11DF2-9222-4FC2-8517-2F0F52A5A3D8_1_en-US_PDF%20(%E4%BA%A7%E5%93%81%E4%BF%A1%E6%81%AF%E8%AE%BE%E8%AE%A1%E9%83%A8_%E5%9F%BA%E7%A1%80%E7%89%88)_1784543697765_compressed.pdf",
      models: [
        { key: "sg3rs-l2", model: "SG3.0RS-L2", acRatingKw: 3, efficiencyPercent: 97.4, maxEfficiencyPercent: 98.2, recommendedMaxPvInputKw: 4.5 },
        { key: "sg4rs-l2", model: "SG4.0RS-L2", acRatingKw: 4, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.3, recommendedMaxPvInputKw: 6 },
        { key: "sg5rs-l2", model: "SG5.0RS-L2", acRatingKw: 5, efficiencyPercent: 97.6, maxEfficiencyPercent: 98.3, recommendedMaxPvInputKw: 7.5 },
        { key: "sg6rs-l2", model: "SG6.0RS-L2", acRatingKw: 6, efficiencyPercent: 97.8, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 9 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "huawei",
      manufacturer: "Huawei",
      sourceUrl: "https://solar.huawei.com/admin/asset/v1/pro/view/46c7b16557cc429182c47921e8e4ed5c.pdf",
      models: [
        { key: "sun2000-2ktl-l1", model: "SUN2000-2KTL-L1", acRatingKw: 2, efficiencyPercent: 96.7, maxEfficiencyPercent: 98.2, recommendedMaxPvInputKw: 3 },
        { key: "sun2000-3ktl-l1", model: "SUN2000-3KTL-L1", acRatingKw: 3, efficiencyPercent: 97.3, maxEfficiencyPercent: 98.3, recommendedMaxPvInputKw: 4.5 },
        { key: "sun2000-3-68ktl-l1", model: "SUN2000-3.68KTL-L1", acRatingKw: 3.68, efficiencyPercent: 97.3, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 5.52 },
        { key: "sun2000-4ktl-l1", model: "SUN2000-4KTL-L1", acRatingKw: 4, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 6 },
        { key: "sun2000-4-6ktl-l1", model: "SUN2000-4.6KTL-L1", acRatingKw: 4.6, efficiencyPercent: 97.7, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 6.9 },
        { key: "sun2000-5ktl-l1", model: "SUN2000-5KTL-L1", acRatingKw: 5, efficiencyPercent: 97.8, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 7.5 },
        { key: "sun2000-6ktl-l1", model: "SUN2000-6KTL-L1", acRatingKw: 6, efficiencyPercent: 97.8, maxEfficiencyPercent: 98.4, recommendedMaxPvInputKw: 9 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "goodwe",
      manufacturer: "GoodWe",
      sourceUrl: "https://en.goodwe.com/Public/Uploads/uploadfile/files/20250822/GW_DNSG43-6kW_India_EN_20250814.pdf",
      models: [
        { key: "gw3k-dns-g40", model: "GW3000-DNS-G40", acRatingKw: 3, efficiencyPercent: 97.2, maxEfficiencyPercent: 98.1 },
        { key: "gw3-6k-dns-g40", model: "GW3600-DNS-G40", acRatingKw: 3.6, efficiencyPercent: 97.2, maxEfficiencyPercent: 98.1 },
        { key: "gw4-2k-dns-g40", model: "GW4.2K-DNS-G40", acRatingKw: 4.2, efficiencyPercent: 97.3, maxEfficiencyPercent: 98.1 },
        { key: "gw5k-dns-g40", model: "GW5000-DNS-G40", acRatingKw: 5, efficiencyPercent: 97.4, maxEfficiencyPercent: 98.1 },
        { key: "gw6k-dns-g40", model: "GW6000-DNS-G40", acRatingKw: 6, efficiencyPercent: 97.4, maxEfficiencyPercent: 98.1 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "growatt",
      manufacturer: "Growatt",
      sourceUrl: "https://africa.growatt.com/products/min-2500-6000tl-x-x2(pro)",
      models: [
        { key: "min-2500tl-x", model: "MIN 2500TL-X", acRatingKw: 2.5, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-3000tl-x", model: "MIN 3000TL-X", acRatingKw: 3, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-3600tl-x", model: "MIN 3600TL-X", acRatingKw: 3.6, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-4200tl-x", model: "MIN 4200TL-X", acRatingKw: 4.2, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-4600tl-x", model: "MIN 4600TL-X", acRatingKw: 4.6, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-5000tl-x", model: "MIN 5000TL-X", acRatingKw: 5, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 },
        { key: "min-6000tl-x", model: "MIN 6000TL-X", acRatingKw: 6, efficiencyPercent: 97.5, maxEfficiencyPercent: 98.4 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "solis",
      manufacturer: "Solis",
      sourceUrl: "https://www.solisinverters.com/global/solarinverter2/2500_6000w_s6_global.html",
      models: [
        { key: "s6-gr1p2-5k-s", model: "S6-GR1P2.5K-S", acRatingKw: 2.5, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 4.5 },
        { key: "s6-gr1p3k-s", model: "S6-GR1P3K-S", acRatingKw: 3, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 5.4 },
        { key: "s6-gr1p3-6k-s", model: "S6-GR1P3.6K-S", acRatingKw: 3.6, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 6.5 },
        { key: "s6-gr1p4k-s", model: "S6-GR1P4K-S", acRatingKw: 4, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 7.2 },
        { key: "s6-gr1p4-6k-s", model: "S6-GR1P4.6K-S", acRatingKw: 4.6, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 8.3 },
        { key: "s6-gr1p5k-s", model: "S6-GR1P5K-S", acRatingKw: 5, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 9 },
        { key: "s6-gr1p6k-s", model: "S6-GR1P6K-S", acRatingKw: 6, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 10.8 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "deye",
      manufacturer: "Deye",
      sourceUrl: "https://www.deyeinverter.com/",
      models: [
        { key: "sun-3k-g04p1-eu-am1", model: "SUN-3K-G04P1-EU-AM1", acRatingKw: 3, efficiencyPercent: 97.3, maxEfficiencyPercent: 97.5, recommendedMaxPvInputKw: 3.9 },
        { key: "sun-3-3k-g04p1-eu-am1", model: "SUN-3.3K-G04P1-EU-AM1", acRatingKw: 3.3, efficiencyPercent: 97.3, maxEfficiencyPercent: 97.5, recommendedMaxPvInputKw: 4.3 },
        { key: "sun-3-6k-g04p1-eu-am1", model: "SUN-3.6K-G04P1-EU-AM1", acRatingKw: 3.6, efficiencyPercent: 97.3, maxEfficiencyPercent: 97.5, recommendedMaxPvInputKw: 4.7 },
        { key: "sun-4k-g04p1-eu-am1", model: "SUN-4K-G04P1-EU-AM1", acRatingKw: 4, efficiencyPercent: 97.3, maxEfficiencyPercent: 97.5, recommendedMaxPvInputKw: 5.2 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "sma",
      manufacturer: "SMA",
      sourceUrl: "https://manuals.sma.de/SBxx-1AV-41/en-US/index.html",
      models: [
        { key: "sunny-boy-3", model: "Sunny Boy 3.0", acRatingKw: 3, efficiencyPercent: 96.5, maxEfficiencyPercent: 97, recommendedMaxPvInputKw: 5.5 },
        { key: "sunny-boy-4", model: "Sunny Boy 4.0", acRatingKw: 4, efficiencyPercent: 96.5, maxEfficiencyPercent: 97, recommendedMaxPvInputKw: 7.5 },
        { key: "sunny-boy-5", model: "Sunny Boy 5.0", acRatingKw: 5, efficiencyPercent: 96.5, maxEfficiencyPercent: 97, recommendedMaxPvInputKw: 9 },
        { key: "sunny-boy-6", model: "Sunny Boy 6.0", acRatingKw: 6, efficiencyPercent: 96.5, maxEfficiencyPercent: 97, recommendedMaxPvInputKw: 9 }
      ]
    }),
    ...inverterFamily({
      keyPrefix: "fronius",
      manufacturer: "Fronius",
      sourceUrl: "https://www.fronius.com/en/help-center/solar-energy/products/solar-inverters/gen24/primo-gen24-plus/fronius-primo-gen24-3-0-plus",
      models: [
        { key: "primo-gen24-3-plus", model: "Primo GEN24 3.0 Plus", acRatingKw: 3, efficiencyPercent: 96.7, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 3.11 },
        { key: "primo-gen24-3-6-plus", model: "Primo GEN24 3.6 Plus", acRatingKw: 3.6, efficiencyPercent: 97, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 3.81 },
        { key: "primo-gen24-4-plus", model: "Primo GEN24 4.0 Plus", acRatingKw: 4, efficiencyPercent: 97.1, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 4.14 },
        { key: "primo-gen24-4-6-plus", model: "Primo GEN24 4.6 Plus", acRatingKw: 4.6, efficiencyPercent: 97.2, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 4.75 },
        { key: "primo-gen24-5-plus", model: "Primo GEN24 5.0 Plus", acRatingKw: 5, efficiencyPercent: 97.3, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 5.17 },
        { key: "primo-gen24-6-plus", model: "Primo GEN24 6.0 Plus", acRatingKw: 6, efficiencyPercent: 97.4, maxEfficiencyPercent: 97.7, recommendedMaxPvInputKw: 6.2 }
      ]
    })
  ]);
  const NORMALIZED_CAPACITY_KW = 1;
  const NORMALIZED_DC_AC_RATIO = 1.2;

  function positiveNumber(value, label) {
    const number = Number(value);
    if (!Number.isFinite(number) || number <= 0) {
      throw new RangeError(`${label} must be greater than zero.`);
    }
    return number;
  }

  function panelCapacityKw(panelCount, panelPowerW) {
    const count = positiveNumber(panelCount, "Panel count");
    const power = positiveNumber(panelPowerW, "Panel power");
    if (!Number.isInteger(count)) {
      throw new RangeError("Panel count must be a whole number.");
    }
    return count * power / 1000;
  }

  function systemCapacityKw(mode, panelCount, panelPowerW, capacityKw) {
    if (mode === "panels") {
      return panelCapacityKw(panelCount, panelPowerW);
    }
    if (mode === "capacity") {
      return positiveNumber(capacityKw, "Total DC capacity");
    }
    if (mode === "normalized") {
      return NORMALIZED_CAPACITY_KW;
    }
    throw new RangeError("Unknown system size input.");
  }

  function dcAcRatio(capacityKw, acRatingKw) {
    return positiveNumber(capacityKw, "Panel capacity") /
      positiveNumber(acRatingKw, "Inverter rating");
  }

  return Object.freeze({
    PANEL_PRESETS,
    INVERTER_PRESETS,
    NORMALIZED_CAPACITY_KW,
    NORMALIZED_DC_AC_RATIO,
    panelCapacityKw,
    systemCapacityKw,
    dcAcRatio
  });
});
