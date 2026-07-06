/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colours: {
        risk: {
          low: "#22c55e",
          medium: "#f59e0b",
          high: "#fb923c",
          severe: "#ef4444",
          unknown: "#64748b",
        },
        brand: {
          DEFAULT: "#1c3f6e",
          fg: "#0f172a",
        },
      },
    },
  },
  plugins: [],
};
