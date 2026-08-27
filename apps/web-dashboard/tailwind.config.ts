import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        tactical: {
          dark: "#0a0d14",
          surface: "#111726",
          border: "#1f293d",
          accent: "#00e5ff",
          danger: "#ff1744",
          warning: "#ff9100",
          success: "#00e676",
        },
      },
    },
  },
  plugins: [],
};
export default config;
