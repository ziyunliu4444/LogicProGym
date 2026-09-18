# Changelog

## 1.0.0

- Enforce per-track YAML observation selection on reset, steps, snapshots, and
  frame histories. Omitted `observe` now hides track state; add the required
  signal names explicitly. Unknown names are rejected. Raw cached LCD diagnostics
  are excluded from filtered snapshots; selected parameter readings remain.

- Separated musical examples, setup tools and manual live integration checks.
- Added shared-instrument and separate-track scripted demonstrations with
  public YAMLs, walkthroughs, and finite-run options.

- Fixed negative frame sleep intervals and burst-packet audio overlaps.
- Training saves before MIDI cleanup; CLI supervision bounds stuck shutdown
  with an explicit warning and nonzero exit status.
- Packaged reset examples and a device-neutral CC20 cutoff template.
- Documented configured baselines and stale controller-assignment troubleshooting.
- Added setup and troubleshooting guides for frames, checkpoint resume, and
  configured cutoff resets, with a checklist for validating local hardware.

## 1.0.0rc1

- Opt-in local-time observation frames with bounded audio/MIDI buffers, gap
  diagnostics, skipped-frame handling, and an observation-only example.

- Opt-in step timing and overwrite-protected run manifests, with freshness
  documentation and expanded episode-reset acceptance checks.
- Opt-in, explicitly agent-owned absolute MIDI control initialization on reset,
  with pre-connection validation and unconfirmed-send reporting.
- Consistent LogicProGym package, imports, command, environment ID and virtual ports.
- Read-only MIDI device discovery and device-neutral public configuration templates.
- Public YAML constructor and `LogicProGym/Logic-v0` Gymnasium registration.
- MIDI-only, Mackie-only and mixed per-track action configurations.
- Offline preview and diagnostics; live page/slot/name verification.
- Quoted instrument headers and explicit handling of truncated page numbers.
- MIDI notes, velocity, pitch bend and user-configured CC actions.
- Multi-track demo, checkpoint/resume training example and bounded cleanup.
- MIT license and source distribution documentation.
- Human MIDI feedback training, checkpoint session metadata and resume checks.
- MIDI CC learning/test helpers, with documented Unsigned/Scaled assignments.
- Mackie numeric observations with validity masks and reading diagnostics.
- Native macOS audio capture for both Logic editions, plus optional device input.
- Raw-audio energy policy example controlling a mapped MIDI CC knob.
- Source archive includes the fixtures and compatibility examples needed by tests.
- One standard installation includes MIDI, Mackie, audio and training dependencies.
- Lazy adapter imports defer loading device libraries until needed.
- SPDX MIT package metadata and a separate developer-only test extra.

Independent simultaneous Mackie feedback from multiple controllers remains
experimental; validate track and parameter routing for each setup.
