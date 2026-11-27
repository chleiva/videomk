#!/usr/bin/env python3
"""Rebuild the voice catalogue from Amazon Polly itself (never from memory).

  AWS_PROFILE=qa python backend/scripts/polly_voice_catalog.py --list                 # what Polly offers today, per region (free)
  AWS_PROFILE=qa python backend/scripts/polly_voice_catalog.py --write [--measure]    # rewrite lambdas/engine/voice_data.py

`--list` calls `describe-voices --engine generative` in every region that offers the generative engine and prints the voices and the
differences between regions. `--write` regenerates `engine/voice_data.py` (the data `engine/voices.py` reads). With `--measure` every voice
says ONE fixed sentence of its language (about 200 characters, generative engine: about 0.6 cents per voice, about $0.35 for all of them) and
its speaking rate is recorded: seconds, words per minute and the pace relative to the estimate of `engine/length.py`. Without `--measure` the
rates already in voice_data.py are kept. The audio is kept in --audio-dir (if given) so the alignment tests can be run on it without paying twice.
Nothing here is called by the product.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

REGIONS = ["us-east-1", "us-west-2", "eu-central-1", "eu-west-2", "ca-central-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2",
           "eu-west-1", "eu-west-3", "ap-south-1", "sa-east-1"]
# One sentence per language, the same content in each: two commas, two full stops, one number. Used only to measure how fast a voice speaks.
SAMPLE = {
    "en": "Every morning, about 300 trains leave the central station. Some cross the whole country, while others only travel to the next town, and each one follows a timetable planned months ago.",
    "es": "Cada mañana salen unos 300 trenes de la estación central. Algunos cruzan todo el país, mientras que otros solo llegan al pueblo vecino, y cada uno sigue un horario planificado hace meses.",
    "fr": "Chaque matin, environ 300 trains quittent la gare centrale. Certains traversent tout le pays, tandis que d'autres ne vont que jusqu'à la ville voisine, et chacun suit un horaire prévu depuis des mois.",
    "de": "Jeden Morgen verlassen etwa 300 Züge den Hauptbahnhof. Einige durchqueren das ganze Land, während andere nur bis in die nächste Stadt fahren, und jeder folgt einem Fahrplan, der vor Monaten festgelegt wurde.",
    "it": "Ogni mattina circa 300 treni lasciano la stazione centrale. Alcuni attraversano tutto il paese, mentre altri arrivano solo alla città vicina, e ognuno segue un orario pianificato mesi fa.",
    "pt": "Todas as manhãs, cerca de 300 trens saem da estação central. Alguns atravessam o país inteiro, enquanto outros vão apenas até a cidade vizinha, e cada um segue um horário planejado há meses.",
    "nl": "Elke ochtend vertrekken ongeveer 300 treinen van het centraal station. Sommige doorkruisen het hele land, terwijl andere alleen naar de volgende stad rijden, en elke trein volgt een dienstregeling die maanden geleden is gepland.",
    "pl": "Każdego ranka około 300 pociągów odjeżdża z dworca centralnego. Niektóre przejeżdżają przez cały kraj, inne jadą tylko do sąsiedniego miasta, a każdy trzyma się rozkładu zaplanowanego wiele miesięcy temu.",
    "fi": "Joka aamu noin 300 junaa lähtee päärautatieasemalta. Jotkut kulkevat koko maan halki, kun taas toiset ajavat vain naapurikaupunkiin, ja jokainen noudattaa kuukausia sitten suunniteltua aikataulua.",
    "ko": "매일 아침 약 300대의 기차가 중앙역을 떠납니다. 어떤 기차는 전국을 가로지르고, 다른 기차는 이웃 도시까지만 가며, 모든 기차는 몇 달 전에 계획된 시간표를 따릅니다.",
}
# Polly's language name -> the accent word the director and the resolver use.
ACCENT = {
    "en-US": "American", "en-GB": "British", "en-AU": "Australian", "en-IN": "Indian", "en-IE": "Irish", "en-NZ": "New Zealand", "en-ZA": "South African", "en-SG": "Singaporean",
    "es-ES": "Spanish (Spain)", "es-MX": "Mexican", "es-US": "Latin American (US)",
    "fr-FR": "French (France)", "fr-CA": "Canadian", "fr-BE": "Belgian",
    "de-DE": "German (Germany)", "de-AT": "Austrian", "de-CH": "Swiss",
    "it-IT": "Italian", "pt-BR": "Brazilian", "nl-NL": "Dutch (Netherlands)", "nl-BE": "Belgian (Flemish)", "pl-PL": "Polish", "fi-FI": "Finnish", "ko-KR": "Korean",
}


def describe(region: str):
    import boto3
    try:
        return boto3.client("polly", region_name=region).describe_voices(Engine="generative")["Voices"]
    except Exception as e:  # noqa: BLE001 - a region without Polly or without access is just reported
        print(f"  {region}: {type(e).__name__}", file=sys.stderr)
        return []


def survey():
    by_region = {r: describe(r) for r in REGIONS}
    return {r: v for r, v in by_region.items() if v}


def measure(voice_id: str, lang: str, region: str, audio_dir: str = ""):
    from engine import tts
    from engine.audio import SR, write_wav
    text = SAMPLE[lang]
    path = os.path.join(audio_dir, f"{voice_id}.wav") if audio_dir else ""
    if path and os.path.exists(path):
        from engine.audio import read_wav
        samples, _ = read_wav(path)
    else:
        samples = tts.synth_beat(tts.get_provider("polly", cfg={"engine": "generative", "region": region}), text, voice=voice_id)
        if path:
            write_wav(path, samples, SR)
    seconds = samples.size / SR
    return round(seconds, 2), round(len(text.split()) / seconds * 60.0), round(len(text) / seconds * 60.0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--region", default="us-east-1", help="the region the engine synthesises in (POLLY_REGION)")
    ap.add_argument("--audio-dir", default="")
    a = ap.parse_args()
    by_region = survey()
    base = {v["Id"]: v for v in by_region.get(a.region, [])}
    if not base:
        print(f"no generative voices in {a.region}", file=sys.stderr)
        return 1
    full = [r for r, vs in by_region.items() if {v["Id"] for v in vs} == set(base)]
    partial = {r: sorted(set(base) - {v["Id"] for v in vs}) for r, vs in by_region.items() if r not in full}
    if a.list or not a.write:
        for v in sorted(base.values(), key=lambda v: (v["LanguageCode"], v["Id"])):
            print(f'{v["LanguageCode"]:6} {v["LanguageName"]:26} {v["Id"]:10} {v["Gender"]:7} engines={",".join(v["SupportedEngines"])} also={",".join(v.get("AdditionalLanguageCodes", []))}')
        print(f"\n{len(base)} voices in {a.region}. Same list in: {', '.join(full)}")
        for r, missing in partial.items():
            print(f"{r}: {len(base) - len(missing)} voices; missing {', '.join(missing)}")
        print("no generative engine in:", ", ".join(r for r in REGIONS if r not in by_region))
    if not a.write:
        return 0
    try:
        from engine import voice_data
        old = {v["id"]: v for v in voice_data.VOICES}
    except Exception:  # noqa: BLE001 - first run
        old = {}
    if a.audio_dir:
        os.makedirs(a.audio_dir, exist_ok=True)
    rows = []
    for v in sorted(base.values(), key=lambda v: (v["LanguageCode"], v["Id"])):
        lang = v["LanguageCode"][:2]
        row = {"id": v["Id"], "name": v["Name"], "locale": v["LanguageCode"], "language": lang, "accent": ACCENT.get(v["LanguageCode"], v["LanguageName"]),
               "gender": v["Gender"].lower(), "engines": sorted(v["SupportedEngines"]), "also": sorted(v.get("AdditionalLanguageCodes", []))}
        if a.measure and lang in SAMPLE:
            row["sample_s"], row["wpm"], row["cpm"] = measure(v["Id"], lang, a.region, a.audio_dir)
            print(f'{v["Id"]:10} {row["sample_s"]:6.2f} s  {row["wpm"]} wpm  {row["cpm"]} chars/min')
        else:
            for k in ("sample_s", "wpm", "cpm"):
                if k in old.get(v["Id"], {}):
                    row[k] = old[v["Id"]][k]
        rows.append(row)
    out = os.path.join(os.path.dirname(__file__), "..", "lambdas", "engine", "voice_data.py")
    with open(out, "w", encoding="utf-8") as f:
        f.write('"""Every Amazon Polly GENERATIVE voice, as Polly lists them. GENERATED by scripts/polly_voice_catalog.py: do not edit by hand.\n\n'
                "`sample_s`, `wpm`, `cpm`: one fixed sentence per language said by the voice (seconds, words per minute, characters per minute), measured.\n"
                '`engines`: the Polly engines the voice exists in; `also`: other languages the same voice speaks (Polly\'s AdditionalLanguageCodes).\n"""\n')
        f.write(f"CHECKED = {datetime.date.today().isoformat()!r}\nREGION = {a.region!r}\n")
        f.write(f"SAME_LIST_REGIONS = {json.dumps(sorted(full))}\nPARTIAL_REGIONS = {json.dumps(partial, sort_keys=True)}\n")
        f.write("SAMPLE = {\n" + "".join(f"    {k!r}: {json.dumps(t, ensure_ascii=False)},\n" for k, t in SAMPLE.items()) + "}\n")
        f.write("VOICES = [\n" + "".join("    " + json.dumps(r, ensure_ascii=False) + ",\n" for r in rows) + "]\n")
    print(f"wrote {out}: {len(rows)} voices")
    return 0


if __name__ == "__main__":
    sys.exit(main())
