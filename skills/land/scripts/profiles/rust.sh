# Rust scan profile, sourced by diff-scan.sh when the repo has a
# Cargo.toml. `check`, `added_lines`, `RANGE`, and `TOTAL` are already defined
# by the caller; this file only adds `check` calls.
#
# Universal Rust only: patterns any Rust reviewer would flag on any project.
# Project-specific traumas (a particular repo's portability rules, layout
# assumptions, style vendettas) belong in that project's own instructions,
# not here.

# This is a sourced fragment, not a standalone script: `check` only exists
# inside diff-scan.sh. Fail loudly when run directly.
if ! declare -F check >/dev/null 2>&1; then
  echo "rust.sh is a profile fragment; run: diff-scan.sh <base-ref> rust" >&2
  return 1 2>/dev/null || exit 1
fi

check "Rust debug or placeholder macros" \
  'dbg!\(|todo!\(|unimplemented!\(' '*.rs'

check "Newly added #[allow(...)] (a silenced lint deserves a glance)" \
  '#\[allow\(' '*.rs'
