# PP-029 verification triage

This record preserves the intermediate PP-029 verification attempts and why they do not represent a security finding.

- Initial command: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/check.ps1 -Ticket PP-029 -EvidencePath docs/evidence/m4/PP-029.txt`.
- Initial result before the additional coverage tests: focused Admin/auth boundary suite **49 passed**; backend regression **108 passed**; one existing Starlette/httpx deprecation warning per pytest run; Bandit clean across **6,170 lines**; pip-audit reported **no known vulnerabilities**. The check completed successfully.
- After adding absolute-session-expiry coverage, a rerun printed a failure marker. The run was interrupted immediately; its partial PowerShell transcript is retained as `PP-029-interrupted-transcript.txt`.
- An isolated diagnostic without the project wrapper first failed during pytest setup/cleanup because the sandbox could not access the default system temp/cache paths. This was an environment failure before the test body ran.
- The isolated run with the approved workspace-local temp directory reached the test and showed the test assertion compared a lowercased `Set-Cookie` header to the mixed-case cookie-name constant. The actual response used a cookie `Max-Age` of 599 seconds for an absolute deadline 10 minutes away. The application behavior was bounded as specified; the test assertion was case-sensitive by mistake.
- The test now lowercases the cookie-name constant before comparison. The final full PP-029 runner is rerun after that correction; its result is recorded in `PP-029.txt`.

No application code was changed in response to the intermediate test failure, and no vulnerability or authorization bypass was found.
