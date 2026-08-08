# ESP-IDF's `REQUIRES` cannot be conditioned on a `CONFIG_*` Kconfig symbol — it silently does nothing — 2026-08-08

## Symptom

A component's `CMakeLists.txt` had an unconditional `idf_component_register(REQUIRES ... some_bsp
...)` even though only one Kconfig-gated source file in the component actually used that BSP. The
fix looked obvious and safe: wrap the BSP entry in the same `if(CONFIG_IOTTA_DIAG_WEB)` block that
already gated the source file and its embedded assets, mirroring an existing pattern in the same
file. It built clean on the one board that was tested, was committed, and was wrong — a later
build (a different board, same config combination) failed with a `fatal error: bsp_....h: No such
file or directory`, even though `sdkconfig` clearly showed the guarding `CONFIG_*` symbol set to
the value that should have included the requirement.

## What actually happened

ESP-IDF computes each component's `REQUIRES`/`PRIV_REQUIRES` in an **early expansion pass**
(`__component_get_requirements` in `build.cmake`) that re-executes every component's
`CMakeLists.txt` in a **separate, minimal `cmake -P` subprocess** — before Kconfig is generated or
imported. That subprocess only receives build-level properties, never `CONFIG_*` symbols. So
`if(CONFIG_X)` guarding a `list(APPEND ... REQUIRES)` line always evaluates false during
requirements computation, regardless of the real config value — the REQUIRES list that actually
gets locked into the dependency graph never contains the conditional entry.

The *later*, real registration pass (with Kconfig loaded) correctly evaluates the same
`if(CONFIG_X)` for `SRCS`/`EMBED_FILES` — those are read live at real-registration time, not
cached from the early pass — which is why the gated source file still compiled in with the right
`CONFIG_*` value, just without the include path/library it needed. The two lists inside the same
`if()` block obey completely different evaluation timing, and nothing in the build output says so;
the component resolves, the wrong file compiles, and the failure looks like a normal missing-header
error with no clue that Kconfig gating was ever attempted or silently dropped.

## The rule

**In an ESP-IDF `CMakeLists.txt`, `REQUIRES`/`PRIV_REQUIRES` cannot be conditioned on a `CONFIG_*`
symbol — full stop, regardless of how the conditional is written.** `SRCS`, `EMBED_FILES`, and any
other property read during the real registration pass CAN be gated this way. If a dependency is
genuinely only needed by Kconfig-gated code, either (a) leave it in `REQUIRES` unconditionally and
accept the coupling (dead code, not a dead build, when the config is off — the linked-in library is
harmless if nothing calls it), or (b) split the gated code into its own component with its own
`CMakeLists.txt`, so the whole component (and its REQUIRES) is what's conditionally included via
`EXTRA_COMPONENT_DIRS`/dependency-manager mechanisms, not a symbol inside one file.

## Why it generalises

Any build system with a two-phase "compute the dependency graph, then configure/generate" flow has
this same trap available, and the trap is specifically dangerous because **half of the file's
own conditional gating works and half silently doesn't**, inside the very same `if()` block. A
reviewer (human or agent) reading the CMakeLists sees one pattern applied consistently and has no
local signal that one branch of it is evaluated in a context with no visibility into the condition.
Before trusting a "gate this dependency behind a config flag" fix in any CMake-based (or similarly
staged) build, check whether the property you're gating is resolved in the same pass as the
condition you're gating it with — and if you can't tell, build both the on and off configurations
and read the component's own dependency-resolution log (ESP-IDF's `project_description.json`, or
the equivalent artifact in another build system) rather than trusting that the build succeeding
once means the gate took effect.
