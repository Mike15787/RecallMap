const path = require("path");
const { getDefaultConfig } = require("expo/metro-config");
const { withNativeWind } = require("nativewind/metro");

const config = getDefaultConfig(__dirname);

// Windows 路徑含空格（"vscode project"）時，NativeWind 預設的 spawn 設定
// （shell:true + windowsVerbatimArguments:true）會讓 cmd.exe 把反斜線路徑切割錯誤。
//
// 修正方式：
// 1. 在 tailwind-cli.js 中改為 shell:false（Windows only），避免 shell 層介入
// 2. cliCommand 改用 "node <相對路徑>" 的形式，split(" ") 可正確分成兩個 token
//
// 注意：tailwind-cli.js 已手動 patch，移除 "..." 對路徑的包裝，改為直接傳路徑字串。
const twCliRelative = path
  .join("node_modules", "tailwindcss", "lib", "cli.js")
  .replace(/\\/g, "/");  // forward slashes → Node.js accepts both on Windows

module.exports = withNativeWind(config, {
  input: "./global.css",
  cliCommand: `node ${twCliRelative}`,
});
