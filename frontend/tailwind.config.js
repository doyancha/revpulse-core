/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        fintech: {
          bg: '#090D16',
          card: '#101623',
          cardHover: '#151D2E',
          border: '#1E293B',
          borderLight: '#334155',
          accent: '#6366F1',
          accentHover: '#4F46E5',
          success: '#10B981',
          warning: '#F59E0B',
          danger: '#EF4444',
          muted: '#94A3B8'
        }
      }
    },
  },
  plugins: [],
}
