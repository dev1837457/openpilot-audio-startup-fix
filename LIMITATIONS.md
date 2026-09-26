# Scope and limitations

- `sound.target` is an ordering signal, not proof that a particular input/output stream or physical speaker is healthy. The original per-daemon stream-open retries remain in place after the gate.
- Until both streams are open, the existing manager reports a retrying daemon as a running process. The launcher gate reduces the observed cold-start race but does **not** implement an end-to-end audio-ready engagement interlock. A larger design would publish actual stream readiness and make the driving state machine consume it.
- If the target never appears, this gate leaves openpilot's manager and UI unstarted instead of bypassing audio readiness. The launcher records an error locally; recovery requires diagnosing audio startup and restoring or repairing the installation.
- The optional cue is a startup indicator. It may remain silent if a safety alert occurs first, data are late/invalid, the vehicle is already engaged, or the asset fails. Silence is not itself a definitive fault diagnosis. A cue does not guarantee future audio availability or prove every engagement condition.
- A cue buffer already handed to PortAudio cannot be recalled. Newly arriving safety alerts replace subsequent audio blocks in the existing callback cadence; this is not a hard-real-time atomic preemption guarantee.
- This patch was tested on one device and one openpilot/AGNOS combination. It should be reviewed against each new source revision. A nightly update can overwrite local patches and the WAV.
- This repository contains summarized, non-identifying findings only—no raw logs, routes, network identifiers, or location data.
