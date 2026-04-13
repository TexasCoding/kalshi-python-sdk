# Technology Stack

**Analysis Date:** 2026-04-13

## Languages

**Primary:**
- Python 3.12+ - SDK runtime (requires-python = ">=3.12")
- Python 3.12, 3.13 - Tested and supported versions

**Specification/Schema:**
- OpenAPI 3.0.0 - API specification for REST endpoints
- AsyncAPI 3.0.0 - WebSocket API specification

## Runtime

**Environment:**
- Python 3.12 (primary, specified in `.python-version`)
- Supports Python 3.12 and 3.13
- uv (Unix virtual environment manager) - Used for dependency management

**Package Manager:**
- uv - Modern Python package manager and project tool
- Lockfile: `uv.lock` (present and up-to-date)
- Installed via: `uv sync`

## Frameworks

**Core:**
- httpx 0.27-0.99 - HTTP client for sync and async requests
- pydantic 2.0-2.99 - Data validation and serialization
- cryptography 43-44 - RSA-PSS signing and key serialization

**Testing:**
- pytest 8.0-8.99 - Test runner
- pytest-asyncio 0.24-0.99 - Async test support
- respx 0.21-0.99 - httpx request mocking library

**Build/Dev:**
- hatchling - Build backend (specified in build-system)
- ruff 0.8-0.99 - Linting, formatting, and code quality
- mypy 1.13-1.99 - Static type checking (strict mode)

**Code Generation (planned):**
- datamodel-code-generator 0.26+ - OpenAPI/AsyncAPI model generation
- pyyaml 6.0+ - YAML parsing for spec files

## Key Dependencies

**Critical:**
- httpx - HTTP request library, supports both sync and async, used for all Kalshi API communication via `SyncTransport` and `AsyncTransport`
- pydantic - Model definition and validation; all API response parsing uses Pydantic v2 models with AliasChoices for field mapping
- cryptography - RSA-PSS-SHA256 signing for authentication; all API requests require signed authentication headers

**Infrastructure:**
- annotated-types - Pydantic annotation support
- anyio - Async primitives for httpx async support
- certifi - SSL/TLS certificate bundle for HTTPS connections
- cffi - C Foreign Function Interface for cryptography backend
- click, pathspec, platformdirs - Dependency chain for ruff/formatting

## Configuration

**Environment:**
- Configured via `kalshi/config.py` using `KalshiConfig` dataclass
- Key variables:
  - `KALSHI_KEY_ID` - API key identifier (required)
  - `KALSHI_PRIVATE_KEY` - PEM-formatted private key string (optional, alternative to _PATH)
  - `KALSHI_PRIVATE_KEY_PATH` - Path to private key file (optional, alternative to inline)
  - `KALSHI_API_BASE_URL` - Custom base URL (optional, defaults to production)
  - `KALSHI_DEMO` - String "true" to use demo environment (optional)

**Build:**
- `pyproject.toml` - PEP 518 compliant project metadata and tool configuration
- Tool configuration in pyproject.toml:
  - `[tool.ruff]` - target-version py312, line-length 100, linting rules
  - `[tool.mypy]` - strict mode, Python 3.12
  - `[tool.pytest.ini_options]` - asyncio_mode auto, testpaths tests
  - `[tool.hatch.build.targets.wheel]` - packages: kalshi

## Platform Requirements

**Development:**
- Python 3.12+ (enforced by requires-python)
- Unix/Linux/macOS/Windows (cross-platform via httpx and cryptography)
- uv (modern replacement for pip + virtualenv)
- For key generation: cryptography library (via pip dependencies)

**Production:**
- Python 3.12 or 3.13
- HTTPS connectivity to Kalshi API endpoints
- RSA private key in PEM format
- Internet connectivity (no local databases or services required)

---

*Stack analysis: 2026-04-13*
