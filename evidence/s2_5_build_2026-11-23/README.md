# The probe design `s2b`, as built on 2026-11-23

`s2b.bit` is the bitstream of the build that `pl/s2b/build.json` records (Vivado 2025.2,
`pl/s2b/build_s2b.tcl`; docs/s2_plan.md, sections 45 and 46): 2,083,859 bytes, sha256
`7f0e1af8a340fb5fe36749447b3266fc401fa4ab3d9c13dde8a6abe29f887a12`. A design cannot be built
again to the same bytes, and `build/` is not in git; this is the copy that is, as
`evidence/s2_1_17A6_2026-11-20/s2a.bit` is for `s2a`. `host/stage_designs.py` puts it where
the run script looks for it, once it has the recorded hash.

It is an opaque file to everything in this repository: read whole, hashed, written, sent to
the board. Nothing here looks into it. It has not been on a board.
