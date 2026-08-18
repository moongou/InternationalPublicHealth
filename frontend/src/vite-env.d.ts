/// <reference types="vite/client" />

declare module 'world-atlas/countries-110m.json' {
  const value: import('topojson-specification').Topology
  export default value
}
