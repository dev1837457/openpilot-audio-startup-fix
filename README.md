# openpilot audio startup gate and optional ready chime

An independently tested, **version-specific** mitigation for intermittent `micd` and `soundd` startup failures on a comma 4 running AGNOS 19.8 and the September 25, 2026 openpilot `nightly-dev` snapshot (`a8f739bdbef28f9a3751c45805378228d28a9ddf`). This is an independent project, not an official comma.ai release.

**Created with OpenClaw using Astra.** The technical work, review, and testing were assisted by OpenClaw agents running Astra.

## Observed failure

On a failing cold start, both daemons repeatedly raised `sounddevice.PortAudioError: Error querying device -1` while opening their default input/output streams. `sound.service` had already finished, but the system `sound.target` became active near the end of the daemons' original retry window. Both streams opened shortly after the target became active. The old generic retry decorator hid the underlying exception; the patches retain the original retry behavior while logging it.

This evidence supports a startup-ordering race. It does **not** establish why the audio target is delayed or prove that every missing-default-device failure has the same cause.

## Changes

1. **Launcher gate:** On AGNOS, wait for system `sound.target` before starting openpilot's manager. Queries are bounded; if the target never appears, manager is not started. Non-AGNOS startup is unchanged.
2. **Exception logging:** Preserve each original PortAudio exception in `micd` and `soundd`, without changing their retry count or delay.
3. **Optional audio-ready cue:** A distinct, quiet, 0.33-second three-note WAV plays once per soundd launch after its output stream is active, a callback completes, and fresh valid microphone and selfdrive messages arrive while not engaged. Any alert or engagement cancels the cue; normal safety alerts retain priority. A missing/bad WAV suppresses only the cue.

The cue means **audio startup succeeded**, not that all openpilot engagement conditions are satisfied. This patch does not add a continuous stream-health interlock; runtime audio loss and the existing alive-but-stream-not-yet-open interval after manager launch remain possible. See [LIMITATIONS.md](LIMITATIONS.md).

## Compatibility and files

Apply only after comparing your checkout to the tested snapshot. Baseline SHA-256 hashes:

| File | SHA-256 |
| --- | --- |
| `launch_chffrplus.sh` | `2a8fd2fa79671bab0d50a1065507931f4538bcfc452b091c2a79163757c38db9` |
| `openpilot/system/micd.py` | `c35f29c24a4fa298267be11eac012b7f59fc01d17dc6270de7ca229f65152e6a` |
| `openpilot/selfdrive/ui/soundd.py` | `90d94c0b78936dcdc3828a93f75ab7d2f15015a8c344bd2a3c182e0ceff4cdef` |

`patches/01-*` changes the launcher, `02-*` logs microphone open failures, and `03-*` includes both speaker open logging and the optional cue. `audio_ready.wav` is an original generated asset; `generate_chime.py` reproduces it. The two `*.gated.sh` / `*.chime.py` files are complete patched references for review and offline tests, not additional files to install.

From the root of a **matching, backed-up** openpilot checkout while the device is parked/offroad, set `PATCH_DIR` to your clone of this repository and run:

```sh
git apply --check "$PATCH_DIR"/patches/*.patch
git apply "$PATCH_DIR"/patches/*.patch
install -m 644 "$PATCH_DIR"/audio_ready.wav openpilot/selfdrive/assets/sounds/audio_ready.wav
bash -n launch_chffrplus.sh
python3 -m py_compile openpilot/system/micd.py openpilot/selfdrive/ui/soundd.py
git diff --check
git diff -- launch_chffrplus.sh openpilot/system/micd.py openpilot/selfdrive/ui/soundd.py
```

Verify the baseline hashes **before** applying, preserve backups of all three source files, and inspect the resulting diff. The updater may replace local changes, so re-check after any update. Do not apply these patches to a different revision without rebasing and retesting them. For rollback, restore your exact backups and remove only the cue asset this project added, then validate on a parked boot.

## Verification

- Offline: 6 launcher-gate tests; 9 cue/alert-priority tests; shell and Python syntax; patch application against the exact baseline.
- Device: 3 consecutive parked cold starts after the gate had both streams open without PortAudio errors. On the chime build, the cue was heard and logged once after both streams opened.
- Limited driving trial: openpilot engagement was recorded; 0 missing `micd`/`soundd` process states across 1,194 manager-state samples, and no audio daemon errors or underrun warnings in that boot.

These are bounded observations, **not** a general vehicle-safety certification or a guarantee for future builds. No raw route/device logs are published here.

## License and attribution

**MIT licensed**—reuse, modification, and redistribution are allowed if the copyright and license notice are retained. The reference files contain portions of comma.ai's openpilot code; its upstream copyright is preserved alongside the project-contributor notice in [LICENSE](LICENSE). The original cue, patches, tests, and documentation are offered under the same permissive terms. [NOTICE.md](NOTICE.md) records the requested **Created with OpenClaw using Astra** credit. No network addresses, location information, route identifiers, or device/owner identifiers are included in this repository.
