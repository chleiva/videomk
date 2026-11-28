"""Fixture plans for characters that speak different languages: what a writer returns for the two requests the feature is judged on. Plain data, no model."""
import copy
from typing import Any, Dict, List, Tuple

SEA_REQUEST = "a French fox, a German bear and an Italian owl explain why the sea is salty"
OWNER_REQUEST = ("video for children of speaking in different languages okay so can we English Italian Spanish German French and talk about topic that is really "
                 "important for children so")

# (speaker, line in the speaker's language, translation into English)
SEA: List[Tuple[str, str, str]] = [
    ("fox", "Bonjour les amis ! Aujourd'hui nous allons voir pourquoi la mer est salée, et c'est une très bonne question.",
     "Hello friends! Today we are going to see why the sea is salty, and it is a very good question."),
    ("bear", "Das ist eine tolle Frage! Das Meer ist nicht immer salzig gewesen, und die Geschichte ist sehr alt.",
     "That is a great question! The sea has not always been salty, and the story is very old."),
    ("owl", "Esatto, e la storia non è semplice. Il sale arriva dalle rocce, che la pioggia consuma piano piano.",
     "Exactly, and the story is not simple. The salt comes from the rocks, which the rain slowly wears away."),
    ("fox", "Les rochers ? Comment le sel peut-il venir des rochers ? Explique-nous cela, mon ami, pour que nous comprenions.",
     "The rocks? How can salt come from rocks? Explain that to us, my friend, so that we understand."),
    ("bear", "Wenn der Regen auf die Berge fällt, nimmt er kleine Salze mit. Das Wasser läuft dann über den Fluss in das Meer.",
     "When the rain falls on the mountains, it takes small salts along. The water then runs along the river into the sea."),
    ("owl", "E il sole fa evaporare l'acqua, ma il sale non evapora. Rimane nel mare, ed è per questo che oggi è così salato.",
     "And the sun makes the water evaporate, but the salt does not evaporate. It stays in the sea, and that is why it is so salty today."),
    ("fox", "Donc la mer est comme une grande soupe de sel, et tous les fleuves sont des cuillères pleines ! C'est très drôle.",
     "So the sea is like a big salt soup, and all the rivers are full spoons! That is very funny."),
    ("bear", "Ja, und das Salz bleibt dort für immer, denn das Wasser geht nur als Wolke weg. Das ist ein guter Gedanke.",
     "Yes, and the salt stays there forever, because the water leaves only as a cloud. That is a good thought."),
    ("owl", "Anche il Mar Morto è molto salato, più di tutti gli altri mari. Non puoi andare a fondo, perché galleggi.",
     "Even the Dead Sea is very salty, more than all the other seas. You cannot sink, because you float."),
    ("fox", "Merci à vous tous et à bientôt ! Maintenant vous savez pourquoi la mer est salée. Au revoir, les amis !",
     "Thank you all and see you soon! Now you know why the sea is salty. Goodbye, friends!"),
]
SEA_LANGS = {"fox": "fr", "bear": "de", "owl": "it"}

# the owner's request, reduced to three characters and three languages (English, Italian, Spanish: the first three named); the topic the writer chose: friendship
FRIENDS: List[Tuple[str, str, str, str]] = [
    # speaker, line, translation into English, translation into Spanish
    ("fox", "Hello everyone! Today we talk about something very important for every child: being a good friend.",
     "Hello everyone! Today we talk about something very important for every child: being a good friend.",
     "¡Hola a todos! Hoy hablamos de algo muy importante para cada niño: ser un buen amigo."),
    ("owl", "Ciao amici! Un buon amico è colui che ti ascolta, e non è mai cattivo. Questo è molto importante, perché nessuno vuole stare solo.",
     "Hello friends! A good friend is someone who listens to you, and is never mean. This is very important, because nobody wants to be alone.",
     "¡Hola amigos! Un buen amigo es el que te escucha y nunca es malo. Esto es muy importante, porque nadie quiere estar solo."),
    ("bear", "¡Qué bonito! Para mí, un buen amigo es el que comparte sus juguetes y sus abrazos, y también dice la verdad.",
     "How lovely! For me, a good friend is one who shares his toys and his hugs, and also tells the truth.",
     "¡Qué bonito! Para mí, un buen amigo es el que comparte sus juguetes y sus abrazos, y también dice la verdad."),
    ("fox", "And what do you do when a friend is sad? You can sit next to them and say: I am here with you.",
     "And what do you do when a friend is sad? You can sit next to them and say: I am here with you.",
     "¿Y qué haces cuando un amigo está triste? Puedes sentarte a su lado y decir: estoy aquí contigo."),
    ("owl", "Bravo! E se un amico sbaglia, non è bello ridere di lui. Si dice: non fa niente, proviamo ancora una volta.",
     "Bravo! And if a friend makes a mistake, it is not nice to laugh at him. You say: it does not matter, let us try one more time.",
     "¡Bravo! Y si un amigo se equivoca, no es bonito reírse de él. Se dice: no pasa nada, probemos otra vez."),
    ("bear", "¡Exacto! Y cuando alguien nuevo llega al parque, también podemos decirle: ¿quieres jugar con nosotros?",
     "Exactly! And when someone new comes to the park, we can also say to them: do you want to play with us?",
     "¡Exacto! Y cuando alguien nuevo llega al parque, también podemos decirle: ¿quieres jugar con nosotros?"),
    ("fox", "Listening, sharing, and including everyone: that is how we make friends all over the world, in any language.",
     "Listening, sharing, and including everyone: that is how we make friends all over the world, in any language.",
     "Escuchar, compartir e incluir a todos: así hacemos amigos en todo el mundo, en cualquier idioma."),
    ("owl", "Grazie a tutti, e alla prossima! Ricordate: un amico è il regalo più bello che c'è. Ciao ciao!",
     "Thank you all, and see you next time! Remember: a friend is the most beautiful gift there is. Bye bye!",
     "¡Gracias a todos, y hasta la próxima! Recuerden: un amigo es el regalo más bonito que hay. ¡Chao chao!"),
]
FRIENDS_LANGS = {"fox": "en", "owl": "it", "bear": "es"}


def _scene(heading: str, who: str, cast: List[str]) -> Dict[str, Any]:
    return {"type": "presenter", "props": {"heading": heading[:48], "character": who, "cast": list(cast)}}


def plan(rows: List[Tuple[str, ...]], *, language: str, cast: List[str], voices: Dict[str, str], speakers: Dict[str, str], translation_index: int = 2, translation: str = "auto",
         target_seconds: int = 60, title: str = "Fixture") -> Dict[str, Any]:
    """A plan as the director's writer returns it (and the cartoon repair leaves it), with the voices a one-language video would give: `polyglot.finish` recasts them."""
    beats = []
    for i, row in enumerate(rows):
        beat = {"id": f"b{i + 1}", "speaker": row[0], "narration": row[1], "scene": _scene(row[1].split(".")[0].split("!")[0], row[0], cast)}
        if translation_index is not None and len(row) > translation_index:
            beat["translation"] = row[translation_index]
        beats.append(beat)
    return {"legit": True, "title": title, "description": "A conversation.", "mood": "bright", "theme": "sunrise", "language": language, "voices": dict(voices), "beats": beats,
            "target_seconds": target_seconds, "captions": True, "tts": {"provider": "polly", "voice": "", "style": ""}, "skills": [], "_expected_speakers": dict(speakers), "_translation": translation}


def sea_plan(**kw: Any) -> Dict[str, Any]:
    return plan(SEA, language="en", cast=["fox", "bear", "owl"], voices={"fox": "Joanna", "bear": "Stephen", "owl": "Brian"}, speakers=SEA_LANGS, **kw)


def friends_plan(main: str = "en", **kw: Any) -> Dict[str, Any]:
    idx = 3 if main == "es" else 2
    return plan(FRIENDS, language=main, cast=["fox", "owl", "bear"], voices={"fox": "Joanna", "owl": "Brian", "bear": "Stephen"} if main == "en" else {"fox": "Lucia", "owl": "Sergio", "bear": "Andres"},
                speakers=FRIENDS_LANGS, translation_index=idx, **kw)


def deep(p: Dict[str, Any]) -> Dict[str, Any]:
    return copy.deepcopy(p)
