/** @type {import('next').NextConfig} */
const nextConfig = {
  // API routes run server-side only — DB credentials never reach the browser
  // The pg client is a Node.js library; mark it external so Next doesn't
  // try to bundle it for the browser.
  serverExternalPackages: ["pg"],
};

module.exports = nextConfig;
