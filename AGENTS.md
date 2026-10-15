# Guidelines

## Package Manager

Always use `uv` to run Python. Never invoke `python`, `pip`, or `pytest` directly.

```bash
uv run python -c "..."
uv run python script.py
uv run pytest
uv run pytest *_test.py **/*_test.py
uv add <package>
uv add <package> --dev
```

---

## Linting and Formatting

Run linting and formatting via `uvx`:

```bash
uvx ruff check *.py **/*.py --fix
uvx ruff format *.py **/*.py
```

The project's `pyproject.toml` defines the full ruff configuration. Do not redefine rules inline. The sections below describe what each enabled rule set enforces so that code is written correctly from the start.

### E - pycodestyle

Basic PEP 8 style. Line length (E501) and whitespace around slices (E203) are ignored because the formatter handles them. All other style violations are errors.

### F - Pyflakes

Catches undefined names, unused imports, and unused variables. Remove all unused imports and variables before committing. Never silence F-rules with `# noqa` unless there is a documented reason.

### I - isort

Imports must be ordered: standard library, then third-party, then local. Use one blank line between groups. The formatter enforces this automatically.

### B - flake8-bugbear

Catches common logic bugs and opinionated style problems. Key rules in effect:

- Do not use mutable default arguments (B006). Use `None` and assign inside the function body.
- Do not call functions in default argument values (B008). This rule is ignored for FastAPI's `Depends` pattern, which is the only permitted exception.
- Do not use `functools.lru_cache` or `functools.cache` on instance methods (B019) - it causes memory leaks.
- Do not use `assert False`; raise `AssertionError()` instead (B011).
- Always pass `strict=` explicitly to `zip()` (B905).
- Do not loop over a collection while mutating it (B909).

### UP - pyupgrade

Enforces modern Python 3.13 syntax. Examples: use `X | Y` union syntax over `Union[X, Y]`, use `list[str]` over `List[str]`, use f-strings over `.format()` where possible.

### N - pep8-naming

- Classes: `CapWords`
- Functions, methods, variables: `snake_case`
- Constants: `UPPER_CASE`
- Type variables: `CapWords` with a `T` suffix (e.g. `ItemT`)
- Do not shadow Python builtins (`list`, `id`, `type`, etc.)

### C4 - flake8-comprehensions

Prefer comprehension and literal syntax over unnecessary wrapping calls. Examples:

- Write `[x for x in y]` not `list(x for x in y)` (C400)
- Write `{k: v for ...}` not `dict([(k, v) for ...])` (C402)
- Write `{"a", "b"}` not `set(["a", "b"])` (C405)
- Avoid double-casting like `list(list(...))` (C414)
- Use `dict.fromkeys(iterable)` instead of `{k: None for k in iterable}` (C420)

### C90 - mccabe

Function complexity is capped at 40. If a function exceeds this, split it into smaller units.

### D - pydocstyle (Google convention)

All public modules, classes, and functions must have docstrings. Use Google style throughout:

```python
def fetch_data(url: str, timeout: int = 30) -> dict:
    """Fetch JSON data from the given URL.

    Args:
        url: The endpoint to query.
        timeout: Request timeout in seconds.

    Returns:
        Parsed JSON response as a dictionary.

    Raises:
        HTTPError: If the response status is not 2xx.
    """
```

The `D417` rule (missing argument descriptions) is ignored - describe arguments as a group, not one by one when it would be redundant.

Private functions (prefixed with `_`) do not require docstrings but benefit from them when the logic is non-obvious.

Docs string content should always be very brief and only contain necessary information.

### TID - flake8-tidy-imports

Relative imports beyond one level are banned. Use absolute imports. Banned module patterns apply as configured in `pyproject.toml`.

### ANN - flake8-annotations

All function arguments and return types must be annotated (ANN001, ANN201–ANN206). Exceptions:

- `*args` (ANN002) and `**kwargs` (ANN003) do not require annotations.
- `typing.Any` (ANN401) is permitted but must not be used where a proper type is feasible.

### ASYNC - flake8-async

- Do not call blocking I/O inside async functions: no `open()` (ASYNC230), no `time.sleep()` (ASYNC251), no blocking HTTP calls (ASYNC210, ASYNC212), no blocking subprocess calls (ASYNC220–ASYNC222).
- Do not use `while True: await sleep(...)` busy-wait loops; use `asyncio.Event` instead (ASYNC110).
- Async functions must not define a `timeout` parameter - pass timeouts via the calling context (ASYNC109).

### PTH - flake8-use-pathlib

Use `pathlib.Path` for all filesystem operations. The `os` and `os.path` modules are banned for path handling.

```python
# Correct
from pathlib import Path

path = Path("data/input.csv")
content = path.read_text()
path.mkdir(parents=True, exist_ok=True)

# Wrong
import os
os.path.join("data", "input.csv")
os.makedirs("data", exist_ok=True)
```

---
## Comments

In-line comments should only appear in functions and should be very brief. Design decitions and background informations will never be part of this comment.

---

## Logging

Use f-strings in all log messages. Never use `%`-style or `.format()` interpolation in log calls.

```python
# Correct
logger.info(f"Processing user {user_id}")
logger.debug(f"Raw payload: {payload}")

# Wrong
logger.info("Processing user %s", user_id)
logger.debug("Payload: {}".format(payload))
```

Log level guidance:
- **info**: control flow milestones visible in production. Keep payloads out.
- **debug**: full data inspection for local debugging. Acceptable to log large structures here.

---

## Typing

Follow PEP-483 and PEP-484. Use `StrEnum` over `Literal` for string constants when the values form a closed set. Prefer `X | Y` union syntax over `Union[X, Y]`.

Use `Any` only as a last resort when implementing a strict type would require disproportionate effort. Document the reason with a comment when you do.

---

## Tests

Test files live next to the source file they cover, in the same directory. File naming: append `_test.py` to the source filename.

```
app/demo_service/service.py
app/demo_service/service_test.py
```

Run tests:

```bash
uv run pytest *_test.py **/*_test.py
