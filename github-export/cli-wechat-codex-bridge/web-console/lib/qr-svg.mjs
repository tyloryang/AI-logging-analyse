import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const QRCode = require("qrcode-terminal/vendor/QRCode");
const QRErrorCorrectLevel = require("qrcode-terminal/vendor/QRCode/QRErrorCorrectLevel");

function escapeAttribute(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("\"", "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

export function buildQrSvg(content, options = {}) {
  const {
    margin = 4,
    errorLevel = "M",
    darkColor = "#000000",
    lightColor = "#ffffff",
  } = options;

  const qr = new QRCode(-1, QRErrorCorrectLevel[errorLevel] ?? QRErrorCorrectLevel.M);
  qr.addData(content);
  qr.make();

  const moduleCount = qr.getModuleCount();
  const viewBoxSize = moduleCount + margin * 2;
  const path = [];

  for (let row = 0; row < moduleCount; row += 1) {
    for (let col = 0; col < moduleCount; col += 1) {
      if (!qr.isDark(row, col)) {
        continue;
      }
      const x = col + margin;
      const y = row + margin;
      path.push(`M${x} ${y}h1v1H${x}z`);
    }
  }

  return [
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${viewBoxSize} ${viewBoxSize}" role="img" aria-label="${escapeAttribute(content)}" shape-rendering="crispEdges">`,
    `<rect width="${viewBoxSize}" height="${viewBoxSize}" fill="${escapeAttribute(lightColor)}"/>`,
    `<path d="${path.join("")}" fill="${escapeAttribute(darkColor)}"/>`,
    "</svg>",
  ].join("");
}

export function buildQrSvgDataUrl(content, options = {}) {
  const svg = buildQrSvg(content, options);
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}
