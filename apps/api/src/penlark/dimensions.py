"""The style dimensions: what each one means in plain words, how it is drawn on the radar, and what to suggest when a text is off."""

from __future__ import annotations

# key: (label, plain meaning, radar range lo, hi, absolute tolerance floor, weight, "too low" advice, "too high" advice)
SCALAR = {
    "sentence_length": ("Sentence length", "Words in an average sentence.", 3, 35, 1.5, 1.5, "Your sentences are shorter than this voice. Join some with a comma or an and.", "Your sentences are longer than this voice. Split the longest ones in two."),
    "sentence_variety": ("Sentence rhythm", "How much sentence length jumps around.", 0, 18, 1.2, 1.0, "The rhythm is flatter than this voice. Mix a very short sentence in.", "The rhythm is jumpier than this voice. Even out the lengths."),
    "paragraph_length": ("Paragraph length", "Sentences per paragraph.", 1, 8, 0.4, 1.0, "Your paragraphs are shorter than this voice. Group related lines together.", "Your paragraphs are longer than this voice. Break them up."),
    "one_line_paragraphs": ("One line paragraphs", "Share of paragraphs that are a single sentence.", 0, 1, 0.12, 1.0, "This voice uses more one line paragraphs. Give a punchy line its own space.", "This voice uses fewer one line paragraphs. Merge a few lines."),
    "contractions": ("Contractions", "Short forms like don't and it's, per 100 words.", 0, 10, 0.8, 1.2, "This voice uses more contractions. Write don't, it's and we're.", "This voice uses fewer contractions. Write do not, it is and we are."),
    "questions": ("Questions", "Question marks per sentence.", 0, 0.5, 0.05, 1.0, "This voice asks more questions. Ask the reader one.", "This voice asks fewer questions. Turn one into a statement."),
    "exclamations": ("Exclamations", "Exclamation marks per sentence.", 0, 0.4, 0.04, 0.8, "This voice uses more exclamation marks.", "This voice uses fewer exclamation marks."),
    "commas": ("Commas", "Commas per sentence.", 0, 4, 0.35, 1.0, "This voice uses more commas, so thoughts run on a little longer.", "This voice uses fewer commas. Cut some and shorten the sentence."),
    "heavy_punctuation": ("Colons, brackets and ellipses", "Semicolons, colons, brackets, quotes and ellipses per sentence.", 0, 1.5, 0.12, 0.8, "This voice uses more colons, brackets or ellipses.", "This voice uses fewer colons, brackets or ellipses."),
    "numbers": ("Numbers", "Number words and digits per 100 words.", 0, 12, 1.0, 1.0, "This voice uses more concrete numbers. Add a real figure from your sources.", "This voice uses fewer numbers. Keep only the one that matters."),
    "vocabulary_richness": ("Vocabulary variety", "How often new words appear (moving average).", 0.5, 1.0, 0.05, 0.8, "This voice repeats words less. Vary your wording.", "This voice repeats words more. Reuse your key words."),
    "formality": ("Formality", "Formal words minus casual words, per 100 words.", -6, 8, 1.0, 1.5, "This voice is more formal. Swap casual words for plain formal ones.", "This voice is more casual. Loosen the wording."),
    "you_address": ("Speaking to the reader", "You, we and our, per 100 words.", 0, 12, 1.2, 1.0, "This voice speaks to the reader more. Use you and we.", "This voice speaks to the reader less. Describe, do not address."),
    "i_voice": ("First person", "I, me and my, per 100 words.", 0, 10, 1.0, 1.0, "This voice says I more. Speak from your own experience.", "This voice says I less. Make the point without the I."),
}
VECTOR = {
    "word_habits": ("Word habits", "The small everyday words this person leans on (the, but, so, just, however).", 2.0, "Your small words drift from this voice. Read two of your own posts and match the connectors you use."),
    "openers": ("How sentences open", "Mix of sentence openers: questions, numbers, I, you or we, and, but, so.", 1.0, "Your sentence openers differ from this voice. Check how it usually starts a line."),
}
ALL = list(SCALAR) + list(VECTOR)


def label(key: str) -> str:
    return SCALAR[key][0] if key in SCALAR else VECTOR[key][0]


def meaning(key: str) -> str:
    return SCALAR[key][1] if key in SCALAR else VECTOR[key][1]
