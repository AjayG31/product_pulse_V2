# M4 Evidence and Fingerprint Cleanup

**Date:** 26 November 2026
**Scope:** Review and disposition of the 11 trailing-whitespace findings reported by `git diff --check b287b97 9c31399`, preservation of historical transcripts, and correction of source fingerprint inputs.

## Whitespace findings

The 11 findings resolve to five Markdown metadata lines and six raw PowerShell transcript metadata lines.

| File | Finding | Disposition |
|---|---|---|
| `M4_IMPLEMENTATION_BRIEF.md` lines 3–4 | Two trailing spaces used for Markdown line breaks | Replaced with explicit `<br>` tags; rendered line breaks are preserved |
| `M4_COMPLETION_REPORT.md` lines 3–5 | Two trailing spaces used for Markdown line breaks | Replaced with explicit `<br>` tags; rendered line breaks are preserved |
| `M4_FINAL_SECURITY_REGRESSION.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |
| `PP-029-interrupted-transcript.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |
| `PP-029.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |
| `PP-037.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |
| `PP-048-initial-transcript.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |
| `PP-048.txt` line 6 | `Configuration Name: ` | Preserved unchanged as raw transcript output |

The six `.txt` lines represent an empty PowerShell transcript configuration value. They were not normalized, copied over, or rewritten. Their original and post-cleanup SHA-256 values match:

| Transcript | Original SHA-256 | Post-cleanup SHA-256 |
|---|---|---|
| `M4_FINAL_SECURITY_REGRESSION.txt` | `5c1779bf4f365f7190122ed91029b30fba72cf52186c28bb7c9598f4f41b8654` | `5c1779bf4f365f7190122ed91029b30fba72cf52186c28bb7c9598f4f41b8654` |
| `PP-029-interrupted-transcript.txt` | `d012b000f4e003f9433a194ebb5313df38b7831c9affb8cd32d533f6b44801c1` | `d012b000f4e003f9433a194ebb5313df38b7831c9affb8cd32d533f6b44801c1` |
| `PP-029.txt` | `3aae0710537c7d68e25450bff38653caa9e27439441a99927649b4aeb4321675` | `3aae0710537c7d68e25450bff38653caa9e27439441a99927649b4aeb4321675` |
| `PP-037.txt` | `aad329120945dd80c0d2236d22e51b7df461aff5c180cdf13b4d9d783616881f` | `aad329120945dd80c0d2236d22e51b7df461aff5c180cdf13b4d9d783616881f` |
| `PP-048-initial-transcript.txt` | `3e64e52864676cff5ba8e2213cf3e85d1d4c9cc3f43ab580564a60277f5ee679` | `3e64e52864676cff5ba8e2213cf3e85d1d4c9cc3f43ab580564a60277f5ee679` |
| `PP-048.txt` | `3dcba18169aea49fe630f0f5160ebac9bc467156bd0f44e965df36abbe779b62` | `3dcba18169aea49fe630f0f5160ebac9bc467156bd0f44e965df36abbe779b62` |

The two Markdown files were changed only to replace trailing-space line breaks with `<br>`. Their original and resulting whole-file hashes are retained here:

| Markdown file | Original SHA-256 | Post-cleanup SHA-256 |
|---|---|---|
| `M4_IMPLEMENTATION_BRIEF.md` | `8e7fef09c3003ae1c596a1ba91393a07b84a004c906ce1fab41cb477b9c0c0d9` | `c32d276cb625396928c29546d11cc2b8401aa2cc3821c5eb767c0cda9d261305` |
| `M4_COMPLETION_REPORT.md` | `7fc6551732ffb917fca05830cc472bff6bc0c0cac7cdc1f302d91d89c2622660` | `e0845a06be9fa983e7ac7ad4f9756a9ac55c51699b10acafe88c90e500927ef0` |

The original `b287b97..9c31399` commit range is immutable. Its historical diff-check will continue to report the original findings; the five Markdown corrections are in the working tree after `9c31399`, and the six transcript lines remain unchanged by design. No commit or history rewrite was made.

## Fingerprint script correction

`scripts/source-fingerprint.ps1` now reports version 2 and prunes or excludes generated inputs before hashing. Excluded directories include Python bytecode/cache and environment folders, `.tools`, `node_modules`, test/tool caches, and build/output folders. Excluded files include `.pyc`/`.pyo`/`.pyd`, TypeScript build info, coverage outputs, logs, temporary files, OS metadata, and environment files other than the explicitly selected `.env.example`. Directory traversal skips reparse points and uses ordinal relative-path ordering.

The earlier fingerprint values in the tickets and completion report remain untouched historical evidence. The value `023cdbc1020ff0cd32922a6cc8ac4f8db7ff289f41e03b17c6c4a2f915c76b92` (149 files) was captured for commit `9c31399` with the old algorithm, which included generated `.pyc` files. The corrected version 2 script was run twice after cleanup and returned the same result both times:

The old algorithm hashed selected file bytes without normalizing CRLF/LF line endings. Line-ending normalization therefore does not explain the historical fingerprint mismatch. The v1 input set included 59 `.pyc` files; compiled bytecode embeds the source checkout path, making those retained values environment-sensitive. The historical records are preserved as reported and were not recalculated or replaced.

```text
Implementation source snapshot v2 SHA-256 (generated artifacts excluded): c93dd51c06705773e541bdb8dfb0412a4e813593add6d8ad885c938b7f2e0ebe
Files included: 90
```

This version 2 value describes the post-cleanup working tree, including the updated fingerprint script; it is not a replacement for or a fingerprint of commit `9c31399`.

## Verification record

Fresh results for the exact `9c31399` checkout are saved in `M4_VERIFICATION_9c31399.md`. No application code, migration, approved specification, test transcript, ticket status, or Product Owner acceptance status was changed as part of this cleanup.
