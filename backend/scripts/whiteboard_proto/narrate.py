#!/usr/bin/env python3
"""Narration with word times, the engine's way: one Polly generative call per sentence (engine/tts.py synth_beat), silence trimmed, words placed by
engine/align.py align_words (pauses matched to punctuation). The sentences are then laid end to end with a breath between them.

  AWS_PROFILE=qa narrate.py en|es   -> WORK/audio/<lang>.wav and <lang>.json {duration, sentences: [{text, start, end, words: [[word, start, end]]}]}
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "lambdas"))
sys.path.insert(0, HERE)

import wbcommon as common  # noqa: E402

LEAD = 0.9         # the pen starts on the title before the voice does
BREATH = 0.38      # between sentences
LONG_BREATH = 0.75  # after a dense point (marked with "|" at the end of a sentence)
TAIL = 2.2

SCRIPT = {
    "en": ("Ruth", [
        "Where does rain come from?",
        "It starts with the sun.",
        "The sun warms the sea, the lakes and the rivers, and some of that water turns into an invisible gas called water vapour.",
        "This is evaporation.|",
        "Plants help too: they release water through their leaves.",
        "The vapour rises, and high in the sky the air is cold, so it turns back into tiny drops.",
        "That is condensation, and it is how clouds form.|",
        "When the drops get heavy, they fall as rain or snow.",
        "The water runs down the mountains into rivers, back to the sea, and the journey starts again.",
        "That is the water cycle.",
    ]),
    "es": ("Lucia", [
        "¿De dónde viene la lluvia?",
        "Todo empieza con el sol.",
        "El sol calienta el mar, los lagos y los ríos, y parte de esa agua se convierte en un gas invisible llamado vapor de agua.",
        "Esto es la evaporación.|",
        "Las plantas también ayudan: liberan agua a través de sus hojas.",
        "El vapor sube, y en lo alto del cielo el aire es frío, así que vuelve a convertirse en gotas diminutas.",
        "Eso es la condensación, y así se forman las nubes.|",
        "Cuando las gotas pesan demasiado, caen en forma de lluvia o de nieve.",
        "El agua baja por las montañas hasta los ríos, vuelve al mar, y el viaje empieza de nuevo.",
        "Ese es el ciclo del agua.",
    ]),
}


def synth(sentences, voice: str, name: str):
    """Narration for any board: -> (wav path, words dict). Cached by the text and the voice, so a board re-renders without paying again."""
    import hashlib

    key = hashlib.sha1((voice + "|" + "|".join(sentences)).encode()).hexdigest()[:10]
    wav, js = os.path.join(common.AUDIO, f"{name}_{key}.wav"), os.path.join(common.AUDIO, f"{name}_{key}.json")
    if not (os.path.exists(wav) and os.path.exists(js)):
        _make(sentences, voice, wav, js, name)
    return wav, json.load(open(js))


def main() -> int:
    lang = sys.argv[1]
    voice, sentences = SCRIPT[lang]
    _make(sentences, voice, os.path.join(common.AUDIO, lang + ".wav"), os.path.join(common.AUDIO, lang + ".json"), lang)
    return 0


def _make(sentences, voice, wav_path, json_path, lang) -> None:
    from engine import align, audio, tts

    region = os.environ.get("POLLY_REGION", "us-east-1")
    provider = tts.PollyTTS(region=region, engine="generative")
    chars = sum(len(s) for s in sentences)
    common.reserve("polly", chars * provider.cost_per_char)
    t = LEAD
    parts, out = [np.zeros(int(LEAD * audio.SR), np.float32)], []
    for raw in sentences:
        text = raw.rstrip("|")
        samples = tts.synth_beat(provider, text, voice=voice)
        words, conf = align.align_words(samples, audio.SR, text)
        dur = len(samples) / audio.SR
        if not words or conf < 0.3:
            words = align.estimate_words(text, dur)
        out.append({"text": text, "start": round(t, 3), "end": round(t + dur, 3), "align_confidence": round(float(conf), 2),
                    "words": [[w, round(t + a, 3), round(t + b, 3)] for w, a, b in words]})
        gap = LONG_BREATH if raw.endswith("|") else BREATH
        parts += [samples, np.zeros(int(gap * audio.SR), np.float32)]
        t += dur + gap
    parts.append(np.zeros(int(TAIL * audio.SR), np.float32))
    wav = np.concatenate(parts)
    audio.write_wav(wav_path, wav, audio.SR)
    json.dump({"voice": voice, "engine": "generative", "duration": round(len(wav) / audio.SR, 3), "sentences": out}, open(json_path, "w"), ensure_ascii=False, indent=1)
    common.charge(f"polly generative {voice} {chars} chars", chars * provider.cost_per_char, item="narration " + lang)
    print(lang, "duration", round(len(wav) / audio.SR, 1), "s;", sum(len(s["words"]) for s in out), "words; lowest alignment confidence", min(s["align_confidence"] for s in out))


if __name__ == "__main__":
    sys.exit(main())
