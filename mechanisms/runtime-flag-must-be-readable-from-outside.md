# A runtime flag an A/B needs must be readable from outside the process

**Class:** design constraint, not enforcement. Nothing detects the mistake; the code looks correct.

## What it is

An experiment that alternates between two arms of one deployed system needs a switch the
experimenter can flip **while the system runs**. The obvious implementation — an environment
variable, read fresh on every call — looks like it satisfies that. It does not.

A process's environment is fixed at exec. Reading `os.environ` per call makes the value changeable
by *the process itself*, not by anyone outside it. To change it from outside you restart, and a
restart clears caches, re-resolves providers and re-reads config — so the arm switch is confounded
with the restart, which is the exact confound the design was built to avoid.

I shipped this, having written a comment in the same file explaining why the value must not be
latched at import. The reasoning was right and the mechanism did not implement it.

## The shape that works

A **file** on a path the process can see, checked per call:

```python
def is_enabled() -> bool:
    raw = os.environ.get("FEATURE_X")
    if raw is not None:                 # explicit setting wins, in EITHER direction
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    try:
        return os.path.isfile(FLAG_FILE)
    except Exception:                   # unreadable is not a reason to enable anything
        return False
```

Flipping an arm becomes `touch` and `rm`. Nothing else about the system changes.

Three properties worth copying:

- **The explicit variable wins in both directions**, so a deliberate `FEATURE_X=0` cannot be
  overridden by a flag file somebody forgot to delete.
- **Every unexpected condition reads as off** — unrecognised value, unreadable path, a directory
  where a file was expected. Ask which way the failure hurts: here the flag gated a path that
  dispatches commands to a hot appliance, so there is no case where guessing "on" is safe.
- **The flag path must be inside a mount the deployment already has**, or the switch requires a
  deploy and you are back where you started.

## What it cannot detect

Nothing here catches the original error. A env-var-only flag passes every unit test, reads correctly
per call, and looks right in review. The only thing that surfaced it was **checking the deployed
system**: the code was live in the container and the variable was `NOT_SET`, which made it concrete
that the only route to the other arm was a restart.

Generalises to: kill switches, sampling rates, canary percentages, log levels — anything an operator
must change on a running system without perturbing it.
