# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest on `main` | Yes |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public GitHub issue
2. Use GitHub's [**private vulnerability reporting**](https://github.com/kiliancm94/daruma/security/advisories/new) to submit a report with:
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
3. You will receive a response within 72 hours

## Scope

Daruma is designed as a **local-only tool** with no built-in authentication. The following are known design decisions, not vulnerabilities:

- No authentication on the API (localhost-only by default)
- Tasks run Claude CLI with `--permission-mode auto`
- Environment variables stored in plaintext in the SQLite database

Security reports should focus on issues that could be exploited **within the intended local deployment model**, such as:

- Command injection via task parameters
- Path traversal
- Unexpected network exposure
- Dependency vulnerabilities
