#!/usr/bin/env python3
"""Unit-economics model for credits, free allowances and AI edit metering.

Every input is an assumption taken from docs/ENGINE.md (estimates, NOT measured on real traffic). Change the Params or
pass --json to feed the numbers into server config. Re-run after measuring real `cost_usd` values from the videos table.

  python scripts/pricing_model.py            # markdown report
"""
import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple


@dataclass
class Params:
    # planning LLM (Sonnet-class list price per 1M tokens)
    llm_in_per_m: float = 3.0
    llm_out_per_m: float = 15.0
    plan_in_tokens: int = 5000            # fixed per video: system prompt + grounding notes
    plan_out_tokens_per_min: int = 600    # structured JSON plan per finished minute
    # narration
    tts_per_char: float = 0.000016        # ~Gemini TTS audio-token pricing at ~15 chars/s
    chars_per_min: int = 900              # ~150 wpm
    # photos
    photos_per_min: float = 0.8
    photo_review_cost: float = 0.004      # vision review of ~6 thumbnails (Haiku-class)
    # render compute (Lambda x86)
    render_cpu_s_per_video_s: float = 1.8  # measured locally on 4 busy cores; real Lambda may differ
    lambda_gb: float = 3.0
    lambda_per_gb_s: float = 0.0000166667
    overhead_per_min: float = 0.002       # audio mix, stitch, S3, Step Functions, logs
    # uncertainty bands applied to the total
    low: float = 0.7
    high: float = 1.6
    # store commission on consumables: 15% (small-business programmes) or 30%
    fees: Tuple[float, float] = (0.15, 0.30)


def parts(minutes: float, p: Params) -> Dict[str, float]:
    m = math.ceil(minutes)
    return {
        "planning": p.plan_in_tokens * p.llm_in_per_m / 1e6 + m * p.plan_out_tokens_per_min * p.llm_out_per_m / 1e6,
        "voice": m * p.chars_per_min * p.tts_per_char,
        "photo_review": m * p.photos_per_min * p.photo_review_cost,
        "render": m * 60 * p.render_cpu_s_per_video_s * p.lambda_gb * p.lambda_per_gb_s,
        "overhead": m * p.overhead_per_min,
    }


def cogs(minutes: float, p: Params, scenario: str = "mid") -> float:
    return sum(parts(minutes, p).values()) * {"low": p.low, "mid": 1.0, "high": p.high}[scenario]


# ---- product rules (proposal) -------------------------------------------------
CREDITS_PER_MINUTE = 5                      # "a video costs 5 credits per started minute"
PACKS: List[Tuple[float, int]] = [(9.99, 100), (19.99, 220), (199.99, 2400)]  # +10% and +20% bonus credits
WELCOME = {"videos": 3, "max_minutes": 3, "watermark": False}   # first 24 h
DAILY = {"videos": 1, "max_minutes": 2, "watermark": True}
TARGET = 7.0


def worst_margin(p: Params, fee: float = 0.15, scenario: str = "mid", lengths=range(1, 13)) -> float:
    """Lowest margin across every pack and every video length: the number the 7x target is judged on."""
    return min(margin(pr, cr, m, fee, p, scenario) for pr, cr in PACKS for m in lengths)


def credits_for(minutes: float) -> int:
    return CREDITS_PER_MINUTE * math.ceil(minutes)


def margin(price: float, credits: int, minutes: float, fee: float, p: Params, scenario: str = "mid") -> float:
    """(store-net revenue of the credits this video uses) / (our cost of this video)."""
    return price * (1 - fee) / credits * credits_for(minutes) / cogs(minutes, p, scenario)


# ---- AI edit actions: price = max(1, ceil(cost / cost-budget-per-credit)) ------
def edit_costs(p: Params) -> Dict[str, Dict[str, float]]:
    voice = 420 * p.tts_per_char                                        # a 70-word scene
    photo = p.photo_review_cost
    rewrite = 1500 * p.llm_in_per_m / 1e6 + 500 * p.llm_out_per_m / 1e6  # AI rewrite of one scene (future)
    compute_chunk = 30 * p.render_cpu_s_per_video_s * p.lambda_gb * p.lambda_per_gb_s  # one re-rendered 30 s chunk
    mix = 0.0015
    return {
        "re-voice a scene": {"ai": voice, "compute": compute_chunk + mix},
        "find new photos (new query)": {"ai": photo, "compute": compute_chunk},
        "AI-rewrite a scene (planned)": {"ai": rewrite + voice, "compute": compute_chunk + mix},
        "reorder / delete / text, chart, timeline, look, music": {"ai": 0.0, "compute": compute_chunk + mix},
    }


def report(p: Params) -> str:
    L: List[str] = []
    a = L.append
    a("## Cost to make a video (estimate)\n")
    a("| Length | Planning | Voice | Photo review | Render | Overhead | **Total (mid)** | per minute |")
    a("|---|---|---|---|---|---|---|---|")
    for m in (1, 2, 3, 5, 10):
        c = parts(m, p)
        a(f"| {m} min | ${c['planning']:.3f} | ${c['voice']:.3f} | ${c['photo_review']:.3f} | ${c['render']:.3f} | ${c['overhead']:.3f} | **${sum(c.values()):.3f}** | ${sum(c.values()) / m:.3f} |")
    a(f"\nBands: low ×{p.low}, high ×{p.high} (uncertainty in LLM prices, TTS vendor, real Lambda speed). A paid voice such as ElevenLabs would roughly triple the voice line.\n")

    a(f"## Credits: {CREDITS_PER_MINUTE} per started minute\n")
    a("| Video | Credits | Our cost (mid) |")
    a("|---|---|---|")
    for m in (1, 2, 3, 5, 10, 12):
        a(f"| {m} min | {credits_for(m)} | ${cogs(m, p):.3f} |")
    a("\n## Packs and margin (store-net revenue ÷ our cost; target ≥ %gx)\n" % TARGET)
    a("| Pack | Credits | Price/credit | 3-min video, mid cost, 15% fee | 5-min | 1-min | 3-min, 30% fee | 3-min, HIGH cost, 15% fee | worst (1-min, high cost, 30% fee) |")
    a("|---|---|---|---|---|---|---|---|---|")
    for price, cr in PACKS:
        a(f"| ${price:.2f} | {cr} | ${price / cr:.4f} | **{margin(price, cr, 3, .15, p):.1f}x** | {margin(price, cr, 5, .15, p):.1f}x | {margin(price, cr, 1, .15, p):.1f}x | "
          f"{margin(price, cr, 3, .30, p):.1f}x | {margin(price, cr, 3, .15, p, 'high'):.1f}x | {margin(price, cr, 1, .30, p, 'high'):.1f}x |")

    a("\n## Free allowances: what they cost us\n")
    for name, rule in (("Welcome (first 24 h)", WELCOME), ("Daily", DAILY)):
        c = cogs(rule["max_minutes"], p)
        a(f"- **{name}:** {rule['videos']} × up to {rule['max_minutes']} min, watermark={rule['watermark']} → worst case ${rule['videos'] * c:.3f} per day per account (${rule['videos'] * c * 30:.2f}/month if used every day).")
    your_a = cogs(5, p) + 10 * cogs(1, p)
    a(f"- *Your original idea* (1 × 5 min clean + 10 × 1 min watermarked per day): worst case **${your_a:.2f}/day = ${your_a * 30:.2f}/month per account** if fully used.")
    pay_net = 9.99 * (1 - 0.15) - cogs(3, p) * 100 / 12
    a(f"\nA first $9.99 purchase leaves about **${pay_net:.2f}** after store fee and the cost of using all its credits. Break-even for the free tier: one payer covers the free usage of N free users, "
      f"N = {pay_net:.2f} ÷ (monthly free cost per user). A user who makes a free video 4 days a month costs about ${4 * cogs(DAILY['max_minutes'], p):.2f}/month, so one payer funds ~{pay_net / (4 * cogs(DAILY['max_minutes'], p)):.0f} of them.\n")

    a("## AI edit actions (cost → credits)\n")
    base_net = 9.99 * 0.85 / 100
    budget = base_net / TARGET
    a(f"One credit funds about **${budget:.4f}** of real cost at a {TARGET:g}x margin on the smallest pack (net ${base_net:.4f}/credit ÷ {TARGET:g}). Price of an action = max(1, ceil(AI cost ÷ ${budget:.4f})); non-AI compute is bundled (bounded by edit caps).\n")
    a("| Action | AI cost | Compute (bundled) | Credits |")
    a("|---|---|---|---|")
    for k, v in edit_costs(p).items():
        credits = 0 if v["ai"] == 0 else max(1, math.ceil(v["ai"] / budget))
        a(f"| {k} | ${v['ai']:.4f} | ${v['compute']:.4f} | **{credits}** |")
    return "\n".join(L)


def server_config(p: Params) -> Dict:
    return {
        "credits_per_started_minute": CREDITS_PER_MINUTE,
        "packs": [{"price_usd": pr, "credits": cr} for pr, cr in PACKS],
        "welcome": WELCOME, "daily_free": DAILY, "max_minutes_paid": 12,
        "ai_edit_credits": {"revoice_scene": 1, "new_photo_search": 1, "ai_rewrite_scene": 1},
        "free_ai_actions_per_video": 3,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print server config JSON instead of the report")
    args = ap.parse_args()
    print(json.dumps(server_config(Params()), indent=2) if args.json else report(Params()))
