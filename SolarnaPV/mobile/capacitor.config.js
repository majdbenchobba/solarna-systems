const developmentHttp = process.env.SOLARNA_MOBILE_DEV_HTTP === "1";

module.exports = {
  appId: "tn.solarna.optimizer",
  appName: "Solarna PV",
  webDir: "www",
  backgroundColor: "#073b41",
  server: {
    hostname: "localhost",
    androidScheme: developmentHttp ? "http" : "https",
    iosScheme: "capacitor",
    cleartext: developmentHttp
  },
  android: {
    allowMixedContent: developmentHttp
  },
  plugins: {
    SystemBars: {
      insetsHandling: "native",
      initialViewportFitValueHint: "cover"
    }
  }
};
