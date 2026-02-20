# DMTDB KiCad Libraries

Place your KiCad library files here:

```
kicad_libs/
├── symbols/          # .kicad_sym files
│   └── DMTDB.kicad_sym
├── footprints/       # .pretty folders containing .kicad_mod files
│   └── DMTDB.pretty/
│       └── R_0603.kicad_mod
└── 3dmodels/         # .step and .wrl files
    └── R_0603.step
```

## Naming Convention

For automatic linking with DMTDB parts:
- Symbol name = Part's `kicad_symbol` field (e.g., `DMTDB:BSS138`)
- Footprint name = Part's `kicad_footprint` field (e.g., `DMTDB:SOT-23`)

## KiCad Configuration

In KiCad, add this library path:
- **Symbols:** `http://YOUR_PI_IP:5000/kicad_libs/symbols/DMTDB.kicad_sym`
- **Footprints:** `http://YOUR_PI_IP:5000/kicad_libs/footprints/`

Or use local path if KiCad runs on the same machine:
- `/path/to/SW_PartsDB/kicad_libs/symbols/`
- `/path/to/SW_PartsDB/kicad_libs/footprints/`
