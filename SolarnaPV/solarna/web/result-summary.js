(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.SOLARNA_RESULT_SUMMARY = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const TUNISIA_VALIDATION = Object.freeze({
    validatedAt: "2026-09-18",
    siteCount: 24,
    meanAbsoluteYieldDifferencePercent: 1.3705852109823404,
    maximumAbsoluteYieldDifferencePercent: 5.842582450487921,
    meanAbsoluteTiltDifferenceDeg: 0.7083333333333334,
    maximumAbsoluteTiltDifferenceDeg: 1,
    meanAbsoluteAzimuthDifferenceDeg: 1.8333333333333333,
    maximumAbsoluteAzimuthDifferenceDeg: 10
  });

  function finiteNumber(value, label) {
    const number = Number(value);
    if (!Number.isFinite(number)) {
      throw new TypeError(`${label} must be a finite number.`);
    }
    return number;
  }

  function normalizeAzimuth(value) {
    const number = finiteNumber(value, "Azimuth");
    return ((number % 360) + 360) % 360;
  }

  function minimalCircularArc(values) {
    if (!Array.isArray(values) || values.length === 0) {
      throw new RangeError("At least one azimuth is required.");
    }
    const sorted = [...new Set(values.map(normalizeAzimuth))].sort((a, b) => a - b);
    if (sorted.length === 1) {
      return {
        startDeg: sorted[0],
        endDeg: sorted[0],
        spanDeg: 0,
        crossesNorth: false
      };
    }

    let largestGap = -1;
    let largestGapIndex = 0;
    sorted.forEach((azimuth, index) => {
      const next = index === sorted.length - 1 ? sorted[0] + 360 : sorted[index + 1];
      const gap = next - azimuth;
      if (gap > largestGap) {
        largestGap = gap;
        largestGapIndex = index;
      }
    });

    const startDeg = sorted[(largestGapIndex + 1) % sorted.length];
    const endDeg = sorted[largestGapIndex];
    return {
      startDeg,
      endDeg,
      spanDeg: 360 - largestGap,
      crossesNorth: startDeg > endDeg
    };
  }

  function summarizeNearOptimal(points, fraction) {
    if (!Array.isArray(points) || points.length === 0) return null;
    const tilts = points.map((point, index) =>
      finiteNumber(point?.tilt_deg, `Tilt at index ${index}`)
    );
    const azimuths = points.map((point, index) =>
      finiteNumber(point?.azimuth_deg, `Azimuth at index ${index}`)
    );
    const nearFraction = finiteNumber(fraction, "Near-optimal fraction");
    if (nearFraction < 0 || nearFraction >= 1) {
      throw new RangeError("Near-optimal fraction must be between zero and one.");
    }
    return Object.freeze({
      thresholdPercent: nearFraction * 100,
      tiltMinDeg: Math.min(...tilts),
      tiltMaxDeg: Math.max(...tilts),
      azimuth: Object.freeze(minimalCircularArc(azimuths)),
      sampleCount: points.length
    });
  }

  function optionalFiniteNumber(value) {
    if (value === null || value === undefined || value === "") return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  }

  function estimateAccuracy(report) {
    const comparison = report?.pvgis_benchmark?.status === "available"
      ? report.pvgis_benchmark.comparison
      : null;
    const yieldDifferencePercent = comparison
      ? Math.abs(optionalFiniteNumber(
        comparison.specific_yield_delta_percent_of_pvgis
      ) ?? NaN)
      : null;
    const validYieldDifference = Number.isFinite(yieldDifferencePercent)
      ? yieldDifferencePercent
      : null;
    const agreementLabel = validYieldDifference === null
      ? "National"
      : validYieldDifference <= 3
        ? "Close"
        : validYieldDifference <= 6
          ? "Moderate"
          : "Review";
    const history = report?.historical_range?.status === "available"
      ? report.historical_range.orientations?.tmy_optimum
      : null;

    return Object.freeze({
      agreementLabel,
      siteBenchmarkAvailable: comparison !== null,
      yieldDifferencePercent: validYieldDifference,
      tiltDifferenceDeg: comparison
        ? Math.abs(optionalFiniteNumber(comparison.tilt_delta_deg) ?? NaN)
        : null,
      azimuthDifferenceDeg: comparison
        ? Math.abs(optionalFiniteNumber(comparison.azimuth_delta_deg) ?? NaN)
        : null,
      historicalRange: history
        ? Object.freeze({
          p10SpecificYieldKwhPerKwp: optionalFiniteNumber(
            history.p10_specific_yield_kwh_per_kwp
          ),
          medianSpecificYieldKwhPerKwp: optionalFiniteNumber(
            history.median_specific_yield_kwh_per_kwp
          ),
          p90SpecificYieldKwhPerKwp: optionalFiniteNumber(
            history.p90_specific_yield_kwh_per_kwp
          )
        })
        : null,
      nationalValidation: TUNISIA_VALIDATION
    });
  }

  function improvementSuggestions(report) {
    const suggestions = [];
    const request = report?.application_request || {};
    const system = report?.system || {};
    const siteName = String(report?.site?.name || "");
    const presetLocation =
      /\(governorate capital\)|illustrative location/i.test(siteName);

    if (presetLocation) {
      suggestions.push(
        "Use the exact roof GPS coordinates instead of the city-center preset."
      );
    }

    if (request.normalized_capacity === true) {
      suggestions.push(
        "Enter the actual panel count, panel power and inverter rating for installed-energy results."
      );
    }

    if (
      optionalFiniteNumber(system.other_dc_loss_fraction) !== null &&
      Number(system.other_dc_loss_fraction) <= 0
    ) {
      suggestions.push(
        "Add realistic wiring, mismatch, soiling and degradation losses."
      );
    }

    if (report?.historical_range?.status !== "available") {
      suggestions.push(
        "Use Historical analysis to measure year-to-year weather variation."
      );
    }

    if (!report?.existing_orientation) {
      suggestions.push(
        "Measure the current panel tilt and direction to quantify any retrofit gain."
      );
    } else {
      const gain = optionalFiniteNumber(
        report.existing_orientation.gain_of_best_percent
      );
      if (gain !== null && gain < 1) {
        suggestions.push(
          "The entered orientation is close to optimum; prioritize maintenance over reorientation."
        );
      } else if (gain !== null && gain >= 3) {
        suggestions.push(
          "Review reorientation cost against the modeled energy gain."
        );
      }
    }

    if (report?.pvgis_benchmark?.status !== "available") {
      suggestions.push(
        "Run the PVGIS comparison when the provider is available."
      );
    }

    suggestions.push(
      "Use module and inverter datasheet values instead of defaults."
    );
    const siteVerification =
      "Verify roof shading, structure, electrical design and first-year production on site.";
    return Object.freeze([...suggestions.slice(0, 3), siteVerification]);
  }

  return Object.freeze({
    TUNISIA_VALIDATION,
    estimateAccuracy,
    improvementSuggestions,
    minimalCircularArc,
    summarizeNearOptimal
  });
});
