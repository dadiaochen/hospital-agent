import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        mist: "#eef4f2",
        clinic: "#0f766e",
        amberline: "#b45309",
        berry: "#9f1239",
      },
    },
  },
  plugins: [],
};

export default config;

