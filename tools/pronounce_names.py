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
    # An Easybreeze Holiday Resort NPC — a minor speaking role, and on
    # neither playable roster. Both engines read the ai as /eɪ/: tˈumAni,
    # "too-MAY-nee". The user's own spelling is exactly right and is kept as
    # written: "Too-mai-knee" is tˈumˈInˈi on both, and the silent k costs
    # nothing ("Too-mai-nee" and "Too-mye-nee" are the same phones).
    "Tumaini": "Too-mai-knee",
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
    # A full-name key only fires on the full name, and dialogue rarely uses
    # one: tools/textmap_words.py counted "Ayaka" alone 258 times in the
    # dumps against the 20-odd for "Kamisato Ayaka", "Kazuha" 255, "Arataki"
    # 571. Every one of those reads wrong today. Keyed on the parts, the same
    # move the "Yae" entry records — and where BOTH parts have an entry the
    # full-name key is dead config and is retired below (a shorter key sorts
    # first and wins the substitution).
    # ˌæɹətˈæki on both — "a-ra-TACK-ee", the English flat a twice over.
    "Arataki": "Ah-rah-tah-kee",
    # the initial a is swallowed into the /aɪ/ of "eye" on both engines:
    # Iˈɑkə, "eye-AH-kuh". "Ah-yah-kah" is ˈɑjˈɑkˈɑ.
    "Ayaka": "Ah-yah-kah",
    # same, plus a flapped t: IˈɑɾO, "eye-AH-doh". "Ah-yah-toh" is ˈɑjˈɑtˈO.
    "Ayato": "Ah-yah-toh",
    # hˈIzu, "HY-zoo". "Hay-zoh" is hˈAzˈO on both — the spelling the
    # retired "Shikanoin Heizou" entry already used for this half.
    "Heizou": "Hay-zoh",
    # kˌidɪhˈɑɹɹə, "kee-di-HAH-ruh", with espeak's doubled rhotic on top.
    # "Kah-ed-eh-hah-rah" is kˈɑˈɛdˈAhˈɑɹˈɑ on both. The third syllable is
    # the one this file can't spell: Japanese "de" is /de/, and a chunk
    # written "deh" is /deɪ/ to BOTH engines ("Kah-eh-deh-hah-rah", the old
    # full-name spelling, is kˈɑˈAdˈAhˈɑɹˈɑ — "kah-AY-day-hah-rah", TWO of
    # them). "Kah-ed-dess-hah-rah" lands the vowel (kˈɑˈɛddˈɛshˈɑɹˈɑ) by
    # inventing an /s/ the name doesn't have, and "Kah-ed-heh-hah-rah"
    # sounds both h's. One wrong vowel, and it is the second-to-last.
    "Kaedehara": "Kah-ed-eh-hah-rah",
    # ˈɪɾO on both — "IT-oh", with the t flapped to a d. "Ee-toh" is ˈitˈO.
    # The clan name has its own entry ("Arataki") above.
    "Itto": "Ee-toh",
    "Kaeya": "Kay-ya",
    # kˌæmɪsˈɑɾO — flat a, and the t flapped to a d. Alphabetically ahead of
    # the full-name keys, so those are retired rather than shadowed.
    "Kamisato": "Kah-mee-sah-toh",
    # kˈæzjuhə on both, "KAZ-yoo-huh". The surname has its own entry now, so
    # the two halves of the full name are respelled one after the other.
    "Kazuha": "Kah-zoo-hah",
    # kəkˈOmi — the first syllable reduced to a schwa, "kuh-KOH-mee".
    # "Ko-ko-mee" is kˈOkˈOmˈi on both.
    "Kokomi": "Ko-ko-mee",
    # kjˈuʤu, "KYOO-joo" — an English u in both syllables. "Koo-joh" is
    # kˈuʤˈO on both.
    "Kujou": "Koo-joh",
    "Kuki Shinobu": "Koo-kee Shee-noh-boo",
    # mɪzˈuki, "mih-ZOO-kee". "Mee-zoo-kee" is mˈizˈukˈi on both.
    "Mizuki": "Mee-zoo-kee",
    # sˈæŋɡənˌɑmɪjə — the flat a of "fat", then two syllables swallowed:
    # "SANG-uh-nah-mi-yuh". "Sahn-go-no-mee-yah" is sˈɑŋɡˌOnˈOmˈijˈɑ.
    "Sangonomiya": "Sahn-go-no-mee-yah",
    "Sayu": "Sah-yoo",
    # ʃˈɪkənˌYn — the "oin" read as the /ɔɪ/ of "coin", "SHIK-uh-noyn",
    # where the name ends on a plain "in". "Shee-kah-no-in" is ʃˈikˈɑnˈOˈɪn
    # on both engines. The last chunk is the user's ear: "-een" (ʃ…ˈOˈin)
    # was the first spelling here and closes on the vowel of "seen", which
    # is a syllable longer than the name has. Their literal "She-ka-no-in"
    # is the same four sounds and was NOT taken — misaki reads it ʃˌikˌɑn-
    # against espeak's ʃikˈɑn-, a stress split of the kind "Ah-shah" was
    # rejected for; "Shee-kah-" pins the same vowels on both.
    "Shikanoin": "Shee-kah-no-in",
    # ʃˈɪnəbˌu, "SHIN-uh-boo". "Shee-noh-boo" is ʃˈinˈObˈu on both. Sorts
    # after "Kuki Shinobu", so that entry still reads as itself.
    "Shinobu": "Shee-noh-boo",
    # keyed on the surname alone: dialogue says "Yae" and "Miss Yae" more
    # often than the full name, and the old "Yae Miko" key left those reading
    # jˈi, "Yee". Word-bounded substitution covers "Yae Miko" too, and "Miko"
    # by itself already reads mˈikO / mˈiːkoʊ — no entry needed. The literal
    # "Ya-ey" is NOT the respelling: a chunk-final "ey" is /aɪ/ on both
    # engines ("ya-EYE"), the same trap as "eh" in the header, mirrored.
    # "Yah-eh" is jˌɑˈA / jˈɑːˈeɪ — "yah-ay", both vowels land.
    "Yae": "Yah-eh",
    # jˌumɪmɪzˈuki, "yoo-mih-mih-ZOO-kee" — the two middle vowels clipped.
    # "Yoo-meh-mee-zoo-kee" is jˈumˈɛmˈizˈukˈi on both. (A mid-word "meh" is
    # /mɛ/ to both engines; it is "deh" that comes out /deɪ/ — see
    # "Kaedehara".)
    "Yumemizuki": "Yoo-meh-mee-zoo-kee",
    # --- Genshin: everywhere else ---
    "Chiori": "Chee-oh-ree",
    "Citlali": "Seet-lah-lee",
    # klˈɔɹɪnd on both, "KLOR-ind", where the duellist is French and said
    # "klo-RAHND". "Klo-rahnd" is klˈOɹˈɑnd on both, and is the user's own
    # gloss.
    "Clorinde": "Klo-rahnd",
    "Dehya": "Deh-yah",
    # both engines apply English short vowels end to end: dˈɪlʌk, "DILL-uck",
    # where the name is "dee-LUKE". "Dee-luke" is dˈilˈuk / dˈiːlˈuːk on the
    # two engines — both vowels land.
    "Diluc": "Dee-luke",
    # kˈɑlA on both — the "ei" read as /eɪ/, "KAH-lay", where the name ends
    # on the vowel of "see". "Coll-ee" is kˈɑlˈi.
    "Collei": "Coll-ee",
    # dˈʊɹɹɪn on both — espeak's doubled rhotic, and the u of "put".
    # "Doo-rin" is dˈuɹˈɪn.
    "Durin": "Doo-rin",
    "Escoffier": "Ess-koff-yay",
    "Faruzan": "Fah-roo-zahn",
    "Freminet": "Frem-ee-nay",
    # the engines disagree: misaki kəʧˈinə is right, espeak kˈæʧInə is
    # "KATCH-eye-nuh". "Kah-chee-nah" is kˈɑʧˈinˈɑ on both.
    "Kachina": "Kah-chee-nah",
    "Kaveh": "Kah-veh",
    "Kinich": "Kee-neech",
    "Lauma": "Lau-mah",
    # the vu is a w, not a v followed by a vowel. Both engines read the raw
    # name as mˈævjuˌɪkə, "MAV-yoo-ick-uh"; the first respelling here fixed
    # the vowels but kept the v (mˈɑvˈuikˈɑ, "mah-voo-EE-kah") — an extra
    # syllable the name doesn't have. "Mah-wee-kah" is mˈɑwˈikˈɑ /
    # mˈɑːwˈiːkˈɑː.
    # lInˈɛt on both — "lye-NET", the /aɪ/ of "eye" for a plain i.
    # "Lih-net" is lˈɪnˈɛt.
    "Lynette": "Lih-net",
    "Mavuika": "Mah-wee-kah",
    "Mualani": "Moo-ah-lah-nee",
    # both engines apply English spelling rules end to end: nˈæhɪdə,
    # "NAH-hid-uh", a flat first a and a schwa where the name ends open.
    # "Nah-hee-dah" is nˈɑhˈidˈɑ / nˈɑːhˈiːdˈɑː.
    "Nahida": "Nah-hee-dah",
    # fjʊɹɹˈinə — a /fj/ where the name opens on a plain "foo", and espeak's
    # doubled rhotic behind it. "Foo-ree-nah" is fˈuɹˈinˈɑ on both.
    "Furina": "Foo-ree-nah",
    # nˈæʃə, the flat a again. "Nahshah" is nˈɑʃə on both. Hyphenated it
    # splits them ("Nah-shah" is misaki nˌæʃˈɑ against espeak nˈɑʃˈɑ) —
    # a one-syllable first chunk keeps misaki's flat a, which is why
    # "Navia" below is chunked "Nahv-" and not "Nah-".
    "Nasha": "Nahshah",
    # nˈæviə, "NAV-ee-uh". "Nahv-ee-ah" is nˈɑvˈiˈɑ on both.
    "Navia": "Nahv-ee-ah",
    "Nilou": "Nee-loo",
    # nˈOl on both — one syllable, "nole", where the name has two.
    # "No-elle" is nˈOˈɛl; "No-ell" is the same phones with the second
    # chunk unstressed on misaki only (nˈOˌɛl).
    "Noelle": "No-elle",
    # the raw name is sˈIʤwɪn on both, "SIJE-win": the ge is already soft,
    # and what is wrong is the first vowel (/aɪ/) and the clipped last one.
    # "See-guh-win" over-corrected — sˈiɡˈʌwˈɪn hardened the g back and
    # bought a third syllable the name doesn't have. "Seej-ween" is
    # sˈiʤwˈin / sˈiːʤwˈiːn. NOT "Siege-ween" or "Seege-ween", which are the
    # same phones but split the stress on the second chunk (misaki wˌin
    # against espeak wˈiːn).
    # sˈændɹOn on both — "SAN-drohn", the final e silent, where the
    # Harbinger's name is Italian: "san-DROH-nay". "San-droh-nay" is
    # sˌændɹˈOnˈA on both.
    "Sandrone": "San-droh-nay",
    "Sigewinne": "Seej-ween",
    "Wriothesley": "Rees-lee",
    # tɪɡnˈɑɹɹi — the doubled rhotic again. "Tig-nah-ree" is tˈɪɡnˈɑɹˈi.
    "Tighnari": "Tig-nah-ree",
    "Xilonen": "Shee-loh-nen",
    # --- Star Rail: pinyin ---
    "Bailu": "Bye-loo",
    "Feixiao": "Fay-shyow",
    # "Shoo-en" splits the stress on the second half (misaki fˈu ʃˌuˈɛn
    # against espeak fˈu ʃˈuˈɛn); "Shu-en" is fˈu ʃˈuˈɛn on both. Same
    # spelling as the "Xuan" entry below, which is the user's.
    "Fu Xuan": "Foo Shu-en",
    "Guinaifen": "Gway-nye-fen",
    "Hanya": "Hahn-yah",
    "Huohuo": "Hoo-aw-hoo-aw",
    "Jiaoqiu": "Jyow-chyoh",
    # identical phones either way (ʤˈɪŋ jˈuˈɛn on both) — respelled only so
    # one sound has one spelling, matching the "Yuan" entry below.
    "Jing Yuan": "Jing Yu-en",
    "Jingliu": "Jing-lyoh",
    "Luocha": "Loo-aw-chah",
    "Qingque": "Ching-chueh",
    # keyed on the surname alone, like "Yae": dialogue says "Ruan" 613 times
    # across the dumps and the full name a fraction of that, and every bare
    # one read ɹjˈuæn ("RYOO-an"). "Mei" on its own is already mˈA on both
    # engines and needs no entry, so the full-name key is retired below.
    "Ruan": "Rwahn",
    "Sushang": "Soo-shahng",
    "Tingyun": "Ting-yoon",
    # kʃˈuæn — a spelled-out K in front of the x, then the flat a of "fat".
    # "Shu-en" is ʃˈuˈɛn on both, and is the user's spelling: "Shoo-en" is
    # the same two sounds but splits the stress (misaki ʃˌuˈɛn against
    # espeak ʃˈuˈɛn), so "Fu Xuan" above was respelled to match. Sorts after
    # that key, so the full name still reads as one name.
    "Xuan": "Shu-en",
    "Xueyi": "Shoo-eh-yee",
    "Yanqing": "Yen-ching",
    # juˈɑn / jˈuən — the engines don't even agree with each other, and
    # neither says "yoo-EN". "Yu-en" is jˈuˈɛn on both, and is the user's
    # spelling; "Yoo-en" is the identical phones, so "Jing Yuan" above was
    # respelled to the same halves rather than kept in two spellings for one
    # sound. Sorts after that key, so the general is still read as one name.
    "Yuan": "Yu-en",
    # --- Star Rail: everywhere else ---
    # A `split`, not a both-engines fault, and the entry that settled how
    # this file treats one. misaki says ˈækəɹˌɑn — which is exactly the
    # dictionary reading, /ˈækərɒn/, "ACK-uh-ron" — while espeak says
    # ˈAkɹɑn, "AY-kron", a syllable short. macOS has been right all along.
    # So the respelling reproduces the engine that HAS it right rather than
    # inventing a third reading: "Ack-uh-ron" is ˈækˈʌɹˈɑn on both.
    # "Ah-keron" (ˈɑkˈɛɹɑn, "ah-KEH-ron") was shipped for one revision as an
    # ear's preference and pulled for parity — it moves the stress to the
    # second syllable and the first vowel to the a of "father", which is a
    # third reading again. Measured runners-up for the dictionary one:
    # "Acke-ron" (ˈækɪɹˈɑn, an /ɪ/ for the schwa), "Ackeron" (the exact
    # vowels, ˈækəɹɹən, but a doubled rhotic) and "Ack-er-on" (ˈækˈɜɹˈɔn,
    # the "er" of "her").
    "Acheron": "Ack-uh-ron",
    "Aglaea": "Ah-glay-uh",
    "Anaxa": "Ah-nak-sah",
    "Asta": "Ass-tuh",
    "Castorice": "Castor-ess",
    # klˈɑɹɹə — the vowels are right and the r is doubled. "Klah-rah" is
    # klˈɑɹˈɑ on both.
    # sˈɜɹsᵻz — the last vowel clipped. "Ser-seez" is sˈɜɹsˈiz on both.
    "Cerces": "Ser-seez",
    "Clara": "Klah-rah",
    "Gepard": "Ghep-ard",
    # hˈɜɹɾə on both — the vowel is right and the t is flapped to a d,
    # "HER-duh". "Hurr-tah" is hˈɜɹtˈɑ on both: a real t and an open final a.
    # NOT "Her-tah", which is the same phones with the stress on the second
    # chunk (hɜɹtˈɑ, "her-TAH") — the name is stressed on the first.
    "Herta": "Hurr-tah",
    "Himeko": "Hee-meh-koh",
    # kˈæfkə — the flat a of "fat", where the name (and the author) is
    # "KAHF-kuh". "Kahf-kuh" is kˈɑfkˈʌ on both.
    "Kafka": "Kahf-kuh",
    # ɹˈæpə. "Rahp-ah" is ɹˈɑpˈɑ on both — chunked "Rahp-" for the reason
    # the "Nasha" entry records.
    # mˈIdA on both — "MY-day", where the gloss is "mai-dee". The user's
    # spelling ships as written: "Mai-dee" is mˈIdˈi on both. ("My-dee" is
    # the same phones with the stress off the first chunk, mˌIdˈi / mIdˈi.)
    "Mydei": "Mai-dee",
    "Rappa": "Rahp-ah",
    "Seele": "See-luh",
    # svˈæɹɑɡ, "SVAR-og". "Svah-rog" is svˈɑɹˈɑɡ on both.
    "Svarog": "Svah-rog",
    # tɹˈIæn on both — "TRY-an". "Tree-ann" is tɹˈiˈæn on both; the user's
    # "Tree-anne" is the same two sounds but splits the stress on the second
    # chunk (misaki tɹˈiˌæn against espeak tɹˈiˈæn), so the silent e goes.
    "Trianne": "Tree-ann",
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
    # Wrong on both engines and worst on Windows: misaki ˌOniɡˈɪɹi has the
    # hard g but clips the third vowel ("oh-nee-GIH-ree"), espeak reads the
    # gi as /ʤ/ AND breaks the vowel — ˌɑnɪʤˈiəɹi, "ah-nih-JEE-uh-ree".
    # "ghee" is what keeps the g hard: "oh-nee-gee-ree" is ˈOnˈiʤˈiɹˈi on
    # both, a j where the word has a g, and so is the ear-gloss spelling
    # "oh-knee-gee-ree" (the silent k changes nothing either way).
    # "oh-nee-ghee-ree" is ˈOnˈiɡˈiɹˈi on both engines, identically.
    # Chunked despite the stress-per-chunk cost: unhyphenated "ohneegheeree"
    # pronounces the h (ˌOniɡhˈɪɹi). Capitalised because the games write it
    # as an item name and --custom-words pins those in the OCR vocabulary —
    # matching is case-insensitive, so the lowercase prose form is covered
    # too, and the spoken form stays lowercase either way.
    "Onigiri": "oh-nee-ghee-ree",
    # --- places. Wrong the same way names are: English spelling rules over
    # pinyin and romaji. They are proper nouns, so --custom-words pins them
    # in the OCR vocabulary too.
    #
    # The block that follows came out of tools/textmap_words.py rather than
    # out of somebody's ear: these are the commonest words in the two dumps
    # that miss the phonemizer's lexicon, with the count the scan reported.
    # They are nations, regions and peoples — said constantly, on no roster,
    # and so never fixed before. The readings below are measured on both
    # engines like every other entry here; what has NOT happened yet is the
    # listen, so the rejected alternatives are recorded with their phonemes
    # for anyone who disagrees by ear.
    #
    # Two the scan raised and the ear then cleared, measured and left OUT
    # because an entry would change nothing: "Fragmentum" (1,305) is already
    # fɹæɡmˈɛntəm on both engines, "frag-MEN-tum", and "Amphoreus" (1,485) is
    # already æmfˈɔɹiəs, "am-FOR-ee-us" — both the reading asked for. The
    # scan lists them because the phonemizer's lexicon has neither and every
    # letter-rules guess is a candidate; a guess can still come out right.
    #
    # Ten more cleared the same way on the fourth pass, listed with the
    # reading both engines already give so nobody re-checks them: "Sparxie"
    # spˈɑɹksi and "Sparxicle" spˈɑɹksɪkᵊl (the x is the /ks/ of "spark",
    # not a pinyin one), "Sampo" sˈæmpO, "Graphia" ɡɹˈæfiə, "Aino" ˈAnO,
    # "Hyacine" hˈIəsˌin, "Maison" mˈAsən, "Natasha" nətˈæʃə, "Jahoda"
    # ʤæhˈOdə, "Zagreus" zˈæɡɹiəs, "Alhaitham" əlhˈAθæm. All are `oov` —
    # both engines guess, and both guess the same — so there is no platform
    # split hiding behind any of them either.
    # 3,126: zˈIənʒˌu on both — the pinyin x read as /z/ AND the zh as /ʒ/,
    # the two faults this file opens with, in one word. "Shyen-joh" is
    # ʃˈIənʤˈO, the "Shy-" onset the shipped Xiao/Xianyun/Xiangling entries
    # already use. "Shen-joh" (ʃˈɛnʤˈO) drops the glide for a plain /ɛ/ and
    # is the one to swap in if the /aɪ/ of "Shy-" doesn't convince.
    "Xianzhou": "Shee-an-joe",
    # 1,385: ljˈuəfˌu, "LYOO-uh-foo". "Loo-aw-foo" is lˈuˈɔfˈu on both — the
    # same two syllables the shipped "Luocha" → "Loo-aw-chah" is built from.
    # "Lwaw-foo" is spelled out as letters (ˈɛlwˈɔfˈu, "L-waw-foo"), the
    # initial-cluster trap in this file's header.
    "Luofu": "Loo-aw-foo",
    # 256: jˈAɑkɪŋ, "yay-AH-king". "Yow-ching" is jˈWʧˈɪŋ on both, the
    # reading the shipped "Yanqing" → "Yen-ching" and "Yaoyao" → "Yow-yow"
    # are built from.
    "Yaoqing": "Yow-ching",
    # 2,228: pˈɛnəkəni — every vowel after the first reduced to a schwa,
    # "PEN-uh-kuh-nee", where the third syllable is the stressed "coh".
    # "Penna-coh-nee" is pˈɛnəkˈOnˈi on both. NOT "Pen-uh-coh-nee", which is
    # the same phones with a stress on every chunk (pˈɛnˈʌkˈOnˈi).
    "Penacony": "Penna-coh-nee",
    # 1,370: bᵻlˈɑbɑɡ, "buh-LAH-bahg" — the stress on the middle syllable and
    # the first one swallowed. "Bell-oh-bog" is bˈɛlˌObˈɔɡ / bˈɛlˈObˈɑɡ: the
    # engines differ only in the cot/caught vowel and which chunk takes the
    # secondary stress, and both say "BELL-oh-bog".
    "Belobog": "Bell-oh-bog",
    # 2,354: mˈɔndstæt, "MOND-stat" — the d sounded and the flat a of "fat",
    # where the German is "MONT-shtat". "Mohntshtaht" is mˈOntʃtɑt on both.
    # Hyphenated it is worse, not better: "Mohnt-shtaht" puts a second stress
    # on a name that has one (mˈOntʃtˈɑt), and any chunk STARTING "sht" is
    # spelled out — "Mohnt-shtot" is mˈOntˌɛsˈAʧtˈɑt, "mohnt-ES-AITCH-tot".
    "Mondstadt": "Mohntshtaht",
    # 2,369: fˈɔntAn, "FON-tayn", where the nation is French and said
    # "fon-TEN". "Fon-ten" is fˌɑntˈɛn / fˈɑntˈɛn.
    "Fontaine": "Fon-ten",
    # 1,939: sˈuməɹɹˌu — the vowels are close, but "meru" doubles the rhotic
    # (ɹɹ), the trill "Narukami" was respelled to lose. "Soo-meh-roo" is
    # sˈumˈɛɹˈu on both. (A chunk-final "eh" is /eɪ/ per this file's header —
    # but only at the END of a word: mid-word "meh" is ɛ on both engines.)
    "Sumeru": "Soo-meh-roo",
    # 1,425: ɪnæzˈumə, "in-AZ-oo-muh" — English spelling rules end to end.
    # "Ee-nah-zoo-mah" is ˈinˈɑzˈumˈɑ on both.
    "Inazuma": "Ee-nah-zoo-mah",
    # 1,367: nˈætlən, the flat a twice. "Naht-lahn" is nˈɑtlˈɑn on both.
    "Natlan": "Naht-lahn",
    # 1,555: ˈækAdmˌɪjə, "AK-ay-d-mee-yuh" — the second syllable read as /eɪ/
    # and the third dropped altogether. Respelled to the ordinary English
    # word it is a transliteration of: "academia" is ˌækədˈimiə on both,
    # the same move as "Katheryne" → "Katherine" and "Kamera" → "Camera".
    # A hyphenated approximation ("Ah-kah-dem-ee-yah", ˈɑkˈɑdˈɛmˈijˈɑ)
    # shipped first and was heard as five stressed syllables.
    "Akademiya": "academia",
    # 498: ˌæɹənˈɑɹɹə — flat a and the doubled rhotic. "Ahrah-nah-rah" is
    # ˈɑɹənˈɑɹˈɑ on both. The fully hyphenated "Ah-rah-nah-rah" SPLITS the
    # engines (misaki nˈæ against espeak nˈɑ) and "Ah-rah-nar-ah" keeps the
    # doubled r it was meant to remove.
    "Aranara": "Ahrah-nah-rah",
    # 1,485, and the ear-gloss is the user's: "Stella-ron". stˈɛlæɹən on
    # both, "STELL-a-ron" with the flat a of "fat" where the name has a
    # schwa. The user's spelling is NOT what ships: "Stella-ron" is
    # stˈɛləɹˌɑn to misaki but stˈɛləɹɹˈɑn to espeak — the doubled rhotic
    # again, on Windows only. "Stell-uh-ron" is stˈɛlˌʌɹˈɑn / stˈɛlˈʌɹˈɑn:
    # same segments on both engines, one r, and the schwa the gloss asks for.
    "Stellaron": "Stell-uh-ron",
    # 963: fˈAnɑn, "FAY-non", where the gloss is "Fai-non". The user's
    # spelling is exactly right and ships as written — "Fai-non" is fˈInˈɑn
    # on both. ("Fy-non" and "Fye-non" are the same phones; the spelling
    # closest to the name wins.)
    "Phainon": "Fai-non",
    # The third pass down the same list. Places and lore first:
    # 507 in the Genshin dump: wˈæɾətsˌumi — the flat a of "fat" and a t
    # flapped to a d. "Wah-tah-tsoo-mee" is wˈɑtˈɑtsˈumˈi on both.
    "Watatsumi": "Wah-tah-tsoo-mee",
    # 380: ɹˈɪɾu, "RIT-oo", the same flap. "Ree-toh" is ɹˈitˈO.
    "Ritou": "Ree-toh",
    # 359: jæʃˈiəɹO. "Yah-shee-roh" is jˈɑʃˈiɹˈO on both.
    "Yashiro": "Yah-shee-roh",
    # 384: kˈɪŋs — the pinyin q read as /k/ AND the final e dropped, so the
    # village comes out "kings". "Ching-tsuh" is ʧˈɪŋtsˈu on both.
    "Qingce": "Ching-tsuh",
    # 492: ˈɑɹɹu, the doubled rhotic. "Ahroo" is ˈɑɹu on both — unhyphenated,
    # because "Ah-roo" splits the stress (misaki ˌɑɹˈu against espeak ˈɑɹˈu),
    # the split "Ah-shah" was rejected for above.
    "Aaru": "Ahroo",
    # 501: pˈæɹi. "Pah-ree" is pˈɑɹˈi on both.
    "Pari": "Pah-ree",
    # 392: the engines disagree — misaki ɑkˈɑʃə, espeak ækˈæʃə ("a-KASH-uh").
    # "Ah-kah-shah" is ˈɑkˈɑʃˈɑ on both, which is misaki's reading with the
    # final vowel opened.
    "Akasha": "Ah-kah-shah",
    # 504: kˈæməɹɹəz — the doubled rhotic on a word that is just "camera"
    # with a K. Respelled to the ordinary word, the move "Katheryne" →
    # "Katherine" and "Reignbow" → "Rainbow" already make; the plural needs
    # its own entry because substitution is word-bounded.
    "Kamera": "Camera",
    "Kameras": "Cameras",
    #
    # 721 in the Star Rail dump: kˈɛfAl on both — "KEF-ayl", two syllables
    # where the Greek has three. "Keff-uh-lee" is kˈɛfˈʌlˈi on both. The
    # user's gloss "kef-a-lee" is the same reading and was nearly kept: it
    # differs only in which schwa the two engines write for the middle
    # vowel (misaki ɐ, espeak ə), which no ear will find, but "Keff-" pins
    # one symbol on both and costs nothing.
    "Kephale": "Keff-uh-lee",
    # 443 in the Genshin dump: mˈɛɹəpˌId, "MER-uh-pyde". "Meh-ro-peed" is
    # mˈɛɹˈOpˈid on both, and is the user's gloss as written.
    "Meropide": "Meh-ro-peed",
    # 652 across the two: the engines don't agree with each other — misaki
    # ˌɪmpəɹˈɑɾəɹ, espeak ɪmpˈɜɹAɾəɹ ("im-PER-ay-der", an /eɪ/ and a flapped
    # t). "Em-per-ah-tor" is ˈɛmpɜɹˌɑtˈɔɹ / ˈɛmpɜɹˈɑtˈɔɹ — the same segments
    # on both, differing only in whether the third chunk takes primary or
    # secondary stress. That is a split of the kind this file usually
    # rejects, and it is accepted here because the alternative that lands
    # identically, "Emper-ah-tor", does it by doubling the rhotic
    # (ˈɛmpəɹɹˈɑtˈɔɹ) — an audible trill against an inaudible stress mark.
    "Imperator": "Em-per-ah-tor",
    #
    # Fourth pass, down to the 200-a-dump line. Liyue and Inazuma first:
    # 250: kˈɪksɪŋ on both — the pinyin q read as /k/ and the x as /ks/, so
    # the Liyue government comes out "KIK-sing". "Chee-shing" is ʧˈiʃˈɪŋ.
    "Qixing": "Chee-shing",
    # 253: wˈæŋɡʃu, the flat a. "Wahng-shoo" is wˈɑŋʃˈu on both.
    "Wangshu": "Wahng-shoo",
    # 218: fˈAjʌn — the ei read as /eɪ/ and the un clipped.
    # "Fay-yoon" is fˈAjˈun on both.
    "Feiyun": "Fay-yoon",
    # 275: tˈɛməɹɹi, espeak's doubled rhotic. "Tem-ah-ree" is tˈɛmˈɑɹˈi on
    # both; "Teh-mah-ree" is tˈAmˈɑɹˈi, the chunk-final "eh" trap again.
    "Temari": "Tem-ah-ree",
    # 264: sˈæŋɡO. "Sahn-go" is sˈɑŋɡˈO on both.
    "Sango": "Sahn-go",
    # 212: kˈænʤu. "Kahn-joh" is kˈɑnʤˈO on both.
    "Kanjou": "Kahn-joh",
    # 215: ˌɑnɪkəbjˈuɾO — a /bju/ where the beetle has "boo", and the t
    # flapped. "Oh-nee-kah-boo-toh" is ˈOnˈikˈɑbˈutˈO on both.
    "Onikabuto": "Oh-nee-kah-boo-toh",
    # Sumeru:
    # 223: hˈænɪjjə. "Hah-nee-yah" is hˈɑnˈijˈɑ on both.
    "Haniyyah": "Hah-nee-yah",
    # 211: sˈæbzəɹɹˌʌz — flat a and a doubled rhotic. "Sahb-zuh-rooz" is
    # sˈɑbzˈʌɹˈuz on both; "Sahb-zeh-rooz" puts an /eɪ/ in the middle.
    "Sabzeruz": "Sahb-zuh-rooz",
    # 203: jˌæsnəpˈɑɾi — flat a and a flapped t. "Yahs-nahp-ah-tee" is
    # jˈɑznˈɑpˈɑtˈi on both. Chunked "-nahp-" and not "-nah-", for the
    # reason the "Nasha" entry above records.
    "Yasnapati": "Yahs-nahp-ah-tee",
    # 259 entries in the Genshin dump, 255 of them dialogue-shaped, and the
    # reading was `kˌAˈAʧvˈæɹɛnə` on both engines — the "Kh" spelled out as
    # LETTERS, "KAY-AY-CH-varena". The worst reading the scan turned up.
    #
    # It is also the one word here with no voiced line to match: the user
    # reports the term appears only in unvoiced dialogue, which is exactly
    # the text this app exists to read — so HoyoVoice is the only voice that
    # ever says it, and the respelling answers to the source rather than to
    # a VO. Wikipedia gives the Avestan as xᵛarənah-: a labialized voiceless
    # velar fricative, which English has no letter for and every g2p here
    # refuses. /kw/ is the ordinary English stand-in for it (the same one
    # that turns Khwarezm into "Kwarezm"), and it keeps the schwa the
    # Avestan spelling has. "Kwah-ruh-nah" is kwˈɑɹˈʌnˈɑ on both.
    #
    # Measured and available to swap in: "Ka-var-na" (kˈɑvˈɑɹnˈɑ,
    # "kah-VAR-nah") drops the schwa and one syllable, and "Kwar-uh-nah"
    # (kwˈɔɹˈʌnˈɑ) opens the first vowel to the "or" of "war". The two
    # spellings that keep the h — "Khwah-ruh-nah", "Hwah-ruh-nah" — are
    # spelled out letter by letter (ˌAˈAʧw…, ˈAʧw…), the initial-cluster
    # trap this file's header warns about.
    "Khvarena": "Kwah-ruh-nah",
    # 919, and both engines say ənˈimO — "uh-NEE-moh", where the element is
    # "AN-uh-moh". Cryo (kɹˈIO), Dendro (dˈɛndɹO) and Geo (ʤˈiO) were
    # checked at the same time and are already right.
    "Anemo": "Ann-uh-moh",
    # 525: both engines read the abbreviation as a WORD — ˈW ˈi, "ow-ee".
    # Expanded rather than spelled, since that is what it stands for.
    "AoE": "area of effect",
    # 1,314: misaki spells it out (ˌɑɹˌiˈɛs), espeak says ɹˈɛz. Players say
    # "rez", so espeak has this one right and the entry gives it to both.
    "RES": "rez",
    # 894: fAvˈOniəs — "fay-VOH-nee-us", the first vowel English.
    "Favonius": "Fah-voh-nee-us",
    # 826: kɹˈɛmnOz — the final s voiced to a z.
    "Kremnos": "Krem-noss",
    # 693: mˈɛɹʧəsˌi — "MERCH-uh-see" for a French word. The user's gloss
    # ships as written: "Ma-ray-shaussay" is mˈɑɹˈAʃˈɔsA on both. (An
    # earlier "Mar-uh-shoh-say" doubled the rhotic, mˈɑɹɹˈʌ-.)
    "Marechaussee": "Ma-ray-shaussay",
    # 1,633 between them: mˈAŋkɪn — "MAY-nkin", where the word is the
    # mannequin. The feminine form needs its own entry.
    "Manekin": "Man-uh-kin",
    "Manekina": "Man-uh-kee-nah",
    # 172: bɑɹbˈɑɾOz — "bar-BAH-doze", the t flapped. The z ending is
    # right and stays; what was wrong is the middle vowel. "bar-bay-tohz"
    # is bˈɑɹbˈAtˈOz on both.
    "Barbatos": "bar-bay-tohz",
    # 168: dˈʌnjɑɹzˌæd — "DUN-yar-zad", English vowels throughout.
    "Dunyarzad": "doon-yar-zahd",
    # 197: ɪnˈæzjumən — the nation is "Ee-nah-zoo-mah" above, and the
    # demonym has to follow it.
    "Inazuman": "Ee-nah-zoo-mun",
    # 194: fɔntˈAniən. Keyed to match the "Fontaine" entry above, which is
    # the French "Fon-ten".
    "Fontainian": "Fon-ten-ee-un",
    # The seventh pass took the ear-only cases in a batch. All eight are
    # invented or foreign words both engines guess at identically, so the
    # gloss IS the answer — and three of the eight could not ship as the
    # user spelled them, all three for the same reason this file's header
    # gives: a chunk-final "eh" is /eɪ/.
    # 1,238: ˈɑkhəmə — "OCK-huh-muh", the h sounded. "ah-kem-ah" is
    # ˈɑkˈɛmˈɑ on both; the gloss "ah-keh-ma" is ˈɑkˈAmˈɑ, "ah-KAY-mah".
    "Okhema": "ah-kem-ah",
    # 931: kɹˈɪsOz — "KRIS-ohz". "cry-sohss" is kɹˈIsˈOs on both; "cry-sohs"
    # as glossed voices the final s to a z (kɹˈIsˈOz), which is the fault
    # the entry exists to remove.
    "Chrysos": "cry-sohss",
    # 178: kjˈulˈɪpɑθ — "kyoo-LIP-oth", the q read as /kj/. "klepoth" is
    # klˈɛpɑθ on both. Unhyphenated, because "kleh-poth" is klˈApˈɑθ —
    # "KLAY-poth", the chunk-final "eh" trap for the third time in this
    # file, and "kle-poth" (klˈipˈɑθ) closes the vowel to the e of "see".
    "Qlipoth": "klepoth",
    # 505: sˈɔɹʌʃ — "SOR-ush". "So-roosh" is sˌOɹˈuʃ on both, as glossed.
    "Sorush": "So-roosh",
    # 187: ʃˈɛvɹus — the stress on the first syllable. "shev-rooz" is
    # ʃˈɛvɹˈuz on both: the stress moved and the s voiced, which is the
    # French. (An earlier "Shev-ress" was the wrong vowel entirely.)
    "Chevreuse": "shev-rooz",
    # 1,603: hˈɛŋ, the e of "bed", where the pinyin is the u of "hung".
    "Heng": "Hung",
    # 857: plˌAnɑɹkˈAdiə — "PLAY-nar-kay-dee-uh". "Plan-ar-kadia" is
    # plˈænˈɑɹkˈAdiə on both, as glossed.
    "Planarcadia": "Plan-ar-kadia",
    # 89, and the one this batch had to look up rather than hear:
    # Wikipedia gives the Nahuatl as /tiˈsosik/, where both engines say
    # tɪzˈɑsɪk — "tih-ZAH-sik", a z for the s and both i's English.
    # "tee-soh-seek" is tˌisˈOsˈik / tˈisˈOsˈik: the same segments in the
    # same order as the source, differing only in which chunk each engine
    # marks. 80 of the 89 are "Tizocic II", which the numeral entry above
    # finishes as "tee-soh-seek Two".
    "Tizocic": "tee-soh-seek",
    #
    # Measured against their glosses and left OUT, because the engines
    # already say exactly that: "Bronya" bɹˈɑnjə ("brawn-ya"), "Columbina"
    # kˌɑləmbˈinə, "Luka" lˈukə, "Aurum" ˈɔɹəm, "Clockie" klˈɑki and
    # "Raiden" ɹˈAdən ("RAY-den" — the glossed "Rai-den" is the same phones
    # on both engines).
    # Eighth pass, clearing the last of the 200-a-dump floor. Liyue and
    # Inazuma again:
    # 220: ɡˈIʌn — "GUY-un" for 孤云. "Goo-yoon" is ɡˈujˈun on both.
    "Guyun": "Goo-yoon",
    # 292: ɡjˈuhjuə. "Goohwah" is ɡˈuhwə on both — unhyphenated, because a
    # chunk STARTING "hw" is spelled out: the glossed "Goo-hwa" reads
    # ɡˈuˌAʧdˌʌbᵊljˌuˈA, "goo-AITCH-DOUBLE-YOU-ay".
    "Guhua": "Goohwah",
    # 218: ʧˈɛnɪˌu. "Chen-yoo" is ʧˈɛnjˈu on both.
    "Chenyu": "Chen-yoo",
    # 298: kˌɪʧɪbˈWʃi — "kich-ih-BOW-shee".
    "Kichiboushi": "Kee-chee-bow-shee",
    # 234: jˈWkI — "YOW-kye" for the Japanese 妖怪.
    "youkai": "yoh-kye",
    # Sumeru and Natlan:
    # 225: kjˌusənˈɑli — a /kj/ onset the name does not have.
    "Kusanali": "Koo-sah-na-lee",
    # 237: kˈɑənɹˌiə — the ae swallowed. "Kon-ree-ah" is kˈɑnɹˈiˈɑ on both,
    # and is the user's ear; an earlier "Kay-en-ree-ah" (kˈAˈɛnɹˈiˈɑ) put a
    # syllable in that nobody says.
    "Khaenri'ah": "Kon-ree-ah",
    # 206: lˈæwəʧˌɜɹl, the flat a of "fat" on a hilichurl variant.
    # "Lah-wah-cherl" is lˈɑwˈɑʧˈɜɹl on both. The glossed "La-wa-cherl"
    # keeps the flat a the entry exists to remove (lˌæwˈɑʧˈɜɹl).
    "Lawachurl": "Lah-wah-cherl",
    # 277: pɹˈæmæd, the flat a twice over.
    "Pramad": "Prah-mahd",
    # 379: sˈɪkɹAn — "SICK-rain", where the Liyue bird is a cy-crane.
    # "sigh-crane" is sˌIkɹˈAn / sˈIkɹˈAn.
    "cycrane": "sigh-krane",
    # 273: dədˈOkO — the first syllable reduced to a schwa.
    "Dodoco": "doh-doh-ko",
    # Star Rail:
    # 286: bˈɑɹθəlˌOz — the middle vowel reduced to a schwa. "bar-thoh-lowz"
    # is bˈɑɹθˈOlˈOz on both; the glossed "bar-tho-lowz" voices the th to
    # the ð of "the" (bˈɑɹðˈOlˈOz), so the h keeps its o.
    "Bartholos": "bar-thoh-lowz",
    # 244: ˈɔɹmOz — the stress on the first syllable. "Or-moze" is ɔɹmˈOz on
    # both; the glossed "oh-moz" drops the r altogether (ˈOmˈɑz).
    "Ormos": "Or-moze",
    # 233: ˈIəɹntum — "EAR-ntoom", the compound fused. Split into the two
    # words it is: ˈIəɹn tˈum on both.
    "Irontomb": "Iron tomb",
    #
    # Four at this floor have no spelling that survives both engines and
    # are left alone: "Tenryou" (447) — "Ten-ryoh" is tˈɛnɹˈIO, the /aɪ/ of
    # "rye", and "Ten-rio" buys a syllable; "Jueyun" (222), where every
    # spelling of the jue- onset either spells out or lands an /eɪ/;
    # "Deshret" (324), whose sh collapses to an s the moment the word is
    # hyphenated (dˈɛsɹˈɛt); and "Aether" (437), which is ˈiθə already —
    # only the final r is missing, and "Ee-ther" voices the th.
    # Fontaine, Nod-Krai, and a Star Rail planet:
    # 306 and 206 — mˈɛlusˌIn(z), "MEL-oo-sine", where the Fontaine species
    # ends on the vowel of "seen" and a z. "Mel-oo-zeen" is mˈɛlˈuzˈin on
    # both; the plural needs its own entry, substitution being word-bounded.
    "Melusine": "Mel-oo-zeen",
    "Melusines": "Mel-oo-zeens",
    # 237: ɡˈɑɹdiənɪʤ — the French swallowed into "-ee-uh-nidge".
    # "Gar-din-nahj" is ɡˈɑɹdˈɪnnˈɑʤ on both.
    "Gardiennage": "Gar-din-nahj",
    # 231: snˈɛʒnəɡɹˌæd — the zh is right (it is right in "Snezhnaya" too),
    # the -grad is the flat a of "fat". "Snezh-noh-grahd" is snˈɛʒnˈOɡɹˈɑd.
    "Snezhnograd": "Snezh-noh-grahd",
    # 234: ʤɑɹɹˈɪlOvˌiˈI — a doubled rhotic, and the numeral read as the
    # LETTERS, "vee-eye". "Ja-rillo Six" is jˈɑɹˈɪlO sˈɪks on both.
    "Jarilo-VI": "Ja-rillo Six",
    # 886, and both engines make the same mess of it: the damage-over-time
    # abbreviation is dˌutˈi / dˈu tˈi — "doo-tee". Spelled out rather than
    # said as a word ("dot" shipped first and was heard as the wrong thing):
    # "dee-oh-tee" is dˌiˈOtˈi / dˈiˈOtˈi.
    "DoT": "dee-oh-tee",
    #
    # Then the ones that are ORDINARY English words, wrong on Windows only —
    # the `split` class of the scan, and the reason it exists. A split has a
    # right answer that does not need an ear: one engine has the word in a
    # human-curated lexicon and the other is guessing, so the respelling
    # reproduces the lexicon's reading on both platforms rather than
    # inventing a third (see "Acheron" above, and "calm" below, where the
    # engine holding the right answer is espeak). Keys are
    # lowercase like "shaman" above: they are common nouns, --custom-words
    # should not pin them in the OCR vocabulary, and a capitalised
    # replacement mid-sentence reads as a name.
    # 727 in the Star Rail dump: misaki says æmbɹˈOʒiəl, espeak æmbɹˈOsiəl —
    # "am-BRO-see-ul", the /ʒ/ of "measure" hardened to an s.
    # "Am-broh-zhul" is æmbɹˈOʒˈʌl on both.
    "ambrosial": "am-broh-zhul",
    # 450: misaki kˈAlɪks, espeak kˈælɪks — "KAL-ix" for a word that opens on
    # the vowel of "cake". "Kay-lix" is kˈAlˈɪks on both.
    "calyx": "kay-lix",
    "calyxes": "kay-lixes",
    # 529 across both: misaki kɹˈɪmzᵊn, espeak kɹˈɪmsən — an s where the word
    # has a z. "Krim-zun" is kɹˈɪmzˈʌn on both.
    "crimson": "krim-zun",
    # 368: misaki ˈɛɹəmˌIt, espeak ɪɹˈɛmIt — "ih-REM-ite", the stress a
    # syllable late. "Airuh-mite" is ˈɛɹʌmˈIt on both; hyphenating the middle
    # chunk splits the stress ("Air-uh-mite" is misaki ˈɛɹˌʌmˈIt against
    # espeak ˈɛɹˈʌmˈIt).
    "eremite": "airuh-mite",
    "eremites": "airuh-mites",
    # 385: misaki ʃˈOɡən, espeak ʃˈɑɡʌn — "SHAH-gun". "Shoh-gun" is ʃˈOɡˈʌn
    # on both.
    "shogun": "shoh-gun",
    # 323: espeak pɹɪmˈɔɹdiəl, "prih-MOR-dee-ul", where the word opens on
    # the /aɪ/ of "pry". "pry-mordial" is pɹˈImˈɔɹdiəl on both.
    "primordial": "pry-mordial",
    # 324: espeak ʃˈɑɡənˌAt — "SHAH-guh-nate", both vowels wrong; the bare
    # "shogun" has its own entry above. "shoh-guh-nit" is ʃˈOɡˈʌnˈɪt.
    "shogunate": "shoh-guh-nit",
    # 296, and the one entry in this file where MACOS is the broken side:
    # misaki sounds the l (kˈɑlm, "kalm") where espeak has it right at
    # kˈɑm. "kahm" is kˈɑm on both.
    "calm": "kahm",
    # 277: espeak θænˈɑɾOz, "than-AH-tohz" — the stress a syllable late and
    # the s voiced. "Thanna-toss" is θˈænətˈɔs on both. NOT "Than-uh-toss",
    # which turns the opening into the voiced th of "the" (ðˌənˈʌtˈɔs).
    "Thanatos": "Thanna-toss",
    # 256: espeak pɹɪsmˈæɾɪk, an s where the word has a z.
    # "priz-matic" is pɹˈɪzmˈæɾɪk on both.
    "prismatic": "priz-matic",
    # 256: espeak stˈæɾəs — "STAT-us", the flat a of "fat", and misaki's
    # stˈAɾəs is "STAY-tus". Neither is the reading by ear. "stah-toose" is
    # stˈɑtˈus on both; "stah-toos" as glossed voices the ending (stˈɑtˈuz).
    "status": "stah-toose",
    # 248: espeak mˈædəm — "MAD-um", the English noun rather than the
    # French address Fontaine uses it as. "muh-dahm" is mˈʌdˈɑm on both.
    "madame": "muh-dahm",
    # 212: espeak dᵻvˈɪnəɹ — "duh-VIN-er", where the reader of fortunes is
    # "di-VINE-er". "di-vyne-er" is dˌɪvˈInˈɜɹ on both.
    "diviner": "di-vyne-er",
    #
    # The fifth pass took this class rather than the names, because a word
    # that is wrong in ORDINARY dialogue is said far more often than any
    # proper noun. Wrong on Windows:
    # 775: espeak sˈɛɹᵻməni — "SER-ih-muh-nee", the third syllable gone.
    "ceremony": "sair-uh-moh-nee",
    # 531: espeak spˈisiz — "SPEE-sees", an s where the word has a /ʃ/.
    "species": "spee-sheez",
    # 457: espeak ˈɑnvəlˌOp — "ON-vuh-lope".
    "envelope": "en-vuh-lope",
    # 729 between them, and the entry that changed sides. espeak drops the
    # /ɡ/ (səʤˈɛst) where misaki keeps it (səɡʤˈɛst), and a first pass
    # restored the /ɡ/ on both — then the audition said espeak had it
    # right and the g does not belong. "sa-jest" is sˈɑʤˈɛst on both, the
    # user's spelling as written; it opens the first vowel and takes the
    # stress, where "suh-jest" (sˌʌʤˈɛst / sˈʌʤˈɛst) is the unstressed
    # schwa and splits a stress mark. The -ing form is the reason an entry
    # is still needed at all: BOTH engines drop the g there.
    "suggest": "sa-jest",
    "suggested": "sa-jested",
    # 427: espeak ˈɑɹɾɪsənʃˌɪp reduces the second vowel to nothing. The s
    # is right by ear and the first respelling's z was not. NOT
    # "ar-teh-san-ship" as glossed — a chunk-final "eh" is /eɪ/, so that is
    # ˈɑɹtˈAsˌænʃˈɪp, "ar-TAY-san-ship".
    "artisanship": "ar-tuh-san-ship",
    # 3,004 in the Star Rail dump, plus 515 possessives — the second most
    # common fault in either game after "they're", and the scan hid it for
    # five passes: all-caps words were skipped wholesale as "read out as
    # letters", which is true of DMG, ATK and TCG and false here. espeak
    # tries to SAY it: ˈɪpk, three letters mashed into one syllable, where
    # misaki spells it out (ˌIpˌisˈi). The company is said aloud by the
    # characters, so the initialism is what the respelling reproduces.
    # Keyed on the bare form only: it fires inside the possessive too and
    # leaves "eye-pee-see's", which is ˌIpˈisˈiz — the identical phones an
    # "IPC's" entry would have produced (cf. the "Yae" entry above).
    "IPC": "eye-pee-see",
    # 718 between the capitalised and lowercase forms: espeak səlˈɛstjᵊl,
    # "suh-LEST-yul", where the ti is the /tʃ/ of "church".
    "celestial": "suh-les-chul",
    # 345: espeak ɛkskwˈɪsɪt — an s for the z.
    "exquisite": "ex-kwiz-it",
    # 311: espeak fˈAsd — the -ced ending voiced to a d.
    "faced": "fayst",
    # 298: espeak ɹᵻsˈɪstəns — an s for the z again.
    "resistance": "rih-zis-tunce",
    # 270: espeak pɹˈOɾəɡənˌɪst — "PRO-tuh-guh-nist", stress on the first
    # syllable and a flapped t.
    "protagonist": "pruh-tag-uh-nist",
    #
    # And four where MACOS is the broken side, fixed the same way — the
    # engine holding the right answer is espeak, and the respelling
    # reproduces it on both:
    # 411: misaki skˈiz — "skeez", where the plural of sky is skˈIz.
    "skies": "skyze",
    # 370: espeak ˈIdɑlən clips the middle vowel; misaki's IdˈOlən has it
    # right. "eye-doh-lon" is ˈIdˈOlˈɑn on both.
    "Eidolon": "eye-doh-lon",
    # 292: misaki ˈɑbztəkᵊlz — "obz-tuh-kulz", a z where the word has an s.
    "obstacles": "ob-stuh-kulz",
    # 269: misaki dəskˈIz — "dis-KYZE", a hard k where the word has a g.
    # Spelled "-guyze" because "-gyze" is read as a /ʤ/ (dˈɪsʤˈIz).
    "disguise": "dis-guyze",
    #
    # Sixth pass, same class, deeper. A word family needs one entry per
    # form — substitution is word-bounded — so the -s and -ed forms are
    # here beside their stems.
    # 764 across the family: espeak reads the s as an s where "absorb" has
    # a z (əbsˈɔɹb). Unhyphenated: "ab-zorb" splits the first vowel
    # (misaki ˌɑb- against espeak ˈæb-), where "abzorb" is əbzˈɔɹb on both
    # — misaki's own reading, exactly.
    "absorb": "abzorb",
    "absorbs": "abzorbs",
    "absorbed": "abzorbed",
    "absorbing": "abzorbing",
    # 447: espeak ʤˈænəs — "JAN-us" for the two-faced god. "Jay-nuss" is
    # ʤˈAnˈʌs on both; "Jay-nus" reads the last chunk as "nooz" on misaki.
    "Janus": "Jay-nuss",
    # the same four-form family, keyed one per form as always.
    "suggests": "sa-jests",
    "suggesting": "sa-jesting",
    # 379 between them: espeak pɹˈɛɹ is right for the petition and misaki
    # pɹˈAəɹ is the one who prays — the games mean the petition.
    "prayer": "prair",
    "prayers": "prairs",
    # 211, the singular of an entry made last pass: misaki ˈɑbztəkᵊl.
    "obstacle": "ob-stuh-kul",
    # 251 between them: espeak mˈiɾɪˌɔɹIt — "MEE-tih-or-ite".
    "meteorite": "mee-tee-oh-rite",
    "meteorites": "mee-tee-oh-rites",
    # 185: espeak ˈOʃənˌɪd — "OH-shun-id", the ce read as a /ʃ/, where the
    # Genshin water spirit is "oh-SEE-uh-nid".
    "Oceanid": "oh-see-uh-nid",
    # 180: espeak nIˈiv — "nye-EEV". "nah-eev" is nˈɑˈiv on both;
    # "nah-eve" splits the first vowel the way "ab-zorb" does.
    "naive": "nah-eev",
    # 176: espeak fInˈænʃᵊl — "fye-NAN-shul".
    "financial": "fuh-nan-shul",
    # 163: espeak θˈʌɹOli — "thuh-ROH-lee".
    "thoroughly": "thur-uh-lee",
    # 159: espeak ˌɪntəfˈɪɹ — the first r dropped. ("interference" has the
    # same fault and no fix: every spelling of the "-ence" tail adds a
    # vowel after the s, ˌɪntəɹfˈɪɹɛnsˈɛ.)
    "interfere": "inter-feer",
    # 157: espeak vˈɪp — said as a word, "vip", where it is three letters.
    "VIP": "vee-eye-pee",
    # Roman numerals, and neither engine reads one: misaki spells the
    # letters (vˌiˌIˈI for VII, ˌIˈɛks for IX) and espeak announces the
    # system — ɹˌOmən sˈɛvən, "ROMAN SEVEN", ɹˌOmən ɪlˈɛvən for XI. 1,664
    # of them across the two dumps, in chapter titles and place names.
    # These are the ONLY entries here that must be exact-case: matching is
    # case-insensitive by default and the Genshin dump has 13 "Xi" and 15
    # "Ix", which would become "Eleven" and "Nine". They go in
    # pronunciations_exact below with "Gaming".
    # II and III can be keyed bare: neither is an English word. I, V and X
    # cannot. "I" is the PRONOUN — 278,936 of them in the dialogue-shaped
    # lines against roughly 340 numerals — so it is keyed only in the
    # containers the games actually number, measured off the dumps: "Act I"
    # (95), "Part I" (67), "Zone I" (53), "Phase I" (48), "Mode I" (48),
    # "Room I" (16), "Chapter I" (8), "Volume I" (2). "Part I" is pˈɑɹt ˌI,
    # "part EYE", where "Part One" is pˈɑɹt wˈʌn. Nine of those lines are
    # prose rather than a title ("Act I" followed by a lowercase word), and
    # they will now read "Act One" — the price of the other 330.
    #
    # V and X are left alone entirely: 501 between them, mostly not
    # numerals at all, and a bare key would reach into "X-ray", "X-Axis"
    # and "V-shaped" (12 such lines). Their containers can be keyed the
    # same way as I if anyone wants them.
    "II": "Two",
    "III": "Three",
    "Act I": "Act One",
    "Part I": "Part One",
    "Zone I": "Zone One",
    "Phase I": "Phase One",
    "Mode I": "Mode One",
    "Room I": "Room One",
    "Chapter I": "Chapter One",
    "Volume I": "Volume One",
    "IV": "Four",
    "VI": "Six",
    "VII": "Seven",
    "VIII": "Eight",
    "IX": "Nine",
    "XI": "Eleven",
    # 156: espeak ɹᵻsˈɪʤuᵊl — an s for the z again.
    "residual": "rih-zij-oo-ul",
    # 154: espeak stɹˈæɾAʤəmz — "STRAT-ay-jemz".
    "Stratagems": "strat-uh-jemz",
    # 153: espeak pɹˌiɹˈɛkwɪsˌɪt — s for z, and the last vowel full.
    "prerequisite": "pre-rek-wiz-it",
    # 149: espeak blˈæzɑɹ — "BLAZ-ar" for what astronomy says "BLAY-zar".
    "Blazar": "Blay-zar",
    # 143: espeak nˈuz — "nooz", where the Star Rail term is Greek νοῦς and
    # ends on an s. Respelled to the ordinary word that sounds like it.
    "Nous": "noose",
    # 121: espeak dˈɑɹʃən — the second vowel reduced to a schwa.
    "Darshan": "Dar-shahn",
    # 120: misaki reads the contraction wˌʌtɹˌA, "what-ray". espeak's
    # wˌʌɾəɹ is not a mistake at all — "wutter" is what the contraction
    # sounds like in speech — so this reproduces it rather than expanding
    # to "what are", which is the formal reading nobody says. "wuttr" is
    # wˈʌɾəɹ on both.
    "What're": "wuttr",
    #
    # Four more where macOS is the broken side:
    # 145: misaki hˈæntsəm inserts a /t/; espeak sounds the d. "han-sum"
    # is the silent-d reading both ways.
    "handsome": "han-sum",
    # 139: misaki hˈæmpstəɹ — an inserted p, "HAMP-ster".
    "Hamster": "Ham-ster",
    # 137: misaki hˈʌzbᵊnd — a z where the word has an s.
    "husband": "huss-bund",
    # 123: misaki ɑɹkˈAnə — "ar-KAY-nuh".
    "Arcana": "ar-kah-nuh",
    #
    # 186: espeak pɹˈisiəns — "PREE-see-uhns". "presh-inz" is pɹˈɛʃˈɪnts on
    # both. The tail is the compromise: every spelling of "-ence"/"-ense"
    # adds a vowel after the s (pɹˈɛʃʌnsˈi), and "-inz" buys a /t/ before
    # the s instead, which is the smaller wrong. The user's own "preh-ssh-inz"
    # is not the spelling that ships: a chunk of bare consonants is read as
    # LETTERS, pɹˈAˌɛsˌɛsˈAʧˈɪnts — "pray-S-S-AITCH-ints".
    "Prescience": "presh-inz",
    # 155: espeak ˌɪntəfˈɪɹəns drops the first r. "in-ter-fear-anss" is
    # ɪntˈɜɹfˈɪɹˈæns on both — the user's gloss with its last two chunks
    # joined, because a chunk written "ss" is read as "ESS-ESS"
    # (…ənˌɛsˈɛs), the same letter-spelling trap as above.
    "interference": "in-ter-fear-anss",
    #
    # "paths" (860) is the one an earlier pass could not fix and is left alone:
    # espeak says pˈæθs where the plural is pˈæðz, and no respelling gets
    # the voiced th back — "pathz" keeps the θ on both engines, which would
    # trade Windows' wrong s for macOS's right ð and gain nothing.
    # 3,336 across the two dumps, and the most common word in either that
    # Windows says wrong: espeak reads the contraction ðAəɹ, "THAY-er",
    # in running text as well as alone ("They're coming." is ðAəɹ kˈʌmɪŋ).
    # misaki says ðˌɛɹ and is right. Respelled to the ordinary homophone,
    # which is ðˈɛɹ on both — the log, dedupe and casting keep "they're".
    "they're": "There",
    # 530: vˌɪdiədhˈɑɹɹə — doubled rhotic again, and the dh read as its own
    # syllable. "Vid-yah-dah-rah" is vˈɪdjˌɑdˌɑɹˈɑ / vˈɪdjˈɑdˈɑɹˈɑ, one r.
    "Vidyadhara": "Vid-yah-dah-rah",
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
    # superseded the same way, and for the same reason: "Ruan", "Kamisato",
    # "Ayaka" and "Ayato" all have entries of their own now, dialogue uses
    # them far more often than the full names, and a shorter key sorts first
    # — so these three could never match again anyway.
    "Ruan Mei": "Rwahn May",
    "Kamisato Ayaka": "Kah-mee-sah-toh Ah-yah-kah",
    "Kamisato Ayato": "Kah-mee-sah-toh Ah-yah-toh",
    # the rest of the full-name keys, retired as their halves got entries.
    # "Kuki Shinobu" is the one that stays: "Kuki" alone is already kˈuki on
    # both engines and needs no entry, so nothing sorts ahead of it.
    "Kaedehara Kazuha": "Kah-eh-deh-hah-rah Kah-zoo-hah",
    "Kujou Sara": "Koo-joh Sah-rah",
    "Sangonomiya Kokomi": "Sahn-go-no-mee-yah Ko-ko-mee",
    "Shikanoin Heizou": "Shee-kah-no-een Hay-zoh",
    "Yumemizuki Mizuki": "Yoo-meh-mee-zoo-kee Mee-zoo-kee",
    # withdrawn the same way, and for the same kind of reason: "Sara" is
    # sˈɛɹə already — the English "Serra" — and the entry gave the
    # Commissioner a Japanese "Sah-rah" nobody asked for. "Kujou" keeps its
    # own entry, so the full name still reads.
    "Sara": "Sah-rah",
    # withdrawn rather than superseded: the flat-a tell was wrong about
    # "Chasca" and the name needs no entry at all (see CLEARED below). It
    # shipped for one revision, so it has to be retired by name or --write
    # would leave it in every voices.json that already took it.
    "Chasca": "Chaz-kuh",
}

# Checked against both engines and deliberately given NO entry, because the
# reading is already right (or, for the last group, because no respelling
# survives both engines — each one's reason is in a comment beside the
# entries above). tools/textmap_words.py reads this set and stops reporting
# them: without it every scan re-lists the same 80-odd words a person has
# already ruled on, and the floor of the candidate list never falls.
CLEARED = {
    # read correctly as they stand
    "Amphoreus", "Fragmentum", "Trailblaze", "Silvermane", "Coreflame",
    "Dreamville", "Dragonspine", "Windblume", "Windtrace", "Scalegorge",
    "Ashveil", "Phantasmoon", "Mechanicus", "Teyvat", "Ley", "Mei", "Mei's",
    "Yang", "Sparxie", "Sparxicle", "Sampo", "Graphia", "Aino", "Hyacine",
    "Maison", "Natasha", "Jahoda", "Zagreus", "Alhaitham", "Bronya",
    "Columbina", "Luka", "Aurum", "Clockie", "Clockie's", "Raiden",
    "Millelith", "adepti", "adeptus", "Adeptus", "Hilichurl", "hilichurl",
    "hilichurls", "Nod-Krai", "Invokation", "Ningguang", "Miko", "Klee",
    "Cyno", "Geo", "Cryo", "Dendro", "Seelie", "Layla", "Arlan", "Monsieur",
    "Siobhan", "Bennett", "Argenti", "Lesley", "Diona", "Rin", "Thoma",
    "Gorou", "Kairagi", "Yoimiya", "Wanmin", "Yunli", "Yukong", "Lyney",
    "Ororon", "Styxia", "Xavier", "Cocolia", "Varka", "Guang", "Wispae",
    # Chasca is the flat-a tell's false positive: the name is Quechua and
    # ʧˈæskə IS "CHASS-kuh". It carried an entry for one revision and lost
    # it, because every respelling is worse than the default — doubling
    # the s turns the ch into a /ʃ/ ("Chasska" is ʃˈæskə), a capital
    # inside the chunk spells it out (sˌiˈAʧ əskˈæ), and opening the a
    # ("Chahsska", ʧˈɑskə) is a different name.
    "Chasca", "Sara",
    "wispae", "Mary-Ann", "Gallagher", "Odette", "Hanu", "Aeon", "Aeons",
    # laughter and hesitation: already read as themselves
    "Hehe", "hehe", "Heh", "heh", "Hehehe", "Hahaha", "hahaha", "Hahahaha",
    "Hee-hee", "Hmm", "hmm", "Umm", "Ohh", "Argh", "Agh",
    # ordinary English where both readings are legitimate
    "route", "routes", "cosmos", "Cosmos", "restaurant", "Restaurant",
    "comfortable", "uncomfortable", "yourself", "somewhat", "cursed",
    "teammates", "objective", "objectives", "corridor", "Corridor",
    "exploration", "Exploration", "everybody", "somebody", "prosperity",
    "shan't", "prototype", "Voracity", "President", "president", "Domain",
    "domain", "domains", "Domains", "Divergent", "Neuvillette", "Whew",
    "Fungi", "SoulGlad", "phenomenon", "hide-and-seek", "immortal",
    "illegal", "Planarcadia",
    # the "final e dropped" tell fires on every 've contraction, and every
    # one of them is already right (wˈʊdəv is "would-uv")
    "would've", "must've", "could've", "should've", "who've", "might've",
    # compounds and fragments the tell misreads: "trashcan" is tɹˈæʃkæn,
    # which is the word; "th's" is a tokenizer stub off an ordinal; and the
    # stray ” in "enemies'" is a quote character in the dump, not a reading
    "trashcan", "trashcans", "th's", "enemies'", "Janus'", "Interastral",
    # no respelling survives both engines — see the comments above
    "paths", "Paths", "truths", "townsfolk", "Blouse", "Wardance",
    "Tenryou", "Jueyun", "Deshret", "Aether", "interfering",
}

# Names that are also ordinary English words. Matching is case-insensitive by
# default (OCR case jitter shouldn't lose a name), which would respell the
# common word too — "the gaming table" is not the Liyue chef. These match the
# capitalised spelling only. Any future entry for Jade, Sunday, Hook, Blade,
# Archer, Robin or March 7th belongs here as well.
EXACT = ["Gaming", "II", "III", "IV", "VI", "VII", "VIII", "IX", "XI",
         # the numbered containers too: matching is case-insensitive by
         # default, and "the act i performed" would otherwise come out
         # "the Act One performed".
         "Act I", "Part I", "Zone I", "Phase I", "Mode I", "Room I",
         "Chapter I", "Volume I"]

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
