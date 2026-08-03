/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return [
      { source: "/knowledge", destination: "/agent", permanent: false },
      { source: "/purchase-plans", destination: "/family", permanent: false },
      { source: "/refill-plans", destination: "/family", permanent: false },
      { source: "/medicine-box", destination: "/family", permanent: false },
      { source: "/reminders", destination: "/agent", permanent: false },
      { source: "/agent-runs/:id", destination: "/agent-runs", permanent: false },
    ];
  },
};

export default nextConfig;
