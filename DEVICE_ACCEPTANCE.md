# Reliability acceptance

Automated checks do not establish physical microphone, installed voice or mobile
background behavior. Record the tested source commit, cloud version, installed
APK version, operating system and pass/fail for each item below. Do not record
passwords, tokens or personal audio in the report.

The desktop Online workspace opens the deployed website. Its new reliability
behavior must be tested against the deployed candidate, not an older live build.
Android candidate source is 1.28/code 29; the offered APK remains 1.27/code 28
until rebuilt with the existing signing key and staged separately.

## Windows

1. In a normal PowerShell session at the project root, run
   `.\scripts\start_desktop.ps1 -Online`. The local inference backend must not
   start. No GPU underclock change is required for this Online-only check.
2. The isolated browser check either opens Online or shows an actionable browser
   fallback while the desktop stays open. A failure must not repeat the probe
   whenever Account, Say it or Online is reopened in the same session.
3. If the built-in browser is unavailable, select **Open in browser**. Sign in
   there using the same approved account. This uses the system browser's session;
   it does not transfer the embedded browser's credentials or drafts.
4. In a working embedded session, verify Account and Say it share sign-in with
   Online; restart and verify session restoration. Sign out and verify access
   is removed. Confirm the expected account before testing opt-in history.
5. Allow the microphone and record a short phrase; Stop must release it. Deny
   permission and confirm a useful error. Switching to Local must stop capture
   and Read Aloud; Local text must remain intact without automatic upload.
6. Read a long multilingual result, Stop partway through and restart. Try a
   language without an installed voice. Export a result, cancel one Save dialog,
   and verify only the explicitly saved file exists with complete text.

## Android

ADB now starts on this workstation, but no device was attached when checked.
Connect the test phone by USB, enable USB debugging and accept its debugging
prompt. Confirm it appears in `adb devices -l` before automated device tests.

1. Verify installed version and signing continuity before installing a candidate.
   Keep the owner's existing signing key; do not create a replacement.
2. In Online and Offline, test short recording, microphone denial, Stop/restart,
   available/unavailable voices and app backgrounding.
3. In Online, record for more than five minutes, interrupt a later upload, and
   verify retry preserves completed parts and sends only unfinished parts.
4. Reload/reopen after interruption and check recovery. Sign out and switch
   accounts; another account must not inherit the first account's draft.

## iPhone

Use the candidate PWA in Safari. The native iOS source needs a separate Mac build.
Check sign-in, microphone allow/deny, short and multi-part recording, background
interruption, reopen/recovery, unavailable voices and Read Aloud Stop/restart.

Reliability stays open until these results are recorded. Publishing source or
passing CI alone does not update the live service, installed APK or Windows EXE.
