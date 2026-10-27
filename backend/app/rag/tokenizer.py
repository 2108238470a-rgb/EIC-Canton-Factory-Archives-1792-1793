"""Chinese word tokens when jieba is available; deterministic CJK bigram fallback."""

import re

try:
    import jieba
except ImportError:
    jieba = None


def tokenize(text):
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    for run in re.findall(r"[\u3400-\u9fff]+", text):
        if jieba:
            tokens.extend(w for w in jieba.cut(run, cut_all=False) if w.strip())
        else:
            tokens.extend(run[i : i + 2] for i in range(max(1, len(run) - 1)))
    return " ".join(tokens)
