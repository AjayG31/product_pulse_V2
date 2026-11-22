# Local pre-merge checklist

Use this checklist for the exact source snapshot proposed for review. The local PowerShell runner records command output and a source snapshot SHA-256 digest in the evidence file for each ticket.

## Required before approval

- [ ] Run the applicable command from the ticket's documented acceptance evidence using `scripts/check.ps1`.
- [ ] Confirm the runner reports success for every applicable automated check; fix and rerun any failure.
- [ ] Review the exact source snapshot digest recorded at the end of the run and confirm it identifies the files under review.
- [ ] Review the per-ticket evidence file and confirm it records command, tool versions, test/security results, and unresolved gates.
- [ ] Confirm no GitHub Actions, Playwright, pending evaluation threshold, or unapproved detection/notification activation is represented as an applicable check or passed gate.
- [ ] Record the reviewer, date, and disposition with the proposed revision's review record.

The applicable checks depend on the ticket. A skipped, unavailable, or failed required check blocks approval until resolved and rerun. Final held-out evaluation and its pending EV-01/02/03 gates are not part of the foundation baseline.

