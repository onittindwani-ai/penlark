# Design notes

Written before any CSS of Penlark, as the quality gates ask. Everything here is original to this repo.

## What Penlark feels like
A quiet writing desk. The person is writing and the page answers back as they type: how close this sounds to them, which sentence drifts, which house rule is broken. Nothing shouts. The accent is plum, a muted red violet that reads as "ink" and stays clear of the true red used for real alarms (a banned phrase, a claim with no source, the kill switch).

## Palette (60, 30, 10)
60 percent warm neutrals from the kit (cream, oat). 30 percent coffee ink and borders. 10 percent plum for the one action on a screen, the live meter ring, the radar fill of the own voice and the active navigation row. The overlay in the radar (a draft or another sample) uses the coffee ink line so two shapes never fight for the same colour. Matches follow meaning: 80 and above is the plum family with a "close" label, 60 to 79 is amber, under 60 is the danger tone. Contrast is checked by the kit test and by axe in both themes.

## Type and spacing
Geist for the interface and numbers, Instrument Serif for page titles and the big match number. The editor uses the interface font at 16 px with a 65 character measure. Spacing 8, 13, 21, 34, 55, 89. The Studio splits 61.8 to 38.2: the page on the left, the meter and checks on the right. On a phone the meter moves below the editor, because the page itself must stay first.

## Signature 1: the live voice match meter
The Studio scores the text as you type (a short debounce, then one call to the match endpoint that writes nothing). A ring gauge shows the number, a row of bars shows each style dimension, and the sentences that pull the score down are underlined softly inside the editor, with a number beside them that says how many points they cost. Under 25 words the meter says the number is rough. Banned phrases and dashes are underlined in the danger tone, claims with no source in amber. A variant can be compared with the draft word by word.

## Signature 2: the voice fingerprint radar
A radar of 14 style dimensions. The person's own voice is the filled shape. A draft or another sample can be laid over it as a line. Clicking an axis shows what it means in plain words and two real sentences from the samples that show it. The radar is drawn as plain SVG with a text alternative (a table) for screen readers.

## Micro interactions (from the shared catalogue)
Every button presses, shows a spinner and then a tick. The meter ring draws in once and eases after that. Numbers count up. Bars grow. Dragging a post on the calendar lifts it, opens a gap, settles on drop, and a toast offers Undo. Drag has a keyboard route: a move button with a date field. Approve and reject show toasts. Skeletons match the final layout. Empty states always name the next step. Errors say what happened and how to fix it. Copy buttons turn into a tick.

## Motion
Tokens from the kit: out easing for entrances, press 120 to 160 ms, popovers 180 to 240 ms, sheets 240 to 320 ms, charts 600 to 800 ms once. Only transform and opacity animate. Reduced motion keeps fades and removes movement.

## What is not in the base and is built here
Highlight editor (a transparent textarea over a mirrored text layer), match meter, radar chart, word diff, calendar grid with drag and drop, funnel bars, trait cards with a sample size bar. Each is a small component in `apps/web/src/components`.
