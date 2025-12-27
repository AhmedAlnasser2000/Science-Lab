# Code See Icon Sheet v1

## Badge semantics

| Key | Rail | Meaning |
| --- | --- | --- |
| state.crash | top | System crash detected. |
| state.error | top | Unhandled error detected. |
| state.warn | top | Warning condition reported. |
| state.blocked | top | Blocked by policy or availability. |
| conn.offline | top | Connection offline. |
| perf.slow | top | Performance degraded. |
| activity.muted | top | Muted activity detected. |
| expect.value | bottom | Expectation value tracked. |
| probe.fail | bottom | Probe failed. |
| probe.pass | bottom | Probe passed. |

## Rail placement
- Top rail: runtime and health signals (state/connection/perf/activity).
- Bottom rail: correctness and expectations (probe/expect).

## Severity and priority order
- crash > error > warn > probe.fail > expect.value > normal
- Unknown or unlisted keys default to normal severity.

## Border rules (state-only)
- crash: very dark / black-ish border
- error: red border
- warn: amber border
- probe.fail: purple border
- normal: neutral border

## Tooltip and inspector behavior
- Hovering a badge shows: node title, badge key, and short summary.
- Clicking a badge or using context menu Inspect opens a dialog with:
  - node id/title/type
  - full badge list (including detail/timestamp if present)
  - incoming/outgoing edge summary

## Icon style
- Auto: prefer mono when reduced_motion is on, otherwise color.
- Color: colored icon pack.
- Mono: monochrome icon pack.
