/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        // ── RecallMap 設計系統配色 ──────────────────────────────────────
        // 整個系統只允許使用以下四種顏色，禁止引入其他顏色（包含 Tailwind 預設色）。
        rm: {
          deep:  "#274c5e",  // 最深 ─ 主背景、頂層文字區塊
          light: "#dae9f4",  // 最淺 ─ 主要文字、按鈕、高亮元素
          mid:   "#77919d",  // 中間 ─ 邊框、次要文字、停用狀態
          muted: "#7f9eb2",  // 淡藍 ─ 輔助文字、placeholder、互動提示
        },
      },
    },
  },
  plugins: [],
};
