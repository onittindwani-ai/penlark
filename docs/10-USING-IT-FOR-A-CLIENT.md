# Using it for a client

One copy of Penlark serves one person or one client. Never mix two clients' writing, notes or logins in one database. A voice profile belongs to the owner of the writing it was built from.

## What you are selling

Setup, a trial period in draft mode, and a monthly review of the voice profile, the house rules and the learning loop. You are selling a writing desk that drafts in the client's own voice, checks every draft against their rules and their sources, and never publishes anything without a second person's approval. You are not selling a promise of reach, followers or sales, and not a ghost writer that invents stories. Say that plainly.

## What to charge for

This guide gives no price figures. It gives the shape of the offer, so you can price it yourself after looking at your market and your costs.

- **Setup, once.** The business basics check (`02`), a fresh copy for the client, collecting 15 or more pieces of writing they own, building the voice profile with them in the room, agreeing the house rules and the posting rhythm, connecting the scheduler tool they already use, and a trial period in draft mode. Charge for the hours and the care, not for the software, which is free.
- **Running it, monthly.** A short review of the drafts that were edited most, the ideas that came from real calls and comments, the learning loop (what the best posts had in common, with the sample sizes), the banned phrase list and the approvals that waited too long. State plainly how many hours a month that includes.
- **Source material, separately.** Good drafts need real examples, numbers and stories. Recording calls, writing case notes and collecting client comments is real work for the client's team or for you, priced on its own.
- **Costs that pass through, at cost.** Hosting, the scheduler tool's own fees and any model usage. Show these as the client's own accounts, not as your markup.
- **Never charge for** a promised engagement, a promised number of leads or a promised follower count. The learning loop describes past posts and does not show cause. Never present the demo numbers as a result: the demo authors are fictional.

## Onboarding checklist

1. Run `02-BUSINESS-BASICS-CHECK.md` with the client: who owns the writing, permission to store it, who is quoted in the notes, and who approves.
2. Make a fresh copy for this client with `DEMO_MODE=false`, their owner address in `OWNER_EMAIL`, a second person in `APPROVER_EMAIL` and their own `SESSION_SECRET`. Nothing can be approved without a second person, because the one who asks cannot approve.
3. Add the client as a voice (Add a voice in the app, or `.venv/bin/python -m penlark.admin add-voice "Name"`). Ask for writing they own: 15 or more posts, emails or talk transcripts. A LinkedIn or X export works. Do not load another person's posts to copy their voice.
4. Build the voice profile, read the guide together, edit it and lock it. The guide is theirs to change.
5. Check the house rules together. The shipped defaults are a starting point: dashes banned in marketing text (`NO_DASHES=false` for a client whose style uses them), reading level grade 9 or lower, a voice match of at least 60 to go to approval, and facts that need a source. The built in banned phrase list stays on, and each phrase can be turned off. Add the phrases and claims this client never uses, and keep what they agree to in writing.
6. Agree the posting rhythm. The default is two posts a week on LinkedIn and two on X (`CADENCE=linkedin:2,x:2`). It shows on the Calendar as a plan and never blocks anything. Set the platforms and counts the client will really keep.
7. Set `REDIRECT_ALLOW_HOSTS` to the client's own site and booking page. A tracked link to any other host is refused.
8. Load a week of real calls, comments and emails as notes. Walk through the first ideas and their verified quotes.
9. Connect the scheduler tool they already use (`03`, `04`), or stay on file export. Start in draft mode and run for at least a week. Compare the drafts with what they would have written and note what to change.
10. Write 5 or more fresh texts of their own that were not used to build the profile and paste each one into the Studio. Show the client the match numbers on their own writing, including the texts that score low and why.
11. Follow `09-GO-LIVE-CHECKLIST.md`.

## Handover

- Give the client their own owner and approver sign ins, and a read only sign in (`VIEWER_EMAIL`) for someone who only needs to look, such as an assistant or an accountant. Remove yours.
- Hand over the backup steps in `11` and the name of the person who updates the app (`12`).
- Hand over the secrets inside the client's own hosting and scheduler accounts, never by chat or email.
- Remove all demo data, then check the voice profile, the house rules and the calendar belong to this client only.
- Show them the kill switch and the audit log check, and the written approval rule: who approves, and what they check first.
- Agree who answers when a post goes out that should not have. It will happen once.

## What to put in the client contract

Plain wording, checked by your own lawyer: what is included in setup and in the monthly work; that the client owns their writing, the notes, the drafts, the data and the accounts; that third party accounts and their costs belong to the client; that the client gave permission to use their writing and anyone quoted in the notes; that the app drafts and a named person approves every post, with no promised results; that posting to each network is done through the client's own scheduler account under that network's rules; that no claim without a source is published; how long the notes and drafts are kept and who can read them; who answers if a post goes wrong, and how fast; how either side ends the work and what happens to the data afterwards. This is not legal advice.

## Keep it honest

The demo draft writer is a template stand in that leaves brackets where a real example is needed, not a language model. The voice match is a set of measured style numbers, not a judge of quality. The learning loop describes past posts with sample sizes and does not show cause. Attribution links show clicks, not why someone clicked.

## The weekly routine

For whoever runs the desk each week:

- **Ideas:** open the inbox, keep the ones with a real quote and a source, drop the rest.
- **Studio:** read the match meter and the underlined sentences before the words. A claim with no source stays flagged until it has one.
- **Approvals:** the second person checks the draft, the sources and the links, then decides. You cannot approve your own request.
- **Calendar:** check the week against the rhythm. A short week is a nudge, not an error.
- **Performance and learning:** read it as hints. Small samples say "too few to say".
- **Audit log:** every action with who did it, kept in order. Press Check the chain to see whether history was changed.

The shared daily and weekly checks are in `11-OPERATING-AND-BACKUPS.md`.
