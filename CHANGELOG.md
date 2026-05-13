# Changelog

## [0.3.2] - 2026-05-14

### Fixed

- `chat SESSION -p PROJECT` now correctly filters by project (was ignoring `-p`)
- `iter_messages()` no longer crashes on non-dict JSON values (arrays, strings)
- `context`/`last` no longer crash when `msg` field is not a dict
- `chat -p PROJECT` now shows candidates and exits 1 on multiple matches
- `errors`/`tools`/`cost -p` now exit 1 when no projects match the filter
- Eliminated double `stat()` calls in `find_sessions()` and `cmd_projects()` (race condition fix)
- `tool_use.name` that is `None` or non-string is now treated as `"unknown"`
- Malformed JSONL smoke test uses `trap` for reliable cleanup

### Added

- Smoke test for `chat session1 -p test-project --json`
- Smoke tests for non-existent project on `errors`/`tools`/`cost`
- CHANGELOG.md
- Security/Privacy section in README

## [0.3.1] - 2026-05-13

### Fixed

- 25 Codex Round 2 review items (robustness, edge cases, test coverage)

## [0.3.0] - 2026-05-12

### Fixed

- 29 Codex Round 1 review items (input validation, error handling, output sanitization)

## [0.2.0] - 2026-05-11

### Added

- Full feature set: search, projects, last, context, chat, errors, tools, cost
- Regex search, date filters, compact/JSON output modes
- PyPI packaging (`pickel-cli`)

## [0.1.0] - 2026-05-10

### Added

- Initial release
- Basic conversation log mining from `~/.claude/projects/`
