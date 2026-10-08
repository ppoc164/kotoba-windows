"""Sentence boundaries derived from Whisper word timestamps."""
import re


def split_sentences(segments):
    result, words = [], []

    def flush():
        if words:
            text = ''.join(w['text'] for w in words).strip()
            if text:
                result.append(dict(start=words[0]['start'], end=words[-1]['end'], text=text))
            words.clear()

    for segment in segments:
        tokens = segment.get('words') or [dict(start=segment['start'], end=segment['end'], text=segment['text'])]
        for token in tokens:
            if words and token['start'] - words[-1]['end'] >= 1.0:
                flush()
            words.append(token)
            if re.search(r'[。！？!?…][\s”’」』]*$|(?<!\d)\.[\s”’"\']*$', token['text']) or words[-1]['end'] - words[0]['start'] >= 22:
                flush()
    flush()
    return result


def timestamp(seconds, srt=False):
    ms = round(seconds * 1000)
    h, rest = divmod(ms, 3600000)
    m, rest = divmod(rest, 60000)
    s, ms = divmod(rest, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}' if srt else f'{h:02}:{m:02}:{s:02}'


def to_srt(rows):
    return '\n\n'.join(f"{i}\n{timestamp(r['start'], True)} --> {timestamp(r['end'], True)}\n{r['text']}" for i, r in enumerate(rows, 1)) + '\n'
