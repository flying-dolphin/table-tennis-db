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
        brand: {
          primary: "#7FA9D9",
          strong: "#4F79B3",
          deep: "#6B97CB",
          soft: "#DCEAF8",
          mist: "#EAF3FF",
          fog: "#F5F9FE",
        },
        surface: {
          primary: "#FFFFFF",
          secondary: "#F8FBFF",
          tinted: "#EEF5FC",
        },
        page: {
          background: "#F7F9FC",
        },
        border: {
          subtle: "#D9E4F2",
          strong: "#C7D7EA",
        },
        text: {
          primary: "#1E2A3D",
          secondary: "#5F6F86",
          tertiary: "#8A9AB0",
        },
        state: {
          success: "#4E9B7A",
          danger: "#C56B72",
          warning: "#C89A4B",
          info: "#6E86A6",
        }
      },
      borderRadius: {
        '3xl': '32px',
      },
      fontFamily: {
        heading: ["Noto Sans SC", "sans-serif"],
        body: ["Noto Sans SC", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
