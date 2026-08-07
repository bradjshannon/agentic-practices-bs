# Checking that markup rendered correctly is not checking that it works

## Symptom

An agent converted a web UI control (a server-picker) from one widget type to another, then
verified the change by loading the page in a browser automation tool and inspecting the DOM: the
new element existed, had the right tag, the right number of options, the right values. Called it
verified and shipped it.

The control's core interaction — selecting an option and having the page navigate — was silently
broken. The script wiring the navigation ran before the element it queried existed in the DOM, so
`document.getElementById(...)` returned `null` and the event listener never attached. Nothing in
the DOM-structure check would ever have caught this: the markup was completely correct. Only
clicking through it revealed the control did nothing.

## What actually happened

"I inspected the rendered HTML and it looks right" and "I clicked the control and the expected
thing happened" are different claims, and only the second one is a claim about *behavior*. A
script-ordering bug, a listener that silently fails to attach, an event that doesn't bubble the
way assumed, a handler that throws and gets swallowed — none of these leave any trace in static
DOM structure. The element is there. Its attributes are correct. It simply doesn't do anything
when interacted with.

The verification that was actually run (read the DOM, confirm shape) answered a real, useful
question — but it was the wrong question for the claim being made ("the dropdown works").

## The rule

**For any claim about interactive behavior (a click navigates, a change fires a handler, a submit
posts data), the only valid verification is triggering the real interaction and observing the
real effect — not inspecting the markup that is supposed to produce it.**

Concretely:

- Don't stop at "the element exists with the right attributes." Dispatch the actual event (a real
  click, or a synthetic `dispatchEvent(new Event('change', {bubbles: true}))` on the element) and
  check what happened as a *result* — a URL changed, a network request fired, a DOM mutation
  occurred elsewhere, state updated.
- If the effect is a navigation, the strongest possible proof is watching the navigation actually
  happen (even to a real destination, if that's safe to do) — reading back
  `window.location.href` synchronously immediately after dispatch can race the navigation and
  read stale; letting it actually navigate and observing the resulting page/origin is unambiguous.
- If DOM structure is genuinely all you can check (e.g., in a static-render-only test harness with
  no JS execution), say so explicitly in the verification claim — "markup renders correctly" is a
  narrower and different claim than "the control works," and conflating them is exactly how this
  class of bug survives review.

## Why it generalizes

Any agent verifying UI changes via a browser-automation or DOM-inspection tool is exposed to this
gap by default, because inspecting rendered markup is the cheap, obvious first check and it is
very easy to mistake "I looked at the output and it seemed right" for "I confirmed the behavior."
The fix costs one extra step (fire the interaction) and closes an entire class of ordering/timing/
attachment bugs that structural inspection cannot see by construction.
