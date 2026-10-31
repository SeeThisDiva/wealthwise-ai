# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :---: |
| `1.0.x` | Yes |

## Threat Model

WealthWise is a local personal-finance dashboard and terminal workstation for a single user. Because it processes personal financial figures and optionally forwards bounded numeric/categorical profile attributes to Google Gemini when an API key is supplied, it is hardened against cross-origin and network attacks:

- **Loopback-only by default** (`127.0.0.1`), with `Host`-header allowlisting to defeat DNS rebinding. Binding to a non-loopback interface requires `WEALTHWISE_ALLOW_REMOTE=1`.
- **Cross-site & CSRF protection** via per-launch `X-CSRF-Token`, `Origin` verification on all state-changing `POST` endpoints, `Sec-Fetch-Site: cross-site` rejection, and side-effect-free `GET` routes.
- **Strict schema & type validation** using Pydantic (`extra="forbid"`, boolean-as-number rejection, finite numeric bounds, and allowlisted categorical enumerations).
- **Untrusted LLM boundary** when `GEMINI_API_KEY` or `X-Gemini-Api-Key` is provided: free-form client strings (including client names) never enter the prompt, API keys travel only in request headers (never URLs or logs), and model responses are reconstructed field-by-field with `https://` hostname allowlisting against the built-in product catalogue.
- **Zero external frontend dependencies**: self-hosted inline SVG iconography and strict `Content-Security-Policy` (`script-src 'self'`, `font-src 'self'`, `connect-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`).
- **Integrity vs. authenticity**: the SHA-256 value in audit records and exported PDFs is an integrity fingerprint (detecting accidental edits), not a cryptographic signature.

Do not expose the built-in Flask development server to untrusted networks (`WEALTHWISE_ALLOW_REMOTE=1`), as the application intentionally has no multi-user authentication layer.

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities. Report vulnerabilities privately via [GitHub Security Advisories](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository with reproduction steps and the affected component (`core/`, `knowledge/`, `reports/`, or `web/`).
