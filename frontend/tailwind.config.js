/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./editor/**/*.{js,ts,jsx,tsx,mdx}",
    "./chat/**/*.{js,ts,jsx,tsx,mdx}",
    "./project/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        background: "#090d16",
        surface: "#0f172a",
        surfaceHover: "#1e293b",
        border: "#1e293b",
        primary: {
          50: "#eef2ff",
          100: "#e0e7ff",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
        },
        cyanGlow: "#06b6d4",
        violetGlow: "#8b5cf6",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "sans-serif"],
        mono: ["var(--font-geist-mono)", "monospace"],
      },
      boxShadow: {
        glow: "0 0 25px -5px rgba(99, 102, 241, 0.3)",
        cyanGlow: "0 0 25px -5px rgba(6, 182, 212, 0.3)",
      },
    },
  },
  plugins: [],
};
