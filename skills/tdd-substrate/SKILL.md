---
name: tdd-substrate
description: Test-driven development substrate for solo + small-team builds. Iron-law red-green-refactor with dual-runtime examples (Vitest for TypeScript/Next.js, pytest for Python/FastAPI), regression-test-for-every-bug pattern, property-based testing for invariants, bilingual test-fixture handling, and best-of-best-aware "pick the test design and ship" stance. Use when the user says /tdd, "write tests first", "red-green-refactor", "regression test for X", or is about to add a feature or fix a bug on any code path. Covers JavaScript/TypeScript + Python; not strictly enforced for Bash, Rust, or Go (defer to runtime-native test discipline there).
---

## /tdd-substrate

Iron-law TDD that incorporates the strongest capabilities from every comparable skill into one substrate, then ships a single opinionated reference. The build pattern follows the everything-comparison rule: read each source, identify the strongest piece in each, fold all of them in.

## Source comparison (everything-comparison build)

This substrate was built by reading each source, identifying the capability they ship best, and incorporating all of those capabilities into one skill at a single voice + density bar. Sources are cited inline.

| Source | What got incorporated | What was left out |
|---|---|---|
| [obra/superpowers/skills/test-driven-development](https://github.com/obra/superpowers/tree/main/skills/test-driven-development) | Iron Law ("no production code without a failing test first"); Red-Green-Refactor cycle with verify-fails-correctly diamond; Good/Bad code framing | Generic single-runtime focus (this substrate ships dual-runtime by default) |
| [trailofbits/skills/property-based-testing](https://github.com/trailofbits/skills/tree/main/skills/property-based-testing) | Property-based testing for invariants when example tests miss the input space | Smart-contract-specific property patterns |
| [trailofbits/skills/testing-handbook-skills](https://github.com/trailofbits/skills/tree/main/skills/testing-handbook-skills) | Sanitizer hygiene mention; fuzzer routing for edge-case discovery | Most of the security-research framing |
| Anthropic [claude-cookbooks](https://github.com/anthropics/claude-cookbooks) testing patterns | TDD-with-LLM patterns: ask the agent to write the failing test FIRST, watch it fail, then implement | Vendor-specific eval patterns |
| Established practice (cross-team norms) | Regression-test-for-every-bug rule; test-isolation discipline; arrange-act-assert structure; one-assertion-per-test for clarity | n/a |

No source's content was forked verbatim. The patterns were extracted, merged, and re-expressed in caveman-form (terse + operationally useful).

## When to use

- User says `/tdd`, "write a test first", "red-green-refactor", "regression test for X"
- User says "I'm about to add a feature" or "I'm about to fix a bug" on any code path
- User reports a bug → answer with "let's write the failing test first" before any fix
- User pastes broken code with a stack trace → reproduce the failure in a test before fixing
- User asks to refactor → tests must exist (or be written) before any refactor

Do NOT use for:
- Throwaway prototypes (use `/prototype` instead)
- Generated code (skip TDD; verify the generation pipeline separately)
- Configuration files (no behavior to test)
- Pure documentation changes (no code path)
- Bash scripts under 30 lines (test discipline is heavy for one-shot scripts)

## The Iron Law

```
NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST
```

(Source: obra/superpowers/test-driven-development. Kept verbatim because the law works.)

If you wrote code before the test:
- Delete it. Start over.
- Do not keep it as "reference."
- Do not "adapt" it while writing tests.
- Do not look at it.

Implement fresh from tests. Period.

## Red-Green-Refactor cycle

```
   [RED]               [GREEN]            [REFACTOR]
   Write failing → Verify it fails → Minimal code → Verify all green → Clean up → Stay green → Next
   test           correctly         to pass        (no broken tests)   (no behavior  
                                                                       change)
```

(Diagram source: obra/superpowers. Verify-fail step is non-skippable.)

### RED: Write failing test

Write ONE minimal test showing the desired behavior. Specific, named after behavior not implementation, single assertion preferred.

<Good>
```typescript
test('retries failed operations 3 times', async () => {
  let attempts = 0;
  const operation = () => {
    attempts++;
    if (attempts < 3) throw new Error('transient');
    return 'success';
  };

  const result = await retryOperation(operation);

  expect(result).toBe('success');
  expect(attempts).toBe(3);
});
```
Clear name; tests behavior; one thing; named operation lets the test fail meaningfully.
</Good>

<Bad>
```typescript
test('retry works', async () => {
  const mock = jest.fn()
    .mockRejectedValueOnce(new Error())
    .mockRejectedValueOnce(new Error())
    .mockResolvedValueOnce('success');

  const result = await retryOperation(mock);
  expect(result).toBe('success');
});
```
Vague name; tests the mock plumbing not the retry behavior; brittle to implementation changes.
</Bad>

(Good/Bad framing source: obra/superpowers.)

### Verify the test fails CORRECTLY

This is the step every junior dev skips and every senior dev never skips.

Run the test. Confirm:
1. It fails (the production code does not yet implement the behavior)
2. The failure message is meaningful — not a syntax error, not a missing import, not a wrong fixture
3. The failure is for the RIGHT reason (the assertion failed because the behavior is missing, not because the test setup is broken)

If the test fails for the wrong reason, fix the test BEFORE writing implementation. A test that passes by accident hides regressions later.

### GREEN: Minimal code to pass

Write the smallest amount of production code that makes the test pass. Resist the urge to write more.

If you find yourself writing `if (x === 1) return 'a'; if (x === 2) return 'b';` — that is fine for now. The next test will force you to refactor.

### REFACTOR: Clean up, stay green

Rename variables. Extract functions. Inline temporaries. Move methods. After every change, run the test suite. ALL tests must stay green.

If a refactor breaks tests:
- Revert and try a smaller refactor.
- Or: the test was depending on implementation detail; rewrite the test to focus on behavior, then refactor.

## Dual-runtime examples (TypeScript + Python)

This substrate covers two runtimes by default because they cover most modern stacks: TypeScript on Next.js for frontend or full-stack apps, Python on FastAPI for backend services + scripts + agents.

### TypeScript / Vitest

```typescript
import { describe, expect, test } from 'vitest';
import { calculateInvoiceTotal } from './invoice';

describe('calculateInvoiceTotal', () => {
  test('sums line items with tax applied per line', () => {
    const items = [
      { description: 'service A', amount: 100, taxRate: 0.10 },
      { description: 'service B', amount: 200, taxRate: 0.07 },
    ];

    const total = calculateInvoiceTotal(items);

    expect(total).toBe(324); // 100*1.10 + 200*1.07
  });

  test('handles zero items', () => {
    expect(calculateInvoiceTotal([])).toBe(0);
  });

  test('throws on negative amount', () => {
    const items = [{ description: 'bad', amount: -50, taxRate: 0.10 }];
    expect(() => calculateInvoiceTotal(items)).toThrow(/negative amount/);
  });
});
```

Run: `pnpm test:unit` or `pnpm vitest --run path/to/test.ts`.

### Python / pytest

```python
import pytest
from billing.invoice import calculate_invoice_total, NegativeAmountError


def test_sums_line_items_with_per_line_tax():
    items = [
        {"description": "service A", "amount": 100, "tax_rate": 0.10},
        {"description": "service B", "amount": 200, "tax_rate": 0.07},
    ]

    total = calculate_invoice_total(items)

    assert total == 324  # 100*1.10 + 200*1.07


def test_handles_zero_items():
    assert calculate_invoice_total([]) == 0


def test_raises_on_negative_amount():
    items = [{"description": "bad", "amount": -50, "tax_rate": 0.10}]
    with pytest.raises(NegativeAmountError):
        calculate_invoice_total(items)
```

Run: `pytest tests/ -v` or `pytest tests/test_invoice.py::test_sums_line_items_with_per_line_tax -vv`.

(Dual-runtime convention: most modern small-team stacks ship at least one of TypeScript and Python; many ship both, so the substrate covers both by default.)

## Test naming convention

Pick ONE of these styles and stay consistent within a codebase. Both are acceptable:

1. **Behavior-named, sentence form**: `test('returns 503 when downstream is unhealthy')`
2. **Should-form**: `test('should return 503 when downstream is unhealthy')`

Avoid:
- Implementation-named: `test('calls fetch with correct headers')` — too brittle
- Vague: `test('error case')`, `test('happy path')` — opaque when it fails
- Method-mirror: `test('getUser')` — does not say what is expected

The test name appears in failure logs months later. Optimize for that future reader.

## Regression-test-for-every-bug

When a bug is reported:

1. Write a failing test that reproduces the bug.
2. Confirm it fails for the right reason (the bug, not test setup).
3. Then fix the bug.
4. The test goes green.
5. The regression test stays in the suite forever — the next change cannot reintroduce that bug without breaking this test.

This is non-negotiable. Codebases with shipped users accumulate regression suites that gate every future change against the bugs that already burned someone.

## Property-based testing (when example tests miss the input space)

For pure functions where the input space is too large to enumerate (parsers, validators, reducers, encoders, mathematical operations), add property-based tests on top of example-based tests.

```typescript
import { fc, test } from '@fast-check/vitest';

test.prop([fc.string(), fc.string()])(
  'concat length is sum of input lengths',
  (a, b) => {
    expect(concat(a, b).length).toBe(a.length + b.length);
  }
);
```

```python
from hypothesis import given, strategies as st

@given(st.text(), st.text())
def test_concat_length_is_sum(a: str, b: str):
    assert len(concat(a, b)) == len(a) + len(b)
```

Properties commonly worth testing: idempotency (`f(f(x)) == f(x)`), commutativity, associativity, identity (`f(x, identity) == x`), inverse (`decode(encode(x)) == x`), bounds (output is within an expected range).

(Property-based source: trailofbits/skills/property-based-testing. Adopted for the invariants angle.)

## Bilingual handling

If the codebase ships multilingual messages or test fixtures (e.g., a Spanish-language UI alongside English):

- Test names stay in English (CI logs are English; English test names search better)
- Test fixture data can be the local language (real local-language input is the right test)
- Assertions on local-language output are fine: `expect(reply).toContain('Hola')` is valid

Do NOT translate test names to a non-English language even when testing non-English behavior. The asymmetry (English names, mixed-language data) is intentional and CI-friendly.

## Test isolation

Each test must run independently:
- No shared mutable state between tests
- No order dependence (tests pass in any order)
- No reliance on a previous test's side effects
- No reliance on database state set up by another test (use fixtures or factory-boy patterns)

If a test depends on order, it is a fixture problem, not a test-running problem. Fix the fixture.

## TDD with LLM help

When pairing with an agent (Claude, Cursor, Copilot, etc.) for a feature:

1. Describe the feature.
2. Ask the agent to write the FAILING test first.
3. Watch it fail (verify the failure reason).
4. Ask the agent to implement. Watch it pass.
5. Refactor.

The trap: the agent will sometimes write the implementation first and the test second, then claim "the test passed." That is not TDD. Force the order: test first, fail observed, then implement.

If the agent presents "Option A vs Option B" test designs, that is menu-mode. The agent should PICK the most-important-first test and write it. Other test cases come in subsequent RED-GREEN-REFACTOR cycles.

## Test-design priority order

When designing the first test for a feature, pick the test that:
1. Catches the most likely failure mode FIRST
2. Runs fastest in the inner loop
3. Has the lowest fixture cost

Then write it. Other test cases come next.

## Speed of the inner loop

The inner loop is the time between save → test result. If it is over 5 seconds, fix the inner loop before doing more TDD:

- Vitest: use `--watch` mode; isolate slow tests with `.slow` annotation; ensure no shared state
- pytest: use `--lf` (last failed) during iteration; `pytest-xdist` for parallelization
- Both: avoid HTTP calls in unit tests; mock at the boundary

Slow tests get skipped by tired engineers. Fast tests get run by tired engineers. The bar is sub-1-second feedback per inner-loop test.

## Anti-patterns

| Anti-pattern | Why it is wrong | Fix |
|---|---|---|
| Write production code, then write the "test" that asserts what it does | Not TDD; tests what code does, not what it should do | Delete code; write the failing test first |
| One test that tests 5 things at once | When it fails, unclear which thing broke | Split into 5 named tests |
| Test that just calls the function and asserts it does not throw | Does not verify behavior | Assert the actual return value or side effect |
| Mock everything | Tests the mocks, not the code | Mock at the system boundary (HTTP, DB), not internal calls |
| Test passes because of a bug that mirrors the bug in implementation | Test and implementation share an error | Verify the failure-reason in RED step is meaningful |
| Coverage as the goal | High coverage with weak assertions is theater | Coverage is a side effect; assertion quality is the goal |

## Output format

When invoked, the skill responds:

```
## TDD plan: <feature or bug name>

### Failing test (RED)
<minimal test showing desired behavior; one assertion preferred>

### Expected failure
<what the failure should look like; verify before writing implementation>

### Implementation (GREEN)
<minimal code to pass; user can ask for the implementation if they want it written>

### Refactor candidates
<things to consider in REFACTOR step>

### Regression-test status
<is this gating a known bug? if yes, add `[regression-of: <id>]` annotation>
```

## Cross-references

- `/code-diagnose` — for bugs where reproduction is hard; does the reduce-minimize step BEFORE writing the failing test
- `/grill-build` — for fuzzy build scope; resolve scope before writing tests
- `/architecture-pass` — for refactors that change architecture (must have tests covering the surface first)

## The full eng-discipline cycle (cross-references)

TDD is one step in a four-step cycle. Each step has its own Iron Law and its own substrate or upstream skill. Use them together:

| Step | Iron Law | Substrate / source |
|---|---|---|
| 1. Design before code | NO IMPLEMENTATION ACTION UNTIL DESIGN APPROVED | `obra:brainstorming` (HARD-GATE: no code, no scaffold, no skill invocation until design is presented and user approves) |
| 2. Test before code | NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST | This skill (`tdd-substrate`) |
| 3. Root cause before fix | NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST | `obra:systematic-debugging` (random fixes waste time + create new bugs; symptom fixes are failure) |
| 4. Evidence before completion | NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE | `obra:verification-before-completion` (run the test in THIS message; do not claim "it passes" from prior memory) |

The four Iron Laws share a rhetorical pattern from obra/superpowers: **"Violating the letter of these rules is violating the spirit of these rules."** Each rule has loopholes a tired engineer will reach for; the rule's intent is the protection, not just the rule's words.

The cycle runs: brainstorming (no code yet) → TDD (one failing test) → if-bug-found → systematic-debugging → fix → verification-before-completion → claim done. Skip any step and the discipline collapses.

(Cycle source: obra/superpowers/skills/{brainstorming, test-driven-development, systematic-debugging, verification-before-completion}. v1 of this substrate cited only the TDD step — substantial gap. v2 maps the cycle.)

## Anti-pattern (shared with verification-before-completion)

| Anti-pattern (recap) | Fix |
|---|---|
| Claim "tests pass" without running them in this message | Run the verification command NOW; show output before claiming done |
| "It worked yesterday" / "I ran it earlier" | Stale evidence is no evidence; re-run |
| "CI is green" without checking the right CI run for the commit currently on disk | Pull the SHA in CI; match against `git rev-parse HEAD`; if mismatch, re-run |

## Source comparison (everything-comparison build, revised)

| Source | What got incorporated | What was left out |
|---|---|---|
| [obra/superpowers/skills/test-driven-development](https://github.com/obra/superpowers/tree/main/skills/test-driven-development) | Iron Law, Red-Green-Refactor cycle with verify-fail diamond, Good/Bad code framing | Generic single-runtime focus (this substrate ships dual-runtime) |
| **[obra/superpowers/skills/brainstorming](https://github.com/obra/superpowers/tree/main/skills/brainstorming) (newly cross-referenced)** | HARD-GATE design-first pattern; "too simple to need a design" anti-pattern; checklist-as-tasks pattern | Visual-companion sub-flow stays in upstream skill |
| **[obra/superpowers/skills/systematic-debugging](https://github.com/obra/superpowers/tree/main/skills/systematic-debugging) (newly cross-referenced)** | Iron Law for root-cause investigation; "symptom fixes are failure" framing | Phase-by-phase debug loop stays in upstream skill |
| **[obra/superpowers/skills/verification-before-completion](https://github.com/obra/superpowers/tree/main/skills/verification-before-completion) (newly cross-referenced)** | Iron Law for fresh verification; "evidence before claims" framing; gate-function pattern | Specific verify-command catalog stays in upstream skill |
| [trailofbits/skills/property-based-testing](https://github.com/trailofbits/skills/tree/main/skills/property-based-testing) | Property-based testing for invariants; hypothesis pattern | Smart-contract-specific properties |
| [trailofbits/skills/testing-handbook-skills](https://github.com/trailofbits/skills/tree/main/skills/testing-handbook-skills) | Sanitizer hygiene mention; fuzzer routing | Most security-research framing |
| Anthropic [claude-cookbooks](https://github.com/anthropics/claude-cookbooks) testing patterns | TDD-with-LLM patterns | Vendor-specific eval patterns |
| Established practice (cross-team norms) | Regression-test-for-every-bug rule, test-isolation discipline, arrange-act-assert structure, one-assertion-per-test | n/a |

**Audit gap closed 2026-05-10.** v1 cited only 1 of 4 obra eng-discipline skills (TDD). v2 cross-references the full cycle (brainstorming, systematic-debugging, verification-before-completion). The discipline is the cycle, not just TDD in isolation.

## Source attribution

Source-comparison build per the repo-evaluation runbook "build with everything-comparison" rule. No source's content was forked verbatim; the patterns were extracted, merged, and re-expressed in caveman-form. Where obra owns specific framings ("Iron Law", "Violating the letter is violating the spirit", "verify-fail diamond"), those frames are credited inline.
