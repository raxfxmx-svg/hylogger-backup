const { PHASE_PRODUCTION_BUILD } = require("next/constants");
const { assertProductionApiBase } = require("./lib/api-config.cjs");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,

  // deck.gl ships modern JS that Next sometimes needs to compile itself.
  // If you ever see a syntax error coming from inside node_modules/@deck.gl,
  // add the offending package to this list.
  transpilePackages: [
    "deck.gl",
    "@deck.gl/core",
    "@deck.gl/layers",
    "@deck.gl/react",
    "@luma.gl/core",
  ],
};

module.exports = (phase) => {
  if (phase === PHASE_PRODUCTION_BUILD) {
    const apiBase = assertProductionApiBase(process.env.NEXT_PUBLIC_API_BASE);
    if (!apiBase) console.warn("NEXT_PUBLIC_API_BASE is unset. Data views will display a service-not-connected message.");
  }
  return nextConfig;
};
