import type { Config } from "tailwindcss";

export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        mint: "#A8D0C9",
        dark: "#1A1A1A",
        soft: "#F4F7F6",
        primary: "#0891B2",
        cta: "#22C55E",
      },
      borderRadius: {
        '3xl': '32px',
      },
      fontFamily: {
        heading: ["Archivo", "sans-serif"],
        body: ["Space Grotesk", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
