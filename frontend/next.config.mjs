/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allows `docker build` to produce a minimal runtime image.
  output: 'standalone',
};

export default nextConfig;
