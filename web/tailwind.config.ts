import type { Config } from "tailwindcss";

export default {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
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
          tertiary: "#617283", // was #8A9AB0 (2.87:1 fail) → now 4.95:1 on white
        },
        gold: {
          DEFAULT: '#C5A059',
          bg: 'rgba(197,160,89,0.1)',
        },
        state: {
          success: "#4E9B7A",
          danger: "#C56B72",
          warning: "#C89A4B",
          info: "#6E86A6",
          // Darker variants for small text (caption/micro) — original colors only pass for large text
          "success-text": "#3A7A5E", // 5.09:1 on white
          "danger-text": "#9E3E44",  // 6.51:1 on white
          "warning-text": "#8C5F0A", // 5.59:1 on white
        }
      },
      borderRadius: {
        'sm': '8px',
        'md': '16px',
        'lg': '24px',
        'full': '9999px',
      },
      fontSize: {
        'display': ['28px', { lineHeight: '1.1', letterSpacing: '-0.01em' }],
        'data-hero': ['24px', { lineHeight: '1.15', letterSpacing: '-0.01em' }],
        'heading-1': ['20px', { lineHeight: '1.25', letterSpacing: '-0.01em' }],
        'heading-2': ['17px', { lineHeight: '1.3' }],
        'body-lg': ['15px', { lineHeight: '1.4' }],
        'body': ['14px', { lineHeight: '1.5' }],
        'caption': ['12px', { lineHeight: '1.4', letterSpacing: '0.01em' }],
        'micro': ['10px', { lineHeight: '1.3', letterSpacing: '0.03em' }],
      },
      fontFamily: {
        heading: ["var(--font-noto-sans-sc)", "Noto Sans SC", "sans-serif"],
        body: ["var(--font-noto-sans-sc)", "Noto Sans SC", "sans-serif"],
        numeric: ["var(--font-inter)", "Inter", "DIN Alternate", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
