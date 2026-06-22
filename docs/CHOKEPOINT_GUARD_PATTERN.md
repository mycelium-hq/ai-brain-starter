# The chokepoint-guard pattern: classify, fail-closed page, dedup-on-delivery, backstop

When a system captures something durable (a user emits content that lands on
disk or in a store and is read back later), a policy violation in that content
is worth catching **at the moment of capture**, not only on a downstream sweep.
Catching it later leaves a window where the violation is live and nobody knows.

This document describes a reusable pattern for guarding a single capture
chokepoint with a synchronous detector that can never break the thing it
guards. It is **pattern-not-mechanic**: the shape ports to any runtime; the
specific channels and criteria are yours to fill in.

## The bug classes it prevents

- **`SILENT-NO-OP-ON-UNEVALUABLE-SPEC`.** A detector that is handed a rule it
  cannot evaluate and quietly does nothing. No error, looks healthy, catches
  nothing.
- **`GUARD-RECORDS-DEDUP-ON-ATTEMPT-NOT-DELIVERY`.** A detector that marks an
  incident "already handled" the moment it *tries* to alert, so when every
  alert channel silently fails, a backstop that shares the dedup state skips it
  and the incident goes unhandled forever.
- **`GUARD-FAILS-THE-THING-IT-GUARDS`.** An alert path that raises and takes the
  capture down with it. The guard becomes a new way to lose user writes.

## The shape

```
capture chokepoint (one place, after the durable write succeeds)
  -> classify(event_props, criteria_registry) -> verdict     # pure, synchronous
  -> maybe_page(verdict, page_fn, dedup_store) -> result      # fail-closed
       -> dedup-on-delivery: record ONLY if >=1 channel delivered
  -> a backstop poller shares the SAME dedup store and re-finds
     anything that blackholed
```

Five properties make it safe.

### 1. One chokepoint, not many

Find the single function every durable write of a given kind passes through and
guard *that*. One proven chokepoint beats five aspirational ones. Wire the hook
to fire **after** the write and its audit/log succeed, so a guard failure can
never prevent a write that already landed.

### 2. A pure classifier

```python
def classify(event_props, criteria_registry) -> Verdict:
    """Map props -> verdict. No I/O, no clock, no globals. Deterministic."""
```

Purity means you can unit-test every criterion in isolation, and the same input
always yields the same verdict. The classifier decides *what matched*; it does
not page, log, or touch a network.

### 3. Criteria are DATA, and absence is dormant, never a silent no-op

Express each criterion as data (a small record), composed into a registry that
can be scoped per-tenant or per-event-type. Two failure modes to design against
explicitly:

- **Dormant-tolerance.** A criterion keyed on a field the schema does not emit
  *yet* must be **skipped** (the absent field is not a violation), not
  mis-fired. Make this explicit in the criterion (e.g. a `dormant_if_absent`
  list), so a future schema can light the criterion up by simply starting to
  emit the field.
- **Fail-loud on the unevaluable.** If the registry is a shape the classifier
  cannot evaluate, **report it** in the verdict's reason. Never accept a spec
  you cannot run and then quietly do nothing. That is the worst failure,
  because it looks healthy.

```python
@dataclass(frozen=True)
class Criterion:
    name: str
    severity: int
    requires_true: tuple[str, ...] = ()        # these props must be exactly True
    requires_not_true: tuple[str, ...] = ()    # present-and-not-True
    dormant_if_absent: tuple[str, ...] = ()    # absent => skip this criterion
```

### 4. Fail-closed paging

```python
def maybe_page(verdict, *, page_fn, targets, dedup_store, ...) -> Result:
    """NEVER raises into the caller. A page failure is logged to a
    scoped failure sink; the capture still succeeds."""
```

`maybe_page` is wrapped in an absolute try/except, and each channel attempt is
wrapped too, so one bad channel cannot stop the others and no failure escapes to
the caller. A failed alert is logged to a **scoped failure sink** (your audit
log, keyed to the tenant/user). Never dropped, never surfaced as a 500 on the
write.

The page channel is injected (`page_fn`), so tests never touch a network and a
new channel is a drop-in. A good universal default is an **incoming-webhook
POST** (a `{"text": ...}` JSON body) to a per-tenant URL configured in your
tenant config: every incident stack (Slack, Discord, PagerDuty, a custom
endpoint) accepts one. Validate any user-supplied webhook URL against SSRF (scheme
allowlist, no embedded credentials, public-IP assertion) both when it is set and
again at send time (a DNS-rebind defense).

### 5. Dedup-on-delivery + a backstop poller

This is the subtle one. Record a deduplication key **only if at least one
channel actually delivered**:

```python
delivered = any(channel_results.values())
if delivered and dedup_key:
    dedup_store.mark(dedup_key)
# else: leave the store UNTOUCHED, so a backstop re-finds this incident
```

If you record on *attempt*, an incident whose every channel blackholed gets
marked "done", and a backstop poller that shares the dedup store skips it
forever. Recording on *delivery* means a fully-failed page is left un-deduped,
so the backstop re-finds and re-pages it. The backstop poller reads the durable
sink, runs the same classifier, and shares the same dedup store, so a delivered
incident is suppressed and a blackholed one is recovered.

(A reasonable refinement: let the highest-severity verdicts bypass dedup
entirely, since a separate durable emit of the same high-severity asset is a
separate violation worth re-alerting.)

## Why synchronous-at-capture beats poller-only

A downstream poller alone leaves a live-violation window and gives no
synchronous signal at the moment of emit. The poller is a **complement**, the
backstop that recovers blackholed pages, not a replacement for catching the
violation as it happens.

## Checklist to port it

1. Pick the one capture chokepoint. Fire the hook after the write + audit
   succeed.
2. Write a pure `classify` that reads event props against a data-driven
   criteria registry. Make absence dormant; make an unevaluable registry
   fail-loud.
3. Add an optional per-tenant alert target (a webhook URL is a good default).
   Absent => log-only. SSRF-validate it at set time and send time.
4. Make `maybe_page` fail-closed: never raise into the caller; log failures to a
   scoped sink.
5. Dedup-on-delivery: record only when a channel delivered.
6. Add a backstop poller that shares the dedup store and re-runs the classifier
   over the durable sink.
7. Test every case: exempt/clean (no page), each criterion (pages), absent-field
   (dormant), channel-raises (fail-closed), dedup (pages once),
   all-channels-failed (does NOT dedup), partial-failure (still dedups).
