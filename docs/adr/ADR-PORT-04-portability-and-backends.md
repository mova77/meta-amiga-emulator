# ADR-PORT-04 — A freestanding core behind explicit ports; SDL3 as the reference backend

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-27 |
| **Deciders** | Product Owner |
| **Scope** | Module boundaries, platform abstraction, backend selection, dependency policy |
| **Depends on** | [ADR-CORE-01](ADR-CORE-01-cycle-accurate-timing-model.md) |

## Context

"Cross-platform" usually degrades the same way: a platform conditional appears in an
emulation file for a good local reason, then another, and eventually the platforms diverge
in behaviour and only one of them is really tested. For a project whose central claim is
*deterministic, identical results everywhere*, that is fatal — a compatibility number
measured on macOS would say nothing about Windows.

The dependency question is equally consequential. Amiga emulators tend to accumulate
platform-specific display, audio and input paths for latency reasons. Each one is a
surface where behaviour can differ, and each one triples the maintenance of every frontend
feature.

## Decision

**D1 · The core is freestanding.** `core` has no I/O, no threads, no dynamic allocation
after initialisation, no platform headers, no third-party dependencies, and no dependency
beyond the C++23 standard library. It cannot open a file, read a clock or draw anything.
This is enforced by an architecture test in CI that scans the module's includes and
symbols, not by convention.

**D2 · Communication is through explicit ports.** The core interacts with the world only
through narrow, synchronous interfaces it is handed at construction:

| Port | Direction | Carries |
|------|-----------|---------|
| `VideoSink` | out | Completed frames with per-line mode metadata |
| `AudioSink` | out | Sample blocks at the emulated rate, with the emitting cycle |
| `InputSource` | in | Key, mouse and joystick events stamped with the cycle they apply at |
| `MediaSource` | in | Byte ranges of disk, ROM and CD images |
| `HostLog` | out | Diagnostics |

Every port is defined so that a null implementation is valid. Headless deterministic
verification (specification §9) is the core plus null ports plus a scripted
`InputSource`, and that configuration is what CI runs.

**D3 · Input is cycle-stamped, not polled.** Events enter with the emulated cycle at which
they take effect. Host frame timing cannot perturb emulated state — which is what makes
recorded input scripts replay identically, and therefore what makes the whole compatibility
measurement possible.

**D4 · SDL3 is the reference backend, and it is replaceable.** SDL3 covers window, GPU
presentation, audio, input and game controllers on all three platforms with one
well-maintained dependency. It lives entirely behind the ports; the core never includes an
SDL header. Native backends (Metal, D3D12, Vulkan, CoreAudio, WASAPI, PipeWire) may be
added later where measurement shows SDL3 costs real latency, and they are added as
alternative port implementations.

**D5 · Layering is fixed and enforced.**

```
frontend  ──▶ ports ──▶ core
tools     ──▶ ports ──▶ core
                        core ──▶ (nothing)
```

`core` never references `ports` or `frontend`. Violations fail the build.

**D6 · Dependency policy.** A new runtime dependency requires an ADR. It must be
GPL-3-compatible, available on all three platforms, and vendorable. Build- and test-time
tools are held to a lower bar. Non-free optional integrations (`capsimage`) are
detected-and-optional, default off, and absent from release binaries.

## Consequences

- Everything the emulator does is reachable headlessly. That is what makes the corpus
  runnable in CI, makes bugs reproducible from a script, and makes `meta-amiga-verify` a
  thin wrapper rather than a parallel implementation.
- The port boundary costs some indirection on the audio and video paths. Both are
  block-oriented, so the cost is per frame and per sample block, not per pixel or per
  sample — negligible against the emulation itself.
- D1 forbids allocation in the core after init, which means fixed-capacity buffers sized
  from the configuration. Deliberate: it removes an allocator from the determinism
  argument and removes a class of latency spike.
- The frontend cannot reach into emulation state directly; debugger and GUI features go
  through an explicit inspection interface. More work up front, and the reason the
  debugger will be able to run remotely later.

## Open decisions

- Whether the presentation backend runs on its own thread once the core is proven
  deterministic single-threaded, and how the handoff stays lock-free.
- Whether `tools` links `core` directly or drives it through the same port layer as the
  frontend.
