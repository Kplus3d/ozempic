# Archived reports

These files are kept for history. They are **point-in-time artifacts** written during
the June 2026 development/audit cycle and are **not** current references. Several
statements in them are now stale or were superseded by later code changes. Nothing has
been edited — they are preserved verbatim.

| File | What it is | Why it's archived |
|---|---|---|
| `API_DOCUMENTATION.md` | Original API reference. | Superseded by `docs/API.md`, which is code-sourced and corrects several inaccuracies (see its "Corrections" section). |
| `audit-report.md` | First "complete audit & fix" report. | Point-in-time; e.g. its item 10 says the 3D viewer was replaced with a placeholder, but the current `Viewer3D.tsx` is a full Three.js mesh viewer. |
| `audit-report-final.md` | "Comprehensive audit report". | Point-in-time; its "needs attention" items (no file-size validation, no auth, no batch processing) have since been implemented — the code now has all three. |
| `IMPROVEMENTS_SUMMARY.md` | Summary of the improvement round. | Point-in-time status report; describes features as "just added". |

For current, verified documentation use:

- [`../README.md`](../../README.md)
- [`../SETUP.md`](../SETUP.md)
- [`../ARCHITECTURE.md`](../ARCHITECTURE.md)
- [`../API.md`](../API.md)