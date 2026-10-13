# Three.js vendor source

This directory contains the minimum runtime subset of `three@0.160.0` needed
by the viewer: `three.module.js`, `OrbitControls`, `GLTFLoader`, and
`BufferGeometryUtils`.

- Source: `https://registry.npmjs.org/three/-/three-0.160.0.tgz`
- Source archive SHA-256: `1ee2f935c4f555814b388e87b5ef78a44856bd2e9d0feb88643a6e193fb42856`
- License: MIT, see `LICENSE`.

The files are intentionally served by the local FastAPI static route so the
portable package does not require a CDN or external network access.
