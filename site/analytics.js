// Google Analytics 4 流量監測。
// 只要改這一行：填入 GA4 的評估 ID（G- 開頭）；留空就完全不載入 Google 的程式。
const GA_MEASUREMENT_ID = "";

(function () {
  if (!/^G-[A-Z0-9]+$/.test(GA_MEASUREMENT_ID)) return;
  const s = document.createElement("script");
  s.async = true;
  s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_MEASUREMENT_ID;
  document.head.appendChild(s);
  window.dataLayer = window.dataLayer || [];
  window.gtag = function () { window.dataLayer.push(arguments); };
  window.gtag("js", new Date());
  window.gtag("config", GA_MEASUREMENT_ID);
})();
