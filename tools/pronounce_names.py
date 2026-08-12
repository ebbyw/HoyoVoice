#!/usr/bin/env python3
"""Character-name and lore-term pronunciations for the TTS, and the roster to
check the names against.

    python tools/pronounce_names.py                  # audit: what Kokoro says now vs. with the fix
    python tools/pronounce_names.py --write          # merge FIXES + roster genders into voices.json
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
# The Genshin roster documents each character's gender as `bodyType` —
# five rig names, two genders. StarRailRes documents no gender at all, so
# HSR names carry None and the auto-caster keeps its name-shape fallback
# for them.
BODY_GENDER = {"GIRL": "female", "LADY": "female", "LOLI": "female",
               "BOY": "male", "MALE": "male"}

ROSTERS = {
    "genshin": ("https://gi.yatta.moe/api/v2/en/avatar",
                lambda d: {v["name"]: BODY_GENDER.get(v.get("bodyType"))
                           for v in d["data"]["items"].values()}),
    "hsr": ("https://raw.githubusercontent.com/Mar-7th/StarRailRes/"
            "master/index_min/en/characters.json",
            lambda d: {v["name"]: None for v in d.values()}),
}

# The rosters list PLAYABLE characters only, so the NPCs with spoken forms
# below have no documented gender to fetch. Without an entry here the
# auto-caster falls back to a name-shape suffix guess — which read Paimon,
# the single most common speaker in Genshin, in a MALE voice for a whole
# session (hoyovoice-20260812-084224: "-on" is not on the feminine suffix
# list). Katheryne trips the same wire: "-yne" isn't "-yn".
NPC_GENDERS = {
    "Paimon": "female",
    "Enjou": "male",
    "Katheryne": "female",
    "Gilgamesh": "male",
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
    # the -yne rhymes with "wine" on both engines (misaki kˈæθəɹɹˌIn, espeak
    # kæθɚɹaɪn) where the guild receptionist is plain Catherine. Respelled to
    # the ordinary spelling rather than hyphen chunks: "Kath-er-rin" makes
    # three stressed syllables (kˈæθˈɜɹˈɪn) where the name has one, and both
    # engines already read "Katherine" as kˈæθɹɪn / kæθɹɪn.
    "Katheryne": "Katherine",
    # Nod-Krai, and Russian: Стужа, "STOO-zha". Both engines read the u as
    # the /ʌ/ of "cut" — stˈʌʒə, "STUH-zhuh"; the zh is already right.
    # "Stoozha" is stˈuʒə on both: the one wrong vowel fixed and nothing
    # else moved. Unhyphenated on purpose, like "Asha" below — "Stoo-zhah"
    # is stˈuʒˈɑ, a second stressed chunk and an open final a where the name
    # ends on a schwa, and "Stoo-zhuh" (stˈuʒˈʌ) buys the same stress for
    # the right vowel.
    "Stuzha": "Stoozha",
    # Windows only, like "shaman": misaki already says ɡˈɪlɡəmˌɛʃ, espeak
    # says ɡˈɪlɡAməʃ — "GIL-gay-mush", an /eɪ/ in the middle and the last
    # syllable swallowed. "Gil-gah-mesh" is ɡˈɪlɡˈɑmˈɛʃ / ɡˈɪlɡˈɑːmˈɛʃ:
    # three stressed chunks rather than misaki's schwa, but the open ah is
    # the reading asked for by ear. "Gilgah-mesh" keeps the schwa
    # (ɡˈɪlɡəmˈɛʃ on both) and was rejected for it.
    "Gilgamesh": "Gil-gah-mesh",
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
    # keyed on the surname alone: dialogue says "Yae" and "Miss Yae" more
    # often than the full name, and the old "Yae Miko" key left those reading
    # jˈi, "Yee". Word-bounded substitution covers "Yae Miko" too, and "Miko"
    # by itself already reads mˈikO / mˈiːkoʊ — no entry needed. The literal
    # "Ya-ey" is NOT the respelling: a chunk-final "ey" is /aɪ/ on both
    # engines ("ya-EYE"), the same trap as "eh" in the header, mirrored.
    # "Yah-eh" is jˌɑˈA / jˈɑːˈeɪ — "yah-ay", both vowels land.
    "Yae": "Yah-eh",
    "Yumemizuki Mizuki": "Yoo-meh-mee-zoo-kee Mee-zoo-kee",
    # --- Genshin: everywhere else ---
    "Chiori": "Chee-oh-ree",
    "Citlali": "Seet-lah-lee",
    "Dehya": "Deh-yah",
    # both engines apply English short vowels end to end: dˈɪlʌk, "DILL-uck",
    # where the name is "dee-LUKE". "Dee-luke" is dˈilˈuk / dˈiːlˈuːk on the
    # two engines — both vowels land.
    "Diluc": "Dee-luke",
    "Escoffier": "Ess-koff-yay",
    "Faruzan": "Fah-roo-zahn",
    "Freminet": "Frem-ee-nay",
    "Kaveh": "Kah-veh",
    "Kinich": "Kee-neech",
    "Lauma": "Lau-mah",
    # the vu is a w, not a v followed by a vowel. Both engines read the raw
    # name as mˈævjuˌɪkə, "MAV-yoo-ick-uh"; the first respelling here fixed
    # the vowels but kept the v (mˈɑvˈuikˈɑ, "mah-voo-EE-kah") — an extra
    # syllable the name doesn't have. "Mah-wee-kah" is mˈɑwˈikˈɑ /
    # mˈɑːwˈiːkˈɑː.
    "Mavuika": "Mah-wee-kah",
    "Mualani": "Moo-ah-lah-nee",
    # both engines apply English spelling rules end to end: nˈæhɪdə,
    # "NAH-hid-uh", a flat first a and a schwa where the name ends open.
    # "Nah-hee-dah" is nˈɑhˈidˈɑ / nˈɑːhˈiːdˈɑː.
    "Nahida": "Nah-hee-dah",
    "Nilou": "Nee-loo",
    # the raw name is sˈIʤwɪn on both, "SIJE-win": the ge is already soft,
    # and what is wrong is the first vowel (/aɪ/) and the clipped last one.
    # "See-guh-win" over-corrected — sˈiɡˈʌwˈɪn hardened the g back and
    # bought a third syllable the name doesn't have. "Seej-ween" is
    # sˈiʤwˈin / sˈiːʤwˈiːn. NOT "Siege-ween" or "Seege-ween", which are the
    # same phones but split the stress on the second chunk (misaki wˌin
    # against espeak wˈiːn).
    "Sigewinne": "Seej-ween",
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
    # Windows only, and the worst kind of wrong: espeak reads "Ms." as the
    # LETTERS — ˌɛmˈɛs, "em-ess" (misaki says mˈɪz). "Miss" is mˈɪs on both.
    # A key ending in a period needs the boundary handling in
    # live.spoken_form() and check() below: \b after "\." would demand a word
    # character where the following space is, and the entry would never fire.
    # The other honorifics were measured and left OUT: "Mrs." is already
    # mˈɪsɪz ("misses") and "Dr." already dˈɑktəɹ / dˈɑːktɚ on both engines —
    # entries would change nothing. So were "Aeon"/"Aeons", already
    # ˈiɑn(z) / ˈiːɑːn(z), "EE-on(z)", on both.
    "Ms.": "Miss",
    # "ma'am" as written is already mˈæm on both engines and needs no entry.
    # What needs one is the form the OCR leaves when it misses the
    # apostrophe: "maam" is mˈɑm on both, "mahm" with the open a of
    # "father". "mam" is mˈæm. Lowercase like "shaman" — it is a common
    # noun, and a capitalised replacement mid-sentence reads as a name.
    "maam": "mam",
    # ˈɪmɪʤnˌi / ˈɪmɪʤnˌiː on the two engines — "IM-ij-nee", the middle
    # vowel dropped and the ending read as -ee. The word should be heard as
    # "imagine" plus "-ay". The literal "imagine-ay" is NOT the respelling: a
    # standalone "ay" chunk is /aɪ/ on both engines ("im-AJ-in-EYE"), the
    # same trap as "eh" and "ey" in the header. "Imagin-nay" is ɪmˈæʤɪnnˈA
    # on both — the doubled n is a held /n/, not a syllable. "Imadgi-nay"
    # (ɪmˈæʤinˈA) avoids the doubling but shifts the third vowel to /i/,
    # "im-AJ-ee-nay", and was rejected for it.
    "Imagenae": "Imagin-nay",
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
    # kwəkjusˈɔɹəs / kwəkjuːsˈɔːɹəs, "kwuh-KYOO-sore-us" — the qu read as
    # /kw/ and the cu as /kju/, where the bird is "koo-koo". Unhyphenated on
    # purpose, like "Asha": "Koo-koo-soar-us" makes four stressed chunks and
    # ends "-USS" (kˈukˈusˈɔɹˌʌs), where "Koocoosaurus" keeps the natural
    # -saurus stress and schwa on both engines: kˌukusˈɔɹəs /
    # kˌuːkuːsˈɔːɹəs, "koo-koo-SORE-us". The species name on screen is
    # usually the short "Qucusaur", wrong the same way (kwəkjˈusɔɹ), and
    # substitution is word-bounded — every form needs its own entry.
    "Qucusaurus": "Koocoosaurus",
    "Qucusauruses": "Koocoosauruses",
    "Qucusaur": "Koocoosaur",
    "Qucusaurs": "Koocoosaurs",
    # sˌɛɹənˈIɾiə, "seren-EYE-tee-uh" — the "tea" read as its own two vowels
    # behind an /aɪ/. The word is a pun on "serenity" and is meant to be
    # HEARD as it: səɹˈɛnəɾi. Respelled to the ordinary word, the same move
    # as Reignbow → Rainbow; the pun survives because the pot is on screen,
    # not because the synthesizer winks. Word-bounded, so "Serenitea Pot"
    # comes out "Serenity Pot".
    "Serenitea": "Serenity",
    # --- places. Wrong the same way names are: English spelling rules over
    # pinyin and romaji. They are proper nouns, so --custom-words pins them
    # in the OCR vocabulary too.
    # lˈɪju / lˈɪjuː, "LIH-yoo" — the i is the i of "lit" and the ue is a
    # dropped vowel. "Lee-wey" is lˈiwˈA / lˈiːwˈA. Spelled "-wey" and not
    # "-way", which reads the same phones but splits the stress (misaki
    # lˌiwˈA against espeak lˈiːwˈA) — the split that "Ah-shah" was rejected
    # for above.
    "Liyue": "Lee-wey",
    # ɡˈɪli on both, "GILL-ee". "Gway-lee" is ɡwˈAlˈi / ɡwˈAlˈiː. NOT
    # "Guay-lee", which is ɡwˈIlˈi — "GWY-lee", the /aɪ/ of "guy": ua is
    # that diphthong to both engines, the same trap as a chunk-final "eh".
    "Guili": "Gway-lee",
    # ˈɔɹəbˌæksi / ˈɔːɹəbˌæksi, "OR-uh-BAK-see" — an open "or" where the word
    # starts on "oh", and a schwa swallowing the second syllable.
    # "Oh-roh-bak-shi" is ˈOɹˈObˈækʃi on both, identically. The last chunk is
    # "-shi" rather than "-shee" on purpose: "-shee" takes a stress of its
    # own (ˈækʃˈi), and the name ends unstressed.
    "Orobaxi": "Oh-roh-bak-shi",
    # nˌɑɹɹukˈɑmi / nˌɑːɹɹuːkˈɑːmi — the vowels are close, but "ru" doubles
    # the rhotic (ɹɹ), which is a trill the name doesn't have.
    # "Nah-roo-kah-mee" is nˈɑɹˈukˈɑmˈi / nˈɑːɹˈuːkˈɑːmˈiː: one r, and even
    # stress across the four syllables rather than a peak on "kah".
    "Narukami": "Nah-roo-kah-mee",
    # snˈɛʒnAə on BOTH engines — "snezh-NAY-uh": the zh survives but "naya"
    # collapses to /neɪə/. "Snezh-nah-yuh" is snˈɛʒnˈɑjˈʌ / snˈɛʒnˈɑːjˈʌ —
    # every vowel lands, and the ʒ (the zh of "measure") is kept, which is
    # what the ear-gloss "nehj" is reaching for; "Snej-nah-yuh" with a real
    # /ʤ/ (snˈɛʤ-) was measured and is there to swap in if the ʒ doesn't
    # convince by ear. Chunked despite the stress-per-chunk cost: the
    # unhyphenated tails pronounce their h — "Snezh-nahyah" is snˈɛʒnˈæhiə,
    # "snezh-NAH-hee-uh". The adjective "Snezhnayan(s)" is wrong the same
    # way (snˈɛʒnAən(z)) and substitution is word-bounded, so both forms
    # get entries ending "-yun(s)", jˈʌn(z), to match the nation's "yuh".
    "Snezhnaya": "Snezh-nah-yuh",
    "Snezhnayan": "Snezh-nah-yun",
    "Snezhnayans": "Snezh-nah-yuns",
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
RETIRED = {
    "Fatus": "Fah-toose",
    # superseded by the "Yae" entry: keyed on the surname so standalone "Yae"
    # and "Miss Yae" are covered, and "Miko" alone already reads right. Left
    # in voices.json it is dead config — the "Yae" substitution fires first
    # and the full-name key can never match again.
    "Yae Miko": "Yah-eh Mee-koh",
}

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
        roster = parse(json.loads(r.read().decode()))
    # placeholders ("{NICKNAME}") and the trailblazer's variants aren't names
    return dict(sorted((n, g) for n, g in roster.items()
                       if n and "{" not in n))


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
        # mirrors live.spoken_form(): a key ending in "." takes no trailing \b
        tail = r"\b" if word[-1:].isalnum() else ""
        out = re.sub(rf"\b{re.escape(word)}{tail}", spoken, out,
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
    # documented genders for the auto-caster: the roster's bodyType plus the
    # shipped NPC table. Same rule as pronunciations — the documented value
    # wins, so --write carries a correction through; a deliberate voice
    # choice lives in "characters" via recasting, not here.
    genders = settings.setdefault("genders", {})
    shipped_g = dict(NPC_GENDERS)
    for names in rosters.values():
        shipped_g.update({n: g for n, g in names.items() if g})
    g_added = {k: v for k, v in shipped_g.items() if genders.get(k) != v}
    genders.update(g_added)
    settings["genders"] = dict(sorted(genders.items()))
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
        # hint it doesn't need. Capitalisation is the tell — and the key has
        # to be a plain word, or the "Ms." honorific entry would pin a
        # period-bearing token the recognizer can never emit.
        cw.update(t for t in TERMS
                  if t[:1].isupper() and PLAIN_WORD.fullmatch(t))
        # a retired term is no longer worth pinning either — unless it is a
        # real name that a roster also supplies
        roster_words = {w for names in rosters.values() for name in names
                        for w in name.split()}
        cw -= {k for k in gone if k not in roster_words}
        settings["custom_words"] = sorted(w for w in cw if len(w) > 1)
        words = len(settings["custom_words"]) - before
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(f"{path}: +{len(added)} pronunciations, +{len(g_added)} genders"
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
