/** @type {import('next').NextConfig} */
// Standalone output so the runtime image copies only the server bundle rather than node_modules.
module.exports = {
  output: "standalone",
  reactStrictMode: true,
  devIndicators: false,
};
