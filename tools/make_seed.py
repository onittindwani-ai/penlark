#!/usr/bin/env python3
"""Generate the fictional performance seed: 60 posts with numbers, tracked links with clicks and leads, two experiments, and the answer key.

Everything is fictional. Effects are planted by construction: a question opener raises the engagement rate by 40 percent, a number in the first line by 30 percent,
and a long post lowers it by 35 percent. Three posts use an emoji and, by planted luck, did very well: that is the false lead a careful learning loop must not report.
Run: python3 tools/make_seed.py   (deterministic: the same files every time)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "data" / "seed"
OPEN_Q = ["How soon should you invoice after the work is done?", "Why do clients ignore the first reminder?", "What do you say when a payment is two weeks late?", "Is it rude to send the bill on the same day?", "Who decides when a project is finished?", "What does a good invoice email look like?", "Do you chase late payers or let it go?"]
OPEN_S = ["Late payments are a communication problem.", "Most invoices are sent too late.", "A polite reminder is not rude.", "Clients pay people they trust.", "The invoice is part of the service.", "Chasing money is a skill.", "Slow payers rarely change."]
OPEN_N = ["I sent 9 reminders last quarter.", "One invoice took 41 days to get paid.", "Three clients paid within a day.", "A reminder after 7 days works for most people.", "I timed 12 invoices this month.", "Two sentences fixed my late payments."]
BODY = ["The fix is boring. Write the same short email each time.", "Say what the work was, what it cost, and when it is due.", "Keep the tone friendly and the dates exact.", "Clients rarely mind a clear request.", "They mind a vague one that sounds like blame.", "I used to wait and hope. Hope is not a process.", "A template saves the awkward rewrite.", "Put the due date in the first line.", "Thank them in the last line.", "Then stop thinking about it.", "Small habits beat big plans here.", "The money arrives faster when the ask is plain."]
EXTRA = ["I keep a folder of every reminder I have sent.", "Reading old ones shows what actually worked.", "The ones with a date got answers within days.", "The ones with an apology got silence.", "None of this needs software, though software helps.", "It needs a habit and a clear first line."]
NUMBER_LINE = ["It took me about 2 hours a month to chase money.", "A 5 line email beats a 20 line one.", "Most replies come in under 3 days."]


def make_posts(rng: random.Random) -> tuple[list[dict], dict]:
    posts, emoji_ids = [], []
    for i in range(60):
        q = rng.random() < 0.34
        n = (not q) and rng.random() < 0.45
        long = rng.random() < 0.3
        opener = rng.choice(OPEN_N if n and not q else OPEN_Q if q else OPEN_S)
        paras = [opener]
        body = rng.sample(BODY, 3)
        if long:
            body += rng.sample(EXTRA, 6) + rng.sample(BODY, 6) + rng.sample(EXTRA, 4)
        for k in range(0, len(body), 2 if rng.random() < 0.5 else 3):
            paras.append(" ".join(body[k:k + 3]))
        if rng.random() < 0.3:
            paras.append(rng.choice(NUMBER_LINE))
        if rng.random() < 0.4:
            paras.append("What do you do when it is late?")
        text = "\n\n".join(paras)
        base = 0.035 * rng.lognormvariate(0, 0.15)
        if q and text.split("\n")[0].endswith("?"):
            base *= 1.4
        if text.split("\n")[0][:60] and any(ch.isdigit() for ch in text.split("\n")[0]):
            base *= 1.3
        if len(text.split()) > 150:
            base *= 0.65
        post = {"post_ref": f"post-{i + 1:02d}", "platform": rng.choice(["linkedin", "linkedin", "x"]), "posted_on": f"2026-{8 + i // 22:02d}-{(i % 22) + 1:02d}", "impressions": rng.randint(2200, 9000), "text": text}
        posts.append((post, base))
    for idx in rng.sample(range(60), 3):  # the false lead: three emoji posts that did very well by luck
        post, base = posts[idx]
        post["text"] = post["text"].rstrip() + " \U0001F680"
        posts[idx] = (post, 0.035 * 3.2)
        emoji_ids.append(post["post_ref"])
    out = []
    for post, base in posts:
        eng = max(1, round(base * post["impressions"]))
        post.update({"likes": round(eng * 0.74), "comments": round(eng * 0.16), "shares": eng - round(eng * 0.74) - round(eng * 0.16), "clicks": round(post["impressions"] * rng.uniform(0.004, 0.02))})
        out.append(post)
    return out, {"emoji_posts": emoji_ids}


def make_links(rng: random.Random, posts: list[dict]) -> dict:
    links, clicks, conv = [], [], []
    picks = rng.sample(posts, 10)
    for n, p in enumerate(picks, start=1):
        hot = n in (2, 5)
        links.append({"id": n, "code": f"seed{n:03d}", "post_ref": p["post_ref"], "target": "https://larkspur.example.test/start", "source": p["platform"], "medium": "social", "campaign": "invoice-timing"})
        k = rng.randint(30, 70) if hot else rng.randint(6, 30)
        for c in range(k):
            clicks.append({"link_id": n, "visitor": f"v{n}-{rng.randint(1, max(3, k - 4))}", "day": rng.randint(0, 9)})
        leads = round(k * (0.18 if hot else 0.05)) or 1
        for l in range(leads):
            conv.append({"link_id": n, "lead_ref": f"lead-{n:02d}-{l + 1}", "kind": "lead", "value": 0})
            if rng.random() < (0.35 if hot else 0.12):
                conv.append({"link_id": n, "lead_ref": f"lead-{n:02d}-{l + 1}", "kind": "customer", "value": rng.choice([4900, 9900, 14900])})
    return {"links": links, "clicks": clicks, "conversions": conv}


def main() -> None:
    rng = random.Random(20261123)
    posts, key = make_posts(rng)
    (SEED / "posts.json").write_text(json.dumps(posts, indent=1) + "\n")
    (SEED / "links.json").write_text(json.dumps(make_links(rng, posts), indent=1) + "\n")
    (SEED / "experiments.json").write_text(json.dumps([
        {"name": "Question opener against statement opener", "metric": "link clicks", "a_label": "Statement", "a_n": 1800, "a_hits": 54, "b_label": "Question", "b_n": 1750, "b_hits": 89},
        {"name": "Short post against long post", "metric": "link clicks", "a_label": "Short", "a_n": 60, "a_hits": 2, "b_label": "Long", "b_n": 55, "b_hits": 5}], indent=1) + "\n")
    (SEED / "authors.json").write_text(json.dumps([
        {"slug": "tobias", "name": "Tobias Rennick (fictional)", "about": "A terse founder of Larkspur, a small invoicing tool for freelancers. Fictional."},
        {"slug": "imani", "name": "Imani Castellan (fictional)", "about": "A warm teacher who writes about learning. Fictional."},
        {"slug": "gareth", "name": "Gareth Whitlow (fictional)", "about": "A formal management consultant. Fictional."}], indent=1) + "\n")
    key.update({"posts": len(posts), "planted_real_effects": {"opens_with_question": "+40 percent engagement rate", "number_in_first_line": "+30 percent", "long_post_over_150_words": "-35 percent"},
                "planted_false_lead": "uses_emoji: only 3 posts, rate set 3.2 times the base by luck; the learning loop must report too few, never a pattern",
                "hot_links": ["seed002", "seed005"], "experiments": {"Question opener against statement opener": "difference", "Short post against long post": "too_small"}})
    (SEED / "answer_key.json").write_text(json.dumps(key, indent=1) + "\n")
    print("OK wrote", len(posts), "posts")


if __name__ == "__main__":
    main()
