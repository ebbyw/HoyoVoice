#!/usr/bin/env python3
"""Character-name and lore-term pronunciations for the TTS, and the roster to
check the names against.

    python tools/pronounce_names.py                  # audit: what Kokoro says now vs. with the fix
    python tools/pronounce_names.py --write          # merge FIXES into voices.json
    python tools/pronounce_names.py --custom-words   # also feed every roster name to the OCR vocabulary

Kokoro phonemizes English spelling rules, so Chinese and Japanese names come
out mangled in a specific, predictable way: pinyin x reads as /z/ ("Xiao" →
"ZY-ah-oh"), q as /k/ ("Qiqi" → "KIH-kee"), zh as /ʒ/ ("Zhongli" → "ZHONG-lee"),
and a final -e vanishes ("Shenhe" → "shenh"). `settings.pronunciations` fixes
that: the respelling below is what the synthesizer hears, while logs, dedupe
and casting keep the real spelling.

Every respelling here was checked against the SAME g2p Kokoro uses (misaki +
espeak fallback) — run this script to see both readings side by side. Respell,
don't reach for IPA: misaki accepts inline phonemes, but the Windows backend
(kokoro-onnx) doesn't, and a markup that only works on one platform is worse
than a plain approximation that works on both.

Things the g2p does that constrain the respellings, all measured:
  - a hyphen chunk is treated as its own word, so a chunk-final "eh" reads
    /eɪ/ ("Freh" → "fray"). Put the /ɛ/ before a consonant: "Frem-ee-nay".
  - an unreadable initial cluster is spelled out letter by letter: "Shway"
    → "S-H-way". Avoid shw/chw/hw/lw at the start of a chunk.
  - "ge" is soft ("Gep-ard" → "JEP-ard"); "ghe" keeps the hard g.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Rosters, in English, from the two community data mirrors that track the
# live game versions. Both are plain JSON over HTTPS and need no key.
# Fetched at run time and never vendored: what this repo keeps is the list of
# names (facts, and HoYoverse's marks either way) plus our own respellings —
# not their files. Project Yatta / Amber (gi.yatta.moe) and Mar-7th's
# StarRailRes (AGPL-3.0) are the upstreams; credit belongs to them.
ROSTERS = {
    "genshin": ("https://gi.yatta.moe/api/v2/en/avatar",
                lambda d: [v["name"] for v in d["data"]["items"].values()]),
    "hsr": ("https://raw.githubusercontent.com/Mar-7th/StarRailRes/"
            "master/index_min/en/characters.json",
            lambda d: [v["name"] for v in d.values()]),
}

# name -> what the synthesizer should hear. Only names Kokoro gets WRONG are
# listed: "Ningguang", "Hu Tao" and "Yao Guang" already come out right, and an
# entry that changes nothing is a line of config to maintain for free.
FIXES = {
    # --- NPCs: the rosters list PLAYABLE characters only, so the companion
    # who talks more than anyone else in Genshin isn't in either fetch ---
    "Paimon": "Pie-mahn",
    # "en-JOO" (ɛnʤˈu) — the Abyss Order clerk's name ends in the "joe" sound.
    # NOT "ehn-joe", which reads "AYN-joe" (ˈAnʤˈO): a chunk-initial "eh" is
    # /eɪ/ on both engines, the same trap the header records for "Freh".
    "Enjou": "En-joe",
    # --- Genshin: pinyin ---
    "Baizhu": "Bye-joo",
    "Beidou": "Bay-doe",
    "Chongyun": "Chong-yoon",
    "Ganyu": "Gahn-yoo",
    "Gaming": "Gah-ming",
    "Keqing": "Kuh-ching",
    "Lan Yan": "Lahn Yen",
    "Qiqi": "Chee-chee",
    "Shenhe": "Shen-huh",
    "Xiangling": "Shyahng-ling",
    "Xianyun": "Shyen-yoon",
    "Xiao": "Shyow",
    "Xingqiu": "Shing-chyoh",
    "Xinyan": "Shin-yen",
    "Yanfei": "Yen-fay",
    "Yaoyao": "Yow-yow",
    "Yelan": "Yel-lahn",
    "Yun Jin": "Yoon Jin",
    "Zhongli": "Jong-lee",
    "Zibai": "Zuh-bye",
    # --- Genshin: Japanese ---
    "Kaedehara Kazuha": "Kah-eh-deh-hah-rah Kah-zoo-hah",
    "Kaeya": "Kay-ya",
    "Kamisato Ayaka": "Kah-mee-sah-toh Ah-yah-kah",
    "Kamisato Ayato": "Kah-mee-sah-toh Ah-yah-toh",
    "Kujou Sara": "Koo-joh Sah-rah",
    "Kuki Shinobu": "Koo-kee Shee-noh-boo",
    "Sangonomiya Kokomi": "Sahn-go-no-mee-yah Ko-ko-mee",
    "Sayu": "Sah-yoo",
    "Shikanoin Heizou": "Shee-kah-no-een Hay-zoh",
    "Yae Miko": "Yah-eh Mee-koh",
    "Yumemizuki Mizuki": "Yoo-meh-mee-zoo-kee Mee-zoo-kee",
    # --- Genshin: everywhere else ---
    "Chiori": "Chee-oh-ree",
    "Citlali": "Seet-lah-lee",
    "Dehya": "Deh-yah",
    "Escoffier": "Ess-koff-yay",
    "Faruzan": "Fah-roo-zahn",
    "Freminet": "Frem-ee-nay",
    "Kaveh": "Kah-veh",
    "Kinich": "Kee-neech",
    "Lauma": "Lau-mah",
    "Mavuika": "Mah-vooee-kah",
    "Mualani": "Moo-ah-lah-nee",
    # both engines apply English spelling rules end to end: nˈæhɪdə,
    # "NAH-hid-uh", a flat first a and a schwa where the name ends open.
    # "Nah-hee-dah" is nˈɑhˈidˈɑ / nˈɑːhˈiːdˈɑː.
    "Nahida": "Nah-hee-dah",
    "Nilou": "Nee-loo",
    "Sigewinne": "See-guh-win",
    "Wriothesley": "Rees-lee",
    "Xilonen": "Shee-loh-nen",
    # --- Star Rail: pinyin ---
    "Bailu": "Bye-loo",
    "Feixiao": "Fay-shyow",
    "Fu Xuan": "Foo Shoo-en",
    "Guinaifen": "Gway-nye-fen",
    "Hanya": "Hahn-yah",
    "Huohuo": "Hoo-aw-hoo-aw",
    "Jiaoqiu": "Jyow-chyoh",
    "Jing Yuan": "Jing Yoo-en",
    "Jingliu": "Jing-lyoh",
    "Luocha": "Loo-aw-chah",
    "Qingque": "Ching-chueh",
    "Ruan Mei": "Rwahn May",
    "Sushang": "Soo-shahng",
    "Tingyun": "Ting-yoon",
    "Xueyi": "Shoo-eh-yee",
    "Yanqing": "Yen-ching",
    # --- Star Rail: everywhere else ---
    "Aglaea": "Ah-glay-uh",
    "Anaxa": "Ah-nak-sah",
    "Asta": "Ass-tuh",
    "Castorice": "Castor-ess",
    "Gepard": "Ghep-ard",
    "Himeko": "Hee-meh-koh",
    "Seele": "See-luh",
}

# Lore terms — not people, so no roster lists them and the coverage report
# below can't check them. They reach the synthesizer through exactly the same
# settings.pronunciations map, and they're worth shipping for the same reason:
# an invented word is precisely what English spelling rules mangle. They also
# go into the OCR vocabulary under --custom-words, since a word the recognizer
# has never seen is the one it fuses into its neighbour.
TERMS = {
    # unhyphenated on purpose: "aa-shah" phonemizes to ˈɑˌɑʃˌɑ, an extra
    # syllable, and "Ah-shah" splits the two engines (misaki ˌɑʃˈɑ, espeak
    # ˈɑːʃˈɑː). "Ahshaa" is ˈɑʃɑ on both.
    "Asha": "Ahshaa",
    # "eign" is read as its own syllable: ɹˌiˈInbO, "ree-EYE-n-bow"
    "Reignbow": "Rainbow",
    # Windows only, like "shaman": misaki says ˈɑɹkɑn already, espeak says
    # ˈɑːɹtʃˌɔn ("AR-chon", the ch of church). The plural needs its own entry
    # because substitution is word-bounded.
    "Archon": "Ahr-kon",
    "Archons": "Ahr-kons",
    # Wrong on ONE platform, like "shaman": misaki says flOʤˈɪstən already,
    # espeak says flˈɑːdʒɪstən ("FLAH-jis-tun"). "flo-jiston" is flˈOʤˈɪstən
    # on both — the reading macOS already had. Spelled with the last
    # syllable joined on purpose: "flo-jis-ten" makes a third stressed chunk
    # (flˈOʤˈɪstˈɛn, "-TEN"), where the word ends in a schwa.
    "Phlogiston": "flo-jiston",
    # Wrong on BOTH engines, and the same way: the a is the flat a of "fat"
    # and the t is flapped — misaki fˈæɾui, espeak fˈæɾuːi, "FAT-oo-ee".
    # "Fah-too-ee" is fˈɑtˈuˈi / fˈɑːtˈuːˈiː, an open ah and a real t.
    "Fatui": "Fah-too-ee",
    # The singular. Same flat a and flap, and it also loses a syllable:
    # fˈæɾuz / fˈæɾuːz, "FAT-ooz", where the word has three. "Fah-too-oose"
    # is fˈɑtˈuˈus / fˈɑːtˈuːˈuːs on both. Spelled "-oose" rather than
    # "-oos" for the hiss — "-oos" is a voiced z on both engines
    # (fˈɑtˈuˈuz, "fah-too-OOZ"), where the word ends on an s.
    "Fatuus": "Fah-too-oose",
    # Read as English "way" plus a flat "ob" on both engines — misaki
    # wˈAɑb, espeak wˈeɪɑːb, "WAY-ahb". "Wah-yohb" is wˈɑjˈOb / wˈɑːjˈoʊb.
    # The plural needs its own entry, substitution being word-bounded, and
    # it has to be "-yohbs": "Wah-yobes" splits the engines (misaki
    # wˌɑjˈɑbz, back to the flat ob), where "-yohbs" is wˈɑjˈObz /
    # wˈɑːjˈoʊbz on both.
    "Wayob": "Wah-yohb",
    "Wayobs": "Wah-yohbs",
    # The one entry here that is only wrong on ONE platform: misaki says
    # ʃˈɑmən, espeak says ʃˈæmən ("SHAM-un", rhyming with salmon), so this
    # reads correctly on macOS and wrong on Windows. "shahmon" is ʃˈɑmən on
    # both — the same reading macOS already had, not a new approximation.
    # Lowercase on purpose: it is a common noun, and a capitalised
    # replacement mid-sentence reads as a proper noun. The plural needs its
    # own entry because substitution is word-bounded, so \bshaman\b never
    # matches inside "shamans"; "shamanism" has the same split if it ever
    # turns up.
    "shaman": "shahmon",
    "shamans": "shahmons",
    # NOT a phonetic fix, and the one entry here that breaks this file's own
    # rule about no-ops on purpose: "Wishpower" already reads correctly as
    # wˈɪʃpWəɹ. Two stressed words rather than one compound is a delivery
    # choice, A/B'd against the compound and kept because the difference is
    # audible. Keep it.
    "Wishpower": "Wish power",
}

# Entries this file used to ship and has withdrawn. `--write` only ever
# ADDS, so a retired entry would sit in every voices.json forever — and
# voices.json is gitignored, which makes "pull the fix" no help and hand
# editing it on the other machine the only way out. Listed with the exact
# value we shipped: an entry whose value has since been changed by hand is
# the user's own and is left alone.
#
#   Fatus — not a word in either game. The singular of Fatui is "Fatuus",
#   which has its own entry above.
RETIRED = {"Fatus": "Fah-toose"}

# Names that are also ordinary English words. Matching is case-insensitive by
# default (OCR case jitter shouldn't lose a name), which would respell the
# common word too — "the gaming table" is not the Liyue chef. These match the
# capitalised spelling only. Any future entry for Jade, Sunday, Hook, Blade,
# Archer, Robin or March 7th belongs here as well.
EXACT = ["Gaming"]

# --custom-words tokenizing: keep name words, drop the connective tissue
PLAIN_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
STOP = {"the", "and", "of", "a"}


def fetch(game):
    url, parse = ROSTERS[game]
    # yatta 403s the default urllib agent
    req = urllib.request.Request(url, headers={"User-Agent": "HoyoVoice/roster"})
    with urllib.request.urlopen(req, timeout=30) as r:
        names = parse(json.loads(r.read().decode()))
    # placeholders ("{NICKNAME}") and the trailblazer's variants aren't names
    return sorted({n for n in names if n and "{" not in n})


def load_g2p():
    """The exact phonemizer Kokoro runs — without it there is nothing to audit."""
    try:
        from misaki import en, espeak
        return en.G2P(trf=False, british=False,
                      fallback=espeak.EspeakFallback(british=False))
    except Exception as e:                       # noqa: BLE001 - report, don't crash
        print(f"[no g2p: {e}] — install misaki to see phonemes", file=sys.stderr)
        return None


def phonemes(g2p, text):
    if g2p is None:
        return ""
    try:
        return g2p(text)[0]
    except Exception:                            # noqa: BLE001
        return "?"


def audit(rosters, g2p):
    print(f"{'name':26} {'Kokoro hears':26} {'respelled as':28} reads as")
    for name, spoken in sorted(FIXES.items()):
        tag = " [exact case]" if name in EXACT else ""
        print(f"{name:26} {phonemes(g2p, name):26} {spoken:28} "
              f"{phonemes(g2p, spoken)}{tag}")
    for term, spoken in sorted(TERMS.items()):
        print(f"{term:26} {phonemes(g2p, term):26} {spoken:28} "
              f"{phonemes(g2p, spoken)} [term]")
    for game, names in rosters.items():
        # substitution is word-bounded, so "Himeko • Nova" is already covered
        # by the "Himeko" entry — don't report it as missing
        missing = [n for n in names
                   if not any(k in n for k in FIXES)]
        print(f"\n{game}: {len(names)} characters, {len(names) - len(missing)} "
              f"with a spoken form")
        print("  no entry (Kokoro's own reading is fine, or unchecked): "
              + ", ".join(missing))


def check(path, sample):
    """What THIS machine's config would actually say — the answer to
    'it still reads the name wrong'.

    Deliberately does not import live.py: the point is to work on a machine
    where the app itself may be the thing that's broken. The substitution
    below mirrors live.spoken_form(), which is what really runs.
    """
    if not path.exists():
        print(f"{path}: MISSING — the app writes it on first run")
        return 1
    settings = json.loads(path.read_text()).get("settings", {})
    pron = settings.get("pronunciations", {})
    exact = set(settings.get("pronunciations_exact", []))
    stamp = __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime)
    print(f"{path}\n  last written {stamp:%Y-%m-%d %H:%M:%S} — the app reads "
          "this file ONCE at startup, so restart it if it has been running "
          "since before then")
    print(f"  {len(pron)} pronunciations, {len(exact)} exact-case, "
          f"{len(settings.get('custom_words', []))} OCR words")
    shipped = {**FIXES, **TERMS}
    absent = [n for n in shipped if n not in pron]
    stale = [n for n, v in shipped.items() if n in pron and pron[n] != v]
    if absent:
        print(f"  MISSING {len(absent)}: {', '.join(absent[:8])}"
              f"{' …' if len(absent) > 8 else ''}")
        print("  -> run this script with --write")
    if stale:
        print(f"  differs from the table (yours wins): {', '.join(stale)}")
    if not absent and not stale:
        print("  every name and term in the table is present")
    out = sample
    for word, spoken in pron.items():
        out = re.sub(rf"\b{re.escape(word)}\b", spoken, out,
                     flags=0 if word in exact else re.IGNORECASE)
    print(f"\n  in:  {sample}\n  out: {out}")
    return 0


def merge(path, rosters, custom_words):
    cfg = json.loads(path.read_text())
    settings = cfg.setdefault("settings", {})
    pron = settings.setdefault("pronunciations", {})
    added = {k: v for k, v in {**FIXES, **TERMS}.items() if pron.get(k) != v}
    pron.update(added)                       # hand-written entries win nothing
    # withdrawn entries go out again, but only where the value is still the
    # one we shipped — a changed value is the user's own respelling
    gone = [k for k, v in RETIRED.items() if pron.get(k) == v]
    for k in gone:
        pron.pop(k)
    settings["pronunciations"] = dict(sorted(pron.items()))
    settings["pronunciations_exact"] = sorted(
        set(settings.get("pronunciations_exact", [])) | set(EXACT))
    words = 0
    if custom_words:
        cw = set(settings.get("custom_words", []))
        before = len(cw)
        for names in rosters.values():
            for name in names:
                # a vocabulary hint is only worth adding if it's a WORD the
                # OCR could get wrong: "The Herta" and "March 7th" contribute
                # "Herta" and "March", not "The", "7th", "LV.999" or "Dr."
                cw.update(w for w in name.split()
                          if PLAIN_WORD.fullmatch(w) and w.lower() not in STOP)
        # invented words are what OCR fuses worst — but only the invented
        # ones. A term that is an ordinary English word ("shaman") is already
        # in the recognizer's vocabulary, and pinning it there would be a
        # hint it doesn't need. Capitalisation is the tell.
        cw.update(t for t in TERMS if t[:1].isupper())
        # a retired term is no longer worth pinning either — unless it is a
        # real name that a roster also supplies
        roster_words = {w for names in rosters.values() for name in names
                        for w in name.split()}
        cw -= {k for k in gone if k not in roster_words}
        settings["custom_words"] = sorted(w for w in cw if len(w) > 1)
        words = len(settings["custom_words"]) - before
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"{path}: +{len(added)} pronunciations"
          + (f", -{len(gone)} retired" if gone else "")
          + (f", +{words} OCR words" if custom_words else ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="merge the spoken forms into voices.json")
    ap.add_argument("--custom-words", action="store_true",
                    help="also add every roster name to the OCR vocabulary")
    ap.add_argument("--voices", default=str(ROOT / "voices.json"))
    ap.add_argument("--offline", action="store_true",
                    help="skip the roster fetch (audit the table only)")
    ap.add_argument("--check", nargs="?", const="Paimon met Xiao and Qiqi.",
                    metavar="LINE",
                    help="report what this machine's voices.json would say")
    args = ap.parse_args()

    if args.check:
        return check(Path(args.voices).expanduser(), args.check)

    rosters = {}
    if not args.offline:
        for game in ROSTERS:
            try:
                rosters[game] = fetch(game)
            except Exception as e:               # noqa: BLE001
                print(f"[{game}: roster fetch failed: {e}]", file=sys.stderr)
    if args.write or args.custom_words:
        if args.custom_words and not rosters:
            print("--custom-words needs the roster; drop --offline", file=sys.stderr)
            return 1
        merge(Path(args.voices).expanduser(), rosters, args.custom_words)
        return 0
    audit(rosters, load_g2p())
    return 0


if __name__ == "__main__":
    sys.exit(main())
