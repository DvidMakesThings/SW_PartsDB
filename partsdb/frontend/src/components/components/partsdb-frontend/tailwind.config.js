/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "1rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        border: "var(--border)",
        background: "var(--bg)",
        surface: "var(--surface)",
        primary: "var(--accent)",
        "primary-foreground": "#ffffff",
        secondary: "#4b5563",
        "secondary-foreground": "#f3f4f6",
        accent: "var(--accent)",
        "accent-foreground": "#ffffff",
        muted: "#374151",
        "muted-foreground": "#9ca3af",
      },
      textColor: {
        default: "var(--text)",
      },
      backgroundColor: {
        default: "var(--bg)",
        card: "var(--surface)",
      },
      borderRadius: {
        lg: "0.5rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}

