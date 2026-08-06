# A handler named after a browser global can silently no-op inside `onclick="..."`

## Symptom

A "select all" checkbox in a web GUI did nothing when clicked. No console error, no failed
network request — the header checkbox toggled its own visual state, but no row checkbox ever
changed. Calling the same JavaScript function directly from the browser console worked perfectly.
That inconsistency — works from console, silently fails from a real click — was the only clue.

## What actually happened

The handler was named `all` and wired via an inline HTML attribute: `onclick="all(this)"`. Inline
event-handler content attributes do not execute in the page's normal global scope. Per the HTML
spec, they run inside an implicit `with (document) { with (form) { with (element) { ... } } }`
scope chain (Annex B legacy compatibility). `document.all` is a real DOM property — the legacy
`HTMLAllCollection`, still supported in every modern browser, and spec'd as an "exotic" object
(`[[IsHTMLDDA]]`) that is silently *callable* (returns `undefined`, no error) rather than throwing
when invoked as a function, precisely so old feature-sniffing code (`if (document.all) {...}`)
wouldn't crash.

So `all(this)` inside the `onclick` attribute resolved the identifier `all` to `document.all`
before it ever reached the page's own `window.all` function — because `document` sits earlier in
the inline handler's scope chain than the global object does. The call silently succeeded (no
throw, no return value anyone checked) and did nothing. Calling the exact same function from the
console worked because the console evaluates in normal global scope, where `all` correctly
resolves to the intended function — which is exactly why this shipped unnoticed: the "obvious"
verification (open devtools, call the function) passes.

## The rule

**Never name a function called from an inline event-handler attribute after a browser or DOM
global.** The known-dangerous set inside that inline scope chain includes at minimum: `all`
(`document.all`), `open` (`window.open`), `top`, `name`, `status`, `location`, `frames`, `length`,
`event`, `self`, `parent`. Any of these, used as a handler function name and invoked via
`onclick="foo(...)"` / `onchange="foo(...)"` / etc., risks being shadowed by the DOM property of
the same name — sometimes with a hard error, sometimes (as with `document.all`) with total,
silent non-execution.

Two defenses, either is sufficient, prefer both:

1. **Don't use inline event-handler attributes at all.** Wire handlers via
   `element.addEventListener(...)` in a real `<script>` block instead. This sidesteps the whole
   scope-chain quirk — `addEventListener` callbacks run in normal scope. Most codebases that avoid
   inline handlers for CSP reasons (`script-src` without `'unsafe-inline'`) get this for free.
2. **If you must use inline attributes**, never name the handler after anything that could
   plausibly be a DOM/BOM property. When in doubt, check: does `typeof document.<name>` or
   `typeof window.<name>` report anything other than `"undefined"` for a name that *shouldn't*
   exist? (`document.all`'s `typeof` reports `"undefined"` even though it's real — the exotic-object
   quirk defeats even that naive check. `Object.prototype.hasOwnProperty` or a direct reference
   check is more reliable than `typeof` for this specific property.)

## Why it generalizes

This is not a one-off bug in one codebase — `document.all` is old enough and forgiving enough
(no throw, no crash) that any project still using inline event-handler attributes is exposed to
it, and the failure mode (silent no-op, works fine from the console) is specifically the shape
that survives manual testing. Any agent asked to debug "this button does nothing" in an
inline-handler-heavy codebase should check the handler's name against the DOM/BOM global list
before looking anywhere else — it costs one grep and rules out an entire, non-obvious class of
bug that a stack trace will never surface.
