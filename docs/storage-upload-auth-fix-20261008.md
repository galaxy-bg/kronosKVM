# Storage upload authentication fix — 2026-10-08

The first appliance (`192.168.31.185`, `infrabox-8ed89866`) logged repeated ISO
upload PUT requests returning 403 about every 30 seconds. No active staging
temporary file was present and disk space was sufficient.

Uploads use XMLHttpRequest, which does not pass through the authentication
layer's fetch wrapper. The upload request omitted `X-InfraBox-Request: 1`, so
the same-origin mutation guard rejected it even with a valid admin session.
Added the required header and changed the dashboard loader's cache version.
Authentication, quotas and proxy timeout settings remain enforced.

Only the web image was rebuilt/recreated. The API was not restarted. Source
backup: `/var/backups/kronoskvm/upload-auth-20261008.MDHylh`.
Previous web tag: `kronoskvm-web:pre-upload-auth-20261008`.
New web tag: `kronoskvm-web:upload-auth-20261008`, also tagged `:dev`.

## Validation

- 28 authentication tests passed, including an actual authenticated storage
  upload that rejects a missing marker with 403 and stores the marked request.
- Live Chrome used the application's file-input/XHR path to upload 16,777,216
  bytes at a throttled 256 KiB/s. The upload took 66.357 seconds, issued exactly
  one PUT and maintained monotonically increasing progress.
- Downloaded bytes matched SHA256
  `55c7e25571a69216de25162f191bb2847201a09ee7efe46b5bada034acc695d5`.
- The uniquely named diagnostic file was deleted successfully and the diagnostic
  administrator session was logged out. Existing user files were not modified.
- Lint and JavaScript syntax checks passed.

Refresh the browser before retrying an upload to load the corrected code.
The operator's original ISO still needs to be retried; the bounded diagnostic
test does not validate every file size, network interruption or idle timeout.
The second appliance has not yet received this web fix.
