# Changelog

All notable changes to HoyoVoice are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).
Add entries under **Unreleased** as you work; move them into a dated version section when you tag a release.
Versions 0.1.0 and 0.2.0 predate tagging; every section from 0.3.0 on has a matching `vX.Y.Z` git tag.

## [Unreleased]

### Added

- **Star Rail's phone Messages app is read — the regular character
  chats.** It had no screen of its own and fell through to the dialogue
  classifier, which in one minute of the 2026-08-28 14:14 session
  (rec_20260828_141426) spoke the thread header as a line in the
  player's voice ("Rin iTahsaka", 14:15:01), auto-cast a
  conversation-list preview as a speaker ("This is way too cute"),
  auto-cast a delivery notice as another ("Message" → zm_yunxi, which
  then said Rin's closing line), and read the player's own sent bubbles
  back to them as Trailblazer choice prompts, since a right-hanging
  bubble lands squarely in the choice band. Nine of Rin Tohsaka's ten
  messages were never read at all.

  It is the same incremental reader the in-story "Answer" panel uses, so
  settling, dedupe and per-sender voices come for free; only the layout
  is new, and Star Rail now has two chat panels behind one
  `classify_chat`. Rows are sorted by what they are ALIGNED to rather
  than by which side of a threshold they fall on — the pane has four
  alignments (sender label 0.367, incoming bubble 0.379, player bubble
  right-aligned 0.867, player name label right-aligned 0.882) and a
  row's own width is irrelevant to all of them. A threshold was tried
  first and got both edges wrong on the same recording: the player's
  longest reply starts at x=0.5945, left of any workable player-column
  floor, and the longest delivery notice starts at x=0.3939, right of
  the incoming rows but inside any band wide enough to hold them safely.
  Anything aligned to none of the four is not speech — the delivery
  notices are UI status, and the reply buttons across the bottom are
  options that have not been sent yet, each of which is read once it
  has, as its own bubble.

  No clip threshold, unlike the Answer panel: a bubble here is faded in
  whole rather than clipped by the pane edge, so across shots #2-#16
  every thread row read identically while it was still rising, and a
  threshold would only have cost the last message of a quiet thread —
  the one with nothing arriving after it to push it up out of the way.
  Replaying the same 61 seconds now reads all ten messages, in order,
  each in its own voice, and speaks none of the list, the notices or the
  buttons. Pinned by `tools/test_hsr_messages.py`.

### Fixed

- **Star Rail menus stop reading their labels as choice prompts.** A
  Currency Wars session (2026-08-24, Windows) had Trailblazer speaking
  the nav's "Data Bank" and "Back", a combat effect name ("Enervation"),
  and the team-setup tooltip ("Increases DMG dealt by all allies…" —
  shot #132, wrapped rows at left edge 0.738-0.757, dead inside the
  choice band), with the same session's earlier menus reading "Claim …
  Claim" and "Rewards Preview". The HSR choice band was never calibrated
  against a real prompt — it still carried the base-profile default, and
  unlike Genshin it had no rule tying a prompt to a speaker. Sweeping
  rec_20260726_121902 at 1 fps supplied the calibration: every genuine
  prompt keeps the speaker's nameplate on the dialogue box under the
  bubbles (frames 111, 482-490, 547-549), while the one plateless
  "prompt" was a battle-prep enemy-team title (frames 268-272). The
  profile drops a plateless choice list, same rule as Genshin; a prompt
  it refuses still leaves a "choice prompt (ignored — no speaker)" row
  in the log. A 906-frame before/after sweep (that corpus, the saved
  shots, and the reported session's) moved only plateless hsr.choices —
  every real prompt classified unchanged.

  The plate turned out to be necessary but not sufficient. A cutscene
  hands the player a lone option with no dialogue box on screen at all,
  and so nothing to plate: "I will not back down." (2026-08-30 12:23,
  Windows — shot #155, bubble at x=0.710) was refused along with the
  menus and read as nothing. What the two cases disagree on is the
  story chrome: a genuine prompt sits under the "✕ Continue" hint
  bottom-right, and the menus draw Confirm, Back or Start Challenge
  instead — the same hint the profile already trusts to tell dialogue
  from menus. A plateless choice list is now kept when that hint is on
  screen. Across the 330 saved frames on hand the two coincide on
  exactly one, this cutscene: a re-sweep of all 660 classifications
  (both profiles) moved that frame and nothing else, and replaying the
  reported clip reads the line in the Trailblazer's voice where it
  previously logged "ignored — no speaker" and said nothing.

- **Left-anchored dialogue keeps its speaker instead of falling to the
  narrator.** Snezhnaya 6.x draws some conversations as ordinary boxed
  dialogue — Auto/Confirm chrome and all — but left-aligned: the
  nameplate at cx=0.223 with the rows sharing its left edge to within
  0.001 (shots #32-#34, 2026-08-23 18:08). find_plate's centered band
  (cx 0.45-0.55) can't take a plate there and the comms band owns
  0.30-0.45, so the plate fell between the two, the speaker was lost,
  and three Eye of Graeae lines read in the narrator's voice — the same
  failure behind the earlier session's "Ebby… please stay calm" lines.
  A plate-shaped block in the band's left reach (cx 0.15-0.30), anchored
  to the dialogue rows' left edge with the same tolerance the comms
  alignment test uses, now claims the line before it is surrendered to
  the narrator. A plate is centered, comms, or left-anchored — the three
  x-bands share edges and never overlap.

- **A comms message that expects an answer is no longer silenced by its
  own reply bubble.** The Eye of Graeae's "Compassion is something to be
  respected, Miss Paimon." went unread — logged as "unknown speaker, no
  story chrome" — on every frame it was up (shots #1340/#1343/#1390/#1398,
  session 2026-08-23), while plain announcements from the same sender in
  the same session read fine. The comms detector requires the plate band
  to hold nothing but the sender, a rule that exists to keep shop-board
  label columns from reading as a plate; the player's floating reply
  option ("They've been carrying out this 'ritual' again and again.")
  wraps to two rows and its lower row lands in that band (cy=0.263,
  measured identically on all four shots), vetoing a perfectly valid
  sender plate at cy=0.231. The band-emptiness test now ignores blocks
  inside the CHOICES region — the bubble sits dead inside it at cx=0.757,
  which is why every one of those frames also logged it as the choice
  prompt it is — and the board defense is untouched, because label
  columns sit left of the choice column. The reply option is read too:
  the no-speaker rule that clears plateless choice prompts (the teleport
  map's defense) couldn't see the comms sender — its left-anchored plate
  is outside find_plate's centered band — so the bubble was cleared and
  logged "ignored — no speaker" on every frame the sender was plainly on
  screen. On a frame classify_comms recognizes, the prompt now survives
  and is read through the ordinary choice path, after the message it
  floats beside; the map still clears, having no plate of either shape.

- **A run of "haha" past two pairs no longer flattens into "HA-hah-huh",
  and ALL-CAPS "HAHAHA" no longer spells itself out letter by letter.**
  One pair ("Haha") is already `hɑhˈɑ` on both engines and untouched, but
  "Hahaha" measures `hæhˈɑhə` and caps versions read as their letter
  names (`ˌAʧˌAˌAʧˌA…`). A text dump varies the repeat count line to
  line, so this isn't a `tools/pronounce_names.py` table entry — it's a
  new `live._LAUGH` regex that hyphenates any 3-or-more-pair run into
  repeated "hah" units regardless of length ("Hah-hah-hah" is
  `hˌɑhˈɑhˈɑ`, "Hah-hah-hah-hah" is `hˌɑhˌɑhˈɑhˈɑ`, both engines). Runs
  ahead of the stammer repair in `spoken_form()`; the stammer regex
  leaves the hyphenated result alone on its own, since a vowel in the
  onset ("hah") already reads as an ordinary prefix rather than a
  stammer.

- **"Hehe" no longer comes out as "hee-HEE."** An earlier entry in this
  section measured the laughter family (`Hehe` 3,866, `Heh`, `Hahaha`)
  and left it alone on the claim that both engines already read it as
  laughter; re-measured on the same g2p (misaki + espeak fallback),
  `Hehe`/`hehe` is actually `hihˈi` — the vowels are wrong, not just the
  stress. Its neighbours really are fine as-is (`Heh` is `hˈɛh`, `Hehehe`
  is `hˈɛhɛh`), so only `Hehe` gets a `tools/pronounce_names.py` TERMS
  entry: `"Heh-heh"`, which measures `hˈɛhhˈɛh` on both engines.

- **A hum is no longer read out as letters.** "Mmm" is `ˌɛmˌɛmˈɛm` to
  both engines — "EM-EM-EM" — where the line is somebody humming; 506 of
  them across the two dumps, and bare "Mm" is spelled out the same way
  (espeak `ˌɛmˈɛm`). Both are now respelled to "hmm" (`hmm` / `həm`, a
  hum either way) in `live._INTERJECTIONS`, beside the `Shh` and `Hmph`
  repairs that were already there. The affirmative "Mm-hmm" and "Mhm"
  (`ˌɛmˈɛmhəm`, `ˌɛmˌAʧˈɛm` — "em-AITCH-em") take their own rule ahead
  of it, and become "uh huh" (`ˈʌ hˈʌ` on both): the obvious
  "hmm-hmm" would come straight back through the stammer repair as
  "Hmmuh-hmm", and the space in "uh huh" is what keeps it out of that
  regex's way. A measurement is left alone — "9mm" is still "9mm".
  Found by `tools/textmap_words.py`, which flags a vowelless word
  because espeak spells one out.

- **A restarted session no longer deletes its own first 300
  screenshots.** The shot-prune deque seeds from the previous session's
  files, but event ids restart at 1 — so appending a reused id pushed
  the deque over its cap and the prune popped that SAME id, unlinking
  the shot just written (its log row still said 📷, and the hover
  404'd), once per event until id 301. Reused ids are now moved to the
  deque's tail instead of appended twice; a half-saved shot (jpg
  written, block-dump write failed) is tracked and pruned too instead
  of orphaned forever.
- **The dashboard's recordings list can no longer latch stale.** The
  1 Hz cache updated its list and its key as two separate stores under
  Flask's threaded server, so two polls straddling a directory change
  could leave new-key/old-list — hiding a just-finished recording until
  the NEXT directory change. The cache is now one atomically-rebound
  (key, list) tuple.
- **The unmeasured-threshold warning fires when it matters.** It sat
  behind the template-exists branch, but templates deliberately never
  ship — a freshly extracted anchor self-calibrates and matches on its
  placeholder threshold in its very first session. The check now runs
  on the spec entry, before the template branch.

### Changed

- **The ROI crop stops paying for compression nobody keeps.** PNG is
  lossless at every level, so the crop now writes at store level —
  byte-identical pixels, ~11ms of deflate work per cropped frame gone
  across the encode and the daemon's inflate. Same treatment for the
  Windows native engine's flatten-and-re-encode buffer (PIL's default
  level 6 spent ~46ms compressing bytes whose only consumer is the
  decoder two lines later), and the flatten arithmetic runs in int16 —
  every intermediate is an exact integer, verified bit-identical, at
  half the allocation. The one-read-one-decode rule closes its last
  hole: when the change gate didn't decode a frame, the loop now reads
  the bytes once and shares them across the anchors, the bootstrap and
  the crop, instead of three reads straddling ffmpeg rewrites.
- **No game text anywhere — the released history included.** A
  register-check found the earlier fixture sweep had substituted words
  into the original sentence skeletons in a few places rather than
  writing new ones, left one fixture file untouched, and left verbatim
  lines in changelog entries and docstrings that the fixture sweep
  never covered. The ghost-splice line is now a from-scratch sentence
  at the same measured lengths, the comms fixture's system notice is
  invented, and every remaining quoted game line in CHANGELOG, README
  and code docstrings is replaced by invented prose of identical shape
  (the published v0.11.0 release notes are updated to match). NOTICE's
  claim now holds against a whole-repo sweep, not a per-file diff.

### Added

- **The default voice slots are visible and changeable in the dashboard.**
  The narrator (narration, lore cards, loading tips, every line with no
  speaker) and the female/male fallbacks that seed auto-casting lived
  only in `voices.json`'s `defaults` block — the one casting decision the
  dashboard couldn't see or change, and the reason a narrator voice swap
  meant hand-editing a gitignored file. The three slots are now pinned
  above the cast list with the same voice dropdowns as characters (no
  mute, no delete — a default can't be deleted, only re-cast). Changing
  the narrator re-reads its last line as an audition, the same way
  re-casting a character does; the female/male seeds have no lines of
  their own, so they speak the smoke-test line instead. Validated on both
  ends because a bad id in `defaults` doesn't fail loudly — it silences
  every line that falls back to that slot.

- **Genshin's new chat panel (the 6.x "Messages" device) is read as a
  conversation.** The phone-style UI the Eye of Graeae questline opens —
  topic sidebar on the left, sender bubbles left, the player's replies
  hanging right — matched no screen the profile knew, so the sidebar
  topics fused into the messages: most fusions were skipped as unknown
  speakers, one was spoken aloud, and "completely lost it." and "them to
  you later." were auto-cast as characters (session 2026-08-23 17:56,
  shots #19-#29 — the calibration frames for every number in the new
  CHAT_* block). The panel now hooks into the same incremental chat
  reader as Star Rail's message screens: identified by the "Messages
  from…" device header, each bubble read in its sender's (auto-)cast
  voice, the player's own replies in theirs, the bottom message deferred
  while it is still sliding in, and the Return hint lifting that deferral
  the way "Conversation Over" does. The sidebar is excluded wholesale;
  sender labels that OCR garbles below the confidence floor
  ("Unl nowwnS1") are dropped rather than cast, and the messages under
  them inherit the previous sender. Scrolled tails of already-read
  messages fall to live.py's existing containment suppression.

- **The auto-cast voice pools now claim from nearly the whole catalog:
  27 female and 21 male voices, up from 11 each.** Long sessions were
  exhausting the pools and reusing voices while ~25 packaged voices sat
  in `VOICE_CATALOG` unclaimable — the non-English-prefix ones, which
  (with the phonemizer pinned to en-us) read English text as
  differently-accented speakers, i.e. exactly what a background NPC
  needs to stay distinguishable. The original 11-per-gender lineup keeps
  its order so existing casts are untouched; the additions follow in
  rough order of how cleanly each reads English. Still excluded:
  `bm_george` (reserved as the narrator default and `release_voice`
  fallback) and the pt/es near-duplicates (`pf_dora`, `pm_alex`,
  `pm_santa`, `em_santa`), whose en-us renderings are too close to their
  es/en siblings to tell two speakers apart by ear.

- **Akivili respelled.** The Nod-Krai god's name is `əkˈɪvɪli` on both
  engines — the schwa opening the raw spelling doesn't have. Respelled
  to "Ah-kee-vil-lee" (`ˈɑkˈivˈɪllˈi`, both engines); a bare "-villi"
  ending reads `ˈɪlI`, "vil-EYE", the chunk-final-vowel trap the header
  of `tools/pronounce_names.py` documents for "eh" and "ey", so the
  final syllable is spelled "-vil-lee" instead.

- **A gate prior that can be set by name, for the two characters the
  speech model cannot hear.** Paimon and Sparxie are processed
  high-register voices; Silero is trained on human speech and scores
  them at or near 0.00, which is a stalemate the existing priors cannot
  break because they are *built out of* the VAD's verdicts. Their voiced
  lines get talked over, every talk-over is filed as another unvoiced
  observation, and the soft gate that would have saved them stays
  unreachable no matter how thoroughly the scene voices them. Worse with
  use: at three of those observations the FIRM gate arms, so we also
  stop cutting our own playback when their VO does start — a wrong
  answer built entirely from the detector's own failure.

  Both are now named in `live.MODEL_DEAF`, in code rather than in
  `voices.json`, because the file is gitignored and the Windows box
  tracks the repo — and because they are the same two characters in
  every save. `settings.gate_prior` extends and overrides it, per
  speaker: `"model_deaf"`, `"voiced"` (soft gate from the first line),
  or `"unvoiced"` (hold the firm gate). A named prior wins over the
  observed record in both directions, which also makes it the way to
  undo a record that went wrong.

  What the model-deaf name buys is corroboration for the centre-energy
  layer, and deliberately nothing else. That layer measures a real
  event — a mid-channel burst 7dB over the pre-line baseline and 5dB
  over the side channel, arriving with the line — and it is the layer
  that caught the Paimon line that went out over her own VO at mid+17.3
  side+5.2; it was held back only by a corroboration test these two can
  never pass. The VAD thresholds themselves stay at full strength.
  Dropping them to the soft floor for these characters was the obvious
  alternative and is the wrong one: Paimon is unvoiced for hundreds of
  lines at a stretch, and 0.12 over three chunks is cleared by an
  unvoiced line in a loud scene as readily as by a voiced one — the
  measurement in `VAD_SOFT_THRESHOLD`'s comment (a voiced line at 4
  such chunks, an unvoiced one in the same scene at 5) is exactly that.
  Corroboration turned out to be only half of it. Reading the mid/side
  numbers back out of seventeen session logs — 109 lines HoyoVoice spoke
  for Paimon or Sparxie — the burst that would have saved them usually
  passed the corroboration test and failed the *shape* test, on the
  decisive cut. `rec_20260812_083939` is the proof: "Wow, it's so
  majestic! Just flying from one side to the other…" was read four times
  over the game's own delivery of it, at 7.1, 6.4, 6.7 and 9.8dB of
  mid-over-side. Only the 9.8 crossed `ENERGY_DECISIVE_OVER_SIDE`, so the
  app skipped the fourth read as voiced and talked over the first three —
  the same sentence, the same voiceover, seconds apart. 8.0 is a
  population split measured across all speakers, and for these two it
  lands inside the population rather than beside it.

  So a named speaker also gets a relaxed cut, `MODEL_DEAF_OVER_SIDE`
  = 6.0, which takes all four reads together. Relaxing it costs two
  lines: over the same seventeen logs it moves six Paimon lines, four in
  that Snezhnaya station scene and two in sessions with no voice acting
  in them at all. Those last two are what `SCENE_VO_WINDOW` is for — the
  relaxed cut applies only while something in the scene has been heard to
  be voiced in the last ten minutes, ANY speaker, because voice acting is
  a property of the scene and not of the character. Both stray lines come
  from sessions where nothing was ever detected as voiced (the Leyla
  vegetable quest, 2026-08-08) and stay spoken; the four in the station
  scene, where other speakers were being skipped seconds earlier, land.
  Six moved, two of them wrongly, becomes four moved and none wrongly. A
  mid-play yield now counts as scene evidence too — it is the scene
  proving it has a voice that the gate's own verdict just missed.

  Not verified by replay: `tools/replay.py` re-reads the recording's
  audio bed, which has the original session's TTS muxed into it, and that
  TTS alone is enough to make both lines skip with or without this
  change. The measurements above come from the live logs, where the
  mid/side figures were taken off clean HDMI audio.

  Not addressed: the mid-play yield has no centre-energy layer, so VO
  that starts after we do still goes undetected for these two.
  `[voiced — center energy]` now says `model-deaf cut 6.0dB` when the
  name is what tipped it.

- **The suggest family changes sides, and Qlipoth loses a hyphen.**
  Second round of audition notes. `suggest`, `suggests`, `suggested` and
  `suggesting` had been respelled to restore the /ɡ/ espeak drops
  (`səʤˈɛst` against misaki's `səɡʤˈɛst`) — heard aloud, espeak was
  right and the g does not belong. All four now read `sa-jest`
  (`sˈɑʤˈɛst` on both), and the family still needs entries because in
  "suggesting" *both* engines drop the g and misaki alone still carries
  it in the other three. `Qlipoth` → `klepoth` (`klˈɛpɑθ`), unhyphenated
  because "kleh-poth" is `klˈApˈɑθ`, "KLAY-poth" — the chunk-final "eh"
  trap for the third time in this file.

- **Ten corrections from hearing the table read aloud.** The first
  audition of the whole set moved nine entries and withdrew one.
  `Xianzhou` → `Shee-an-joe` (the house "Shy-" onset the Xiao/Xianyun
  entries use turned out to be the /aɪ/ of "shy"), `Akademiya` →
  `academia` — the ordinary English word it transliterates, the
  `Katheryne` → `Katherine` move again — `Chevreuse` → `shev-rooz`,
  `Barbatos` → `bar-bay-tohz` (the z ending was right all along; the
  middle vowel was not), `Eidolon` → `eye-doh-lon`, `DoT` →
  `dee-oh-tee` spelled out rather than said as "dot", `artisanship` →
  `ar-tuh-san-ship` (the s is right by ear, the first respelling's z was
  not) and `status` → `stah-toose`, which is neither engine's reading.

  `Sara` is withdrawn, the second entry in this sweep to be: `sˈɛɹə` is
  already the English "Serra", and the entry had been giving the Tenryou
  Commissioner a Japanese "Sah-rah" nobody asked for. `Kujou` keeps its
  own entry, so the full name still reads. Retired as well as cleared, so
  `--write` takes it back out.

  Two of the glosses could not ship as spelled, both on traps this file
  already documents: "ar-teh-san-ship" is `ˈɑɹtˈAsˌænʃˈɪp`,
  "ar-TAY-san-ship", and "stah-toos" voices its ending to a z.

- **The 200-a-dump floor cleared, and the scan now remembers what has
  been ruled on.** Last pass over the tier: `Guyun` (`ɡˈIʌn`, "GUY-un"),
  `Guhua`, `Chenyu`, `Kichiboushi`, `Kusanali` (a /kj/ onset the name
  doesn't have), `Khaenri'ah`, `Lawachurl`, `Dodoco`, `youkai`
  (`jˈWkI`, "YOW-kye"), `Chasca`, `Cerces`, `Bartholos` and `Ormos` (both
  voicing a final s to a z), `Irontomb`, `Pramad`, `cycrane` (`sˈɪkɹAn`,
  "SICK-rain"). Two more interjections: `Uhh` is `ˈu` — "oo", not the
  hesitation — and `Aww` is `ˈɔwə`, "AW-uh", where the sound is one
  vowel.

  `Chasca` is the flat-a tell's false positive, and the only entry in
  this whole sweep to be withdrawn after shipping: the name is Quechua
  and `ʧˈæskə` **is** "CHASS-kuh". Every respelling measured worse than
  the default — doubling the s turns the ch into a /ʃ/ (`ʃˈæskə`), a
  capital inside the chunk spells it out (`sˌiˈAʧ əskˈæ`), and opening
  the a is a different name. It is in `RETIRED` as well as `CLEARED`, so
  `--write` takes it back out of any `voices.json` that already has it.

  Four at this floor have no spelling that survives both engines and say
  so in the file: `Tenryou` ("Ten-ryoh" is `tˈɛnɹˈIO`, the /aɪ/ of
  "rye"), `Jueyun`, `Deshret` (whose sh collapses to an s the moment the
  word is hyphenated) and `Aether`, which is `ˈiθə` already — only the
  final r is missing, and "Ee-ther" voices the th.

  The bigger change is `pronounce_names.CLEARED`: 130-odd words checked
  against both engines and deliberately given no entry, which
  `tools/textmap_words.py` now reads and stops reporting. Without it
  every scan re-listed the same judgements — the ✓'d names, the laughter,
  the legitimate-either-way English, the handful no respelling fixes —
  and the floor never fell. It also caught a class the tell had been
  misreading: the "final e dropped" rule fires on every `'ve` contraction
  (`would've`, `must've`, `could've`, `should've`, `who've` — 2,224
  between them) and all of them are already right. **245 candidates at
  200+ before the change, 87 after, 6 of those with any evidence against
  them.**

- **The rest of the numerals, and the words the acronym fix uncovered.**
  `II` and `III` can be keyed bare — neither is an English word — but
  **`I` cannot**: the dialogue-shaped lines hold 278,936 of the pronoun
  against roughly 340 numerals, so a bare rule would respell "I think,
  therefore I am". It is keyed only in the containers the games actually
  number, counted off the dumps: `Act I` (95), `Part I` (67), `Zone I`
  (53), `Phase I` (48), `Mode I` (48), `Room I` (16), `Chapter I` (8),
  `Volume I` (2) — "Part I" is `pˈɑɹt ˌI`, "part **EYE**", where "Part
  One" is `pˈɑɹt wˈʌn`. Nine of those lines are prose rather than a title
  and will now read "Act One"; that is the price of the other 330. Every
  numeral key is exact-case, including the containers — "the act i
  performed" would otherwise come out "the Act One performed". `V` and
  `X` are left alone and say why: 501 between them, mostly not numerals,
  and a bare key reaches into "X-ray", "X-Axis" and "V-shaped".

  Raising the acronym skip also surfaced `RES` (1,314 — misaki spells it
  out, espeak says `ɹˈɛz`, and players say "rez", so espeak wins) and
  `AoE` (525), which **both** engines read as a word: `ˈW ˈi`, "ow-ee",
  now expanded to "area of effect".

  Eight more were settled from glosses, and three of the eight could not
  ship as spelled — all three hitting the chunk-final "eh" this file's
  header warns about: `Okhema` → `ah-kem-ah` (the glossed "ah-keh-ma" is
  "ah-KAY-mah"), `Chevreuse` → `Shev-ress` ("Shev-rehss" is
  "shev-RAYSS"), and `Chrysos` → `cry-sohss`, where the glossed
  "cry-sohs" voices the final s to the very z the entry removes. Shipped
  verbatim: `Marechaussee` → `Ma-ray-shaussay`, `Qlipoth` → `kle-poth`,
  `Sorush` → `So-roosh`, `Heng` → `Hung`, `Planarcadia` →
  `Plan-ar-kadia`. `Tizocic` came from Wikipedia's Nahuatl /tiˈsosik/
  against the engines' `tɪzˈɑsɪk` — 80 of its 89 lines are "Tizocic II",
  which the numeral entry finishes as "tee-soh-seek Two".

  Six glosses were measured and deliberately produced no entry, because
  both engines already say exactly them: `Bronya` `bɹˈɑnjə`, `Columbina`,
  `Luka`, `Aurum`, `Clockie` and `Raiden` — whose glossed "Rai-den" is
  the same phones as the current `ɹˈAdən`. Their readings are recorded so
  nobody re-checks them.

  Then the terms the same pass found above 150: `Anemo` (919 — `ənˈimO`,
  "uh-NEE-moh", where the element is "AN-uh-moh"; `Cryo`, `Dendro` and
  `Geo` were checked alongside and are already right), `Manekin` and
  `Manekina` (1,633 — `mˈAŋkɪn`, "MAY-nkin", for the mannequin),
  `Favonius` (894), `Kremnos` (826 — a voiced final s), `Marechaussee`
  (693 — `mˈɛɹʧəsˌi`, "MERCH-uh-see"), `Inazuman` and `Fontainian`, which
  now follow their nations, plus `Barbatos` and `Dunyarzad`. The laughter
  (`Hehe` 3,866, `Heh`, `Hahaha`) was measured and left alone — both
  engines already read it as laughter.

- **The scanner was hiding a 3,004-occurrence fault, and thirty more
  words came out from under it.** `tools/textmap_words.py` skipped
  all-caps words wholesale on the grounds that an acronym is read out as
  its letters. That is true of `DMG` (`dˌiˌɛmʤˈi`), `ATK` and `TCG` —
  and false of `IPC`, which espeak tries to *say*: `ˈɪpk`, three letters
  mashed into one syllable, **3,004 times** in the Star Rail dump, where
  misaki spells it out. The skip now applies only where both engines
  agree, so an acronym one engine mangles is reported. `IPC` →
  `eye-pee-see`, keyed on the bare form because it fires inside the 515
  possessives too and lands the identical phones. `VIP` (157, espeak
  says "vip") came out of the same change.

  Then the sixth pass down the same class, with a word family getting
  one entry per form: `absorb`/`absorbs`/`absorbed`/`absorbing` (764 —
  espeak's s for a z), `suggests`/`suggesting` (375, and in "suggesting"
  *both* engines drop the /ɡ/), `prayer`/`prayers` (379 — misaki reads
  the one who prays where the games mean the petition), `Janus` (447 —
  "JAN-us"), `meteorite`/`meteorites`, `obstacle`, `Oceanid` (185 —
  "OH-shun-id"), `naive` ("nye-EEV"), `financial` ("fye-NAN-shul"),
  `thoroughly`, `interfere` (a dropped r), `residual`, `Stratagems`,
  `prerequisite`, `Blazar`, `Nous` (Greek νοῦς, said "nooz"), `Darshan`,
  and `What're` (120), which neither engine reads — misaki "what-ray",
  espeak "wutter" — expanded to the two words it stands for.

  Four more where macOS is the broken side: `handsome` (misaki inserts a
  /t/), `Hamster` ("HAMP-ster"), `husband` (a z for the s) and `Arcana`
  ("ar-KAY-nuh").

  `Prescience`, `interference` and `Pfft` were reported as unfixable and
  then settled by ear: `presh-inz`, `in-ter-fear-anss` and `puft`. Two of
  the three arrived as glosses whose literal spelling could not ship — a
  chunk of bare consonants is read as LETTERS, so "preh-ssh-inz" is
  `pɹˈAˌɛsˌɛsˈAʧˈɪnts` ("pray-S-S-AITCH-ints") and the "-AN-ss" of
  "in-ter-fear-AN-ss" comes out "ESS-ESS"; joining the tail keeps the
  sound. `Pfft` moves to `live._INTERJECTIONS` beside `Shh` and `Mmm`,
  and knowingly trades macOS's correct bare `ft` for a reading both
  engines say.

  `What're` was re-decided the same way: espeak's `wˌʌɾəɹ` is not a
  mistake — "wutter" is what the contraction sounds like — so the entry
  reproduces it as `wuttr` instead of expanding to the formal "what are".

  **Roman numerals**, which neither engine reads: misaki spells the
  letters (`vˌiˌIˈI`), espeak announces the system — `ɹˌOmən sˈɛvən`,
  literally **"ROMAN SEVEN"**, and `ɹˌOmən ɪlˈɛvən` for XI. 1,664 of them
  across the two dumps in chapter titles and place names. `IV`, `VI`,
  `VII`, `VIII`, `IX` and `XI` now read as words, and are the only
  entries in the table that *must* be exact-case: the Genshin dump has 13
  "Xi" and 15 "Ix", which case-insensitive matching would have turned into
  "Eleven" and "Nine".

- **Sixteen ordinary English words the two engines disagree about.**
  Fifth pass, and it took the `split` class rather than the names,
  because a word that is wrong in *ordinary dialogue* is said far more
  often than any proper noun. Wrong on Windows: `ceremony` (775 —
  `sˈɛɹᵻməni`, a syllable gone), `species` (531 — `spˈisiz`,
  **"SPEE-sees"**), `envelope` (457 — "ON-vuh-lope"), `suggest` and
  `suggested` (729 between them — espeak drops the **/ɡ/**, "suh-JEST"),
  `artisanship`, `IPC's` (385 — `ˈɪpk`, three letters mashed into one
  syllable), `celestial` (718 — "suh-LEST-yul"), `exquisite`, `faced`,
  `resistance`, `protagonist` (270 — "PRO-tuh-guh-nist").

  Four where **macOS** is the broken side and espeak holds the right
  answer: `skies` (411 — misaki says `skˈiz`, **"skeez"**), `Eidolon`
  (370 — "eye-DOH-lun"), `obstacles` (292 — "obz-tuh-kulz") and
  `disguise` (269 — `dəskˈIz`, "dis-KYZE", a hard k for the g). Same rule
  as `Acheron`: reproduce the engine that has it right, on both.

  `paths` (860) is the one this pass could not fix and says so in the
  file: espeak reads `pˈæθs` where the plural is `pˈæðz`, and no
  respelling gets the voiced th back — "pathz" keeps the θ on both, which
  would trade Windows' wrong s for macOS's right ð and gain nothing.

- **Thirty more, and the first fault that was wrong on the Mac.** Fourth
  pass. Liyue and Inazuma: `Qixing` (250 — `kˈɪksɪŋ`, the q as /k/ and
  the x as /ks/, so the government came out **"KIK-sing"**) →
  `Chee-shing`, `Wangshu` → `Wahng-shoo`, `Feiyun` → `Fay-yoon`,
  `Temari` → `Tem-ah-ree`, `Sango` → `Sahn-go`, `Kanjou` → `Kahn-joh`,
  `Onikabuto` → `Oh-nee-kah-boo-toh`, `Itto` (`ˈɪɾO`, a flapped t) →
  `Ee-toh`. Sumeru: `Haniyyah`, `Sabzeruz`, `Yasnapati`. Fontaine and
  Nod-Krai: `Melusine`/`Melusines` (`mˈɛlusˌIn`, "MEL-oo-sine") →
  `Mel-oo-zeen(s)`, `Gardiennage` → `Gar-din-nahj`, `Snezhnograd` →
  `Snezh-noh-grahd`, `Lynette` (`lInˈɛt`, "lye-NET") → `Lih-net`,
  `Noelle` (`nˈOl` — one syllable, "nole") → `No-elle`, `Sandrone` →
  `San-droh-nay`, `Kachina` (Windows `kˈæʧInə`, "KATCH-eye-nuh") →
  `Kah-chee-nah`. Star Rail: `Acheron` → `Ack-uh-ron`, `Jarilo-VI`
  (`ʤɑɹɹˈɪlOvˌiˈI` — the numeral read as the letters "vee-eye") →
  `Ja-rillo Six`. And `DoT` (886), which both engines read `dˈu tˈi`,
  **"doo-tee"** → `dot`.

  `Khvarena` is the worst reading the scan turned up — `kˌAˈAʧvˈæɹɛnə`
  on both engines, the "Kh" spelled out as letters, **"KAY-AY-CH-varena"**
  — and the only entry here with no voiced line to answer to: the term
  appears in unvoiced dialogue, which is exactly the text this app
  exists to read, so HoyoVoice is the only voice that ever says it. 255
  of its 259 entries are dialogue-shaped. The respelling follows the
  source instead of a VO: Avestan xᵛarənah-, a labialized velar
  fricative English has no letter for, gets the ordinary /kw/ stand-in
  (the one that turns Khwarezm into "Kwarezm") and keeps the schwa —
  `Kwah-ruh-nah`, `kwˈɑɹˈʌnˈɑ` on both. Every spelling that keeps the h
  is spelled out letter by letter.

  `Acheron` is the one that set the rule for the `split` class: misaki
  already said `ˈækəɹˌɑn`, which is the dictionary's own /ˈækərɒn/, while
  espeak said `ˈAkɹɑn`, "AY-kron" — so macOS was never wrong, and the
  respelling reproduces the engine that has the word rather than
  inventing a third reading. A split has a right answer that doesn't
  need an ear.

  Eight are ordinary English the engines split on: `primordial`
  (Windows "prih-MOR-dee-ul"), `shogunate`, `Thanatos` ("than-AH-tohz"),
  `prismatic` (an s for a z), `status` ("STAT-us"), `madame`
  ("MAD-um"), `diviner` ("duh-VIN-er") — and **`calm`**, the first entry
  in this file where **macOS** is the broken side: misaki sounds the l
  (`kˈɑlm`) where espeak has it right.

- **Six the scan raised and only an ear could settle.** Proper nouns
  where both engines guess and the guess is wrong, resolved against the
  user's own glosses. `Kephale` (721 in the Star Rail dump — `kˈɛfAl`,
  "KEF-ayl", two syllables where the Greek has three) → `Keff-uh-lee`,
  `Mydei` (739 — `mˈIdA`, "MY-day") → `Mai-dee`, `Imperator` (652, and
  the engines disagree with each other: misaki `ˌɪmpəɹˈɑɾəɹ` against
  espeak `ɪmpˈɜɹAɾəɹ`) → `Em-per-ah-tor`, `Clorinde` (559 — `klˈɔɹɪnd`,
  "KLOR-ind", for a Fontaine duellist) → `Klo-rahnd`, `Trianne` (465 —
  `tɹˈIæn`, "TRY-an") → `Tree-ann`, `Meropide` (443 — `mˈɛɹəpˌId`,
  "MER-uh-pyde") → `Meh-ro-peed`.

  Four ship as the gloss was written. `Trianne` lost its silent e —
  "Tree-anne" splits the stress on the second chunk (misaki `tɹˈiˌæn`
  against espeak `tɹˈiˈæn`) — and `Kephale` gained an f, because
  "kef-a-lee" is the same reading with a schwa the two engines spell
  differently (misaki `ɐ`, espeak `ə`). `Imperator` is the one entry
  here that keeps a stress split on purpose: the spelling that lands
  identically, "Emper-ah-tor", does it by doubling the rhotic — an
  audible trill traded for an inaudible stress mark.

- **Twenty-seven more, down to the 300-a-dump line — and the commonest
  Windows fault in either game.** Third pass of the scan. Characters:
  `Furina` (`fjʊɹɹˈinə`, a /fj/ where the name opens on "foo") →
  `Foo-ree-nah`, `Kafka` → `Kahf-kuh`, `Clara` → `Klah-rah`, `Svarog` →
  `Svah-rog`, `Collei` (`kˈɑlA`, the "ei" as /eɪ/) → `Coll-ee`,
  `Tighnari` → `Tig-nah-ree`, `Navia` → `Nahv-ee-ah`, `Durin` →
  `Doo-rin`, `Rappa` → `Rahp-ah`, `Nasha` → `Nahshah`. Places and lore:
  `Watatsumi` → `Wah-tah-tsoo-mee`, `Qingce` (`kˈɪŋs` — the q as /k/ and
  the final e gone, so the village came out "kings") → `Ching-tsuh`,
  `Ritou` → `Ree-toh`, `Yashiro` → `Yah-shee-roh`, `Aaru` → `Ahroo`,
  `Pari` → `Pah-ree`, `Akasha` → `Ah-kah-shah`, and `Kamera`/`Kameras`
  → `Camera`/`Cameras`, the ordinary word with its doubled rhotic gone.

  Six are ordinary English words that only Windows says wrong — the
  `split` class the scan exists for, keyed lowercase like `shaman` so
  `--custom-words` doesn't pin a word the recognizer already knows.
  `they're` is the big one: **3,336 occurrences**, and espeak reads it
  `ðAəɹ`, "THAY-er", in running text as well as alone ("They're
  coming." is `ðAəɹ kˈʌmɪŋ`) — respelled to the homophone `There`,
  which is `ðˈɛɹ` on both. Then `crimson` (espeak `kɹˈɪmsən`, an s for a
  z), `calyx`/`calyxes` (`kˈælɪks`, "KAL-ix"), `ambrosial`
  (`æmbɹˈOsiəl`, the /ʒ/ of "measure" hardened), `eremite`/`eremites`
  (`ɪɹˈɛmIt`, the stress a syllable late) and `shogun` (`ʃˈɑɡʌn`).

  Two spelling rules came out of this pass and are recorded where they
  bit: a one-syllable first chunk keeps misaki's flat a, so `Nah-shah`
  splits the engines where `Nahshah` and `Nahv-ee-ah` don't; and
  hyphenating a middle schwa splits the stress, so `Air-uh-mite` lost to
  `Airuh-mite`.

- **Fourteen more, and the last of the full-name keys.** Second pass of
  the scan. The Japanese names dialogue uses on their own were all
  wrong: `Shinobu` (249 — `ʃˈɪnəbˌu`) → `Shee-noh-boo`, `Sara` (260 —
  `sˈɛɹə`) → `Sah-rah`, `Kujou` (364 — `kjˈuʤu`) → `Koo-joh`, `Heizou`
  (202 — `hˈIzu`) → `Hay-zoh`, `Kokomi` → `Ko-ko-mee`, `Mizuki` →
  `Mee-zoo-kee`, `Sangonomiya` → `Sahn-go-no-mee-yah`, `Shikanoin`
  (`ʃˈɪkənˌYn`, the "oin" read as the /ɔɪ/ of "coin") →
  `Shee-kah-no-in`, `Yumemizuki` → `Yoo-meh-mee-zoo-kee`, `Kaedehara`
  → `Kah-ed-eh-hah-rah`; plus the two Star Rail halves `Xuan`
  (`kʃˈuæn`, a spelled-out K in front of the x) → `Shu-en` and `Yuan`
  → `Yu-en`. `Fu Xuan` and `Jing Yuan` are respelled to the same halves
  — `Foo Shu-en` fixes a stress split the old `Foo Shoo-en` had (misaki
  `fˈu ʃˌuˈɛn` against espeak `fˈu ʃˈuˈɛn`), and `Jing Yu-en` is the
  identical phones, changed so one sound has one spelling.
  `Kaedehara Kazuha`, `Kujou Sara`, `Sangonomiya Kokomi`,
  `Shikanoin Heizou` and `Yumemizuki Mizuki` retire with them; `Kuki
  Shinobu` is the one full name that stays, because `Kuki` alone is
  already `kˈuki` and nothing sorts ahead of it.

  Two lore terms from the user's own ear-glosses. `Phainon` (963 —
  `fˈAnɑn`, "FAY-non") ships as the gloss was written: `Fai-non` is
  `fˈInˈɑn` on both engines. `Stellaron` (1,485 — `stˈɛlæɹən`, the flat
  a of "fat" for a schwa) does not: the gloss `Stella-ron` is
  `stˈɛləɹˌɑn` to misaki but `stˈɛləɹɹˈɑn` to espeak — the doubled
  rhotic, on Windows only — so it ships as `Stell-uh-ron`, the same
  schwa with one r on both.

  `Fragmentum` and `Amphoreus` were checked and deliberately left out:
  both already read as asked (`fɹæɡmˈɛntəm`, `æmfˈɔɹiəs`), and an entry
  that changes nothing is config to maintain for free. The scan lists
  them because the lexicon has neither — a letter-rules guess can still
  come out right, which is why the last word is an ear's.

- **Twenty spoken forms, found by the scan rather than by ear.** The
  first pass of `tools/textmap_words.py` over both dumps, worked
  through from the top. Nations and regions the games say constantly
  and no roster lists: `Xianzhou` (3,126 — `zˈIənʒˌu`, the pinyin x
  read as /z/ *and* the zh as /ʒ/, this file's two opening faults in
  one word) → `Shyen-joh`, `Mondstadt` → `Mohntshtaht`, `Fontaine` →
  `Fon-ten`, `Penacony` → `Penna-coh-nee`, `Sumeru` → `Soo-meh-roo`,
  `Inazuma` → `Ee-nah-zoo-mah`, `Natlan` → `Naht-lahn`, `Akademiya` →
  `Ah-kah-dem-ee-yah`, `Luofu` → `Loo-aw-foo`, `Belobog` →
  `Bell-oh-bog`, `Yaoqing` → `Yow-ching`, and the two peoples
  `Aranara` → `Ahrah-nah-rah` and `Vidyadhara` → `Vid-yah-dah-rah`.

  The rest are names a full-name key never reached. `Ayaka` alone
  appears 258 times against a handful for "Kamisato Ayaka", `Kazuha`
  255, `Arataki` 571, `Ruan` 613 — and every bare one read wrong:
  `Iˈɑkə` ("eye-AH-kuh"), `kˈæzjuhə`, `ˌæɹətˈæki`, `ɹjˈuæn`. Keyed on
  the parts now, the move the `Yae` entry already records, plus
  `Kamisato`, `Ayato` and `Herta` (`hˈɜɹɾə`, a flapped t) → `Hurr-tah`.
  `Ruan Mei`, `Kamisato Ayaka` and `Kamisato Ayato` are retired with
  it: both halves have their own entry, a shorter key sorts first, and
  they could never match again.

  Every respelling is measured on both engines like the rest of the
  table, with the rejected alternatives kept next to it — a chunk-final
  "eh" that came out /eɪ/ (`Ah-kah-deh-mee-yah` is "ah-kah-DAY-mee-yah"),
  a chunk starting "sht" that got spelled out (`Mohnt-shtot` is
  "mohnt-ES-AITCH-tot"), a hyphenation that split the two engines
  (`Ah-rah-nah-rah`). What has not happened is the listen; the phonemes
  are checked, the ear is the user's.

- **A mispronounced name can now be found before it is ever spoken.**
  `tools/textmap_words.py` reads a TextMap dump and reports the words
  the synthesizer will get wrong, ranked by how often the games say
  them. Until now every entry in `pronounce_names.py` arrived the same
  way — somebody heard the app say it wrong, mid-scene, and wrote the
  respelling afterwards. The dumps hold both games' whole vocabulary,
  so the same faults are findable in one pass over them.

  Two classes, and the second is the one an ear on one machine cannot
  catch. A word the misaki lexicon **misses** falls through to espeak's
  English spelling rules — the path every `FIXES` entry took, "Xiao" to
  `zˈIəˌO` and "Fatui" to `fˈæɾui` — and the scan says which rule bit:
  a pinyin x read as /z/, a final -e dropped, the flat /æ/ of "fat"
  where a foreign a should be open, a doubled rhotic, a flapped t. A
  word the lexicon **has** but espeak reads differently is right on
  macOS and wrong on Windows, which is exactly the history behind the
  `shaman`, `Archon` and `Phlogiston` entries; all three fall out of
  the scan without anyone having to hear them first, and the report
  prints both engines' readings side by side.

  Deciding whether two transcriptions are two readings is the whole
  problem: compared as strings, the Genshin dump alone reports 8,349
  ordinary English words, because the engines disagree about stress and
  reduction in nearly all of them. They are aligned instead, and a run
  that differs only in reduction, dialect (cot/caught, trap/dress), a
  spelled-out glide, espeak's doubled r, a velar-assimilated n or a
  one-symbol diphthong is passed over — 1,449 across both dumps
  survive that, against 1,552 for Genshin's stress alone.

  Words already fixed are filtered through the app's own
  `spoken_form()`, so the pronunciations map, the interjections and the
  stammer repairs all count as handled. Output is candidates, not
  patches: a respelling has to be chosen against the traps
  `pronounce_names.py`'s header documents and checked by ear, which is
  a person's job. `tools/test_textmap_words.py` pins both halves — the
  four splits somebody already found by ear, and the eleven shapes of
  noise that must stay quiet.

- **The dashboard and the downloaded log name the exact commit.** The
  header and the log's first line now read `0.11.0 (<sha>)` — sha via
  `git rev-parse` on first render (lazy and memoized, so CLI commands
  that import the module for constants don't pay the ~180ms of git
  subprocesses), `-dirty` appended when tracked files differ from it. `VERSION` only changes at release time, so a
  mid-cycle session used to report the previous release's number: the
  2026-08-13 Windows log said 0.10.4 while running ~45 commits past it,
  and the log couldn't say which fixes were in play. Git is how both
  machines deploy, so the sha is always there; if git is missing or
  errors, the bare version appears exactly as before.

## [0.11.0] - 2026-08-13

### Added

- **Snapping a read line to the game's own text (`settings.textmap`).**
  The recognizer's everyday errors are small and local — `Ves.` for `Yes.`,
  `Choosel"harbor repairs"` for `Choose "harbor repairs"`, a full stop that
  never arrived — and each costs twice: the synthesizer says the wrong
  thing, and dedupe sees a line it has never seen and reads it again. Point
  the setting at a file of the game's dialogue strings and a settled line is
  matched back to the one it came from before the log, dedupe, casting or
  synthesis sees it, so a repaired line MATCHES the next read of itself and
  the jitter dies at the source rather than being absorbed downstream.

  A match must score 0.82 and beat the runner-up by 0.05, or the read is
  kept exactly as it is. Measured on the recorded sessions — 377 distinct
  lines as the map, 164 real misreads of them as queries — that repaired
  113 to exactly the right line, refused 51, and snapped **none** to a
  wrong line. The refusals include the fused-rows catastrophe (0.57 against
  its own line): the top match is right there and is still refused, because
  nothing about accepting 0.57 generalizes to a map three orders of
  magnitude larger, and a confident wrong sentence is a worse failure than
  an obviously garbled one. `snapped` on the dashboard metrics counts the
  lines repaired.

  **A dump is not the text on screen, and the first run against a real one
  repaired nothing at all.** An entry is the line *before* the runtime
  substitutes the player's name, picks a gender and renders the rich text:
  of the 237,812 Genshin entries, 5,719 open with a `#` sentinel, 4,644
  carry `{NICKNAME}`, 1,629 an `{F#…}{M#…}` pair, 1,210 a `<color>` span,
  560 an escaped newline, 221 a `{RUBY#…}` gloss; Star Rail's 228,068 are
  the same with more markup (34,613 newlines, 14,498 `<unbreak>`). The line
  that was needed read `#The name's Pell, and this is {NICKNAME}.` against
  a screen saying `The name's Pell, and this is Ebby.` (entry SHAPES real,
  prose invented — no dump text ships here). Entries are now
  unwrapped as the game draws them, `settings.player_name` fills in
  `{NICKNAME}`, both halves of a gender pair are indexed (and no longer
  veto each other as each other's runner-up — they are one entry to the
  margin gate), a ruby gloss is dropped rather than spliced into the middle
  of the word it annotates (`Kuu{RUBY#[S]Sea Lantern}tar` is drawn
  `Kuutar`, not `KuuSea Lanterntar`), and an entry still holding a runtime
  placeholder is dropped rather than indexed subtly wrong.

  Maps are per game and load on first use of that game, on a background
  thread. For the current dumps that is ~9 s and 600-770 MB resident (398k
  usable lines for Genshin, 315k for Star Rail) — not a price to pay at
  startup for a game the session may never read, and not one the capture
  loop can pay inline either: indexing where the first line of the session
  is being read would stop the loop dead at the one moment it cannot
  afford to be away. Until a map is ready, snapping is off and lines are
  read exactly as they are without one. Lookup is a length-bucketed trigram index
  over the rarest two dozen trigrams of the query, then a real comparison
  of the top 40: 20 ms against a 400k-line dump, paid once per spoken line
  rather than once per frame. Three things keep that affordable at dump
  scale: only every third trigram is indexed (chosen by a stable crc32 of
  the trigram, so entry and query pick the same subset — measured
  identical repair quality for ~150 MB less), postings are machine ints
  rather than Python lists (~80 MB of pointers saved), and a posting list
  longer than 3000 is skipped as a trigram that names nothing.

  A repair is logged once per LINE, not once per stabilized read of it —
  the line on screen stabilizes repeatedly as OCR jitters and every variant
  snaps to the same place, which on the first session with a real map
  printed eight identical repairs for a line that was spoken once.

  **`python tools/textmap.py <map.json> --nickname <name>` scores a dump
  against the lines this install has actually read**, which is the only way
  to tell a current dump from a stale one before trusting it. On the dumps
  to hand: of 120 lines recorded from live sessions, 3 scored 0.95+, 4
  between 0.82 and 0.95, and 79 under 0.60 — the quest being played is
  simply not in that dump, and snapping would have done nothing. **No text
  ships here**: the games' strings are HoYoverse's. Unset, or unreadable,
  and nothing changes.

- **`tools/ocr_bench.py` — the OCR is measurable now.** Every reader fix so
  far has been signature-by-signature (fused rows, a bullet glyph welded to
  a word, garbled re-reads) because there was no way to ask whether the
  reader is better than it was yesterday. Three commands, and the first
  needs no human at all:

  - `stability` groups consecutive frames of a held line and scores the
    share that disagree with their run's majority read. That disagreement
    IS the bug — a line that reads two ways alternately defeats the dedupe
    window and gets spoken twice — so it can be scored over hundreds of
    frames the moment a corpus exists.
  - `policy` replays a run through competing stabilization rules and counts
    how many times each would hand the line downstream. One is right.
  - `accuracy` scores exact-match and character error rate against a typed
    `truth.json`. The only metric that catches an error every frame agrees
    on, and the only one that costs a human anything.

  Corpora come from `extract` (frames out of a session recording) or
  `capture` (frames out of the LIVE capture file) — and the distinction
  matters: a recording is re-encoded and its frames re-scaled, so only a
  `capture` corpus sees the exact bytes the live loop reads, which is
  what the stability number below is measured on. Corpora are
  gitignored: they are game screenshots, and large.

  What it says so far, on 147 live frames of a held Genshin line: **49.7%
  of frames disagree with their run's majority read**. That is the number
  to beat.

- **`crop_frame()` takes a `scale`.** Enlarging the image handed to the
  recognizer is the cheapest accuracy lever available in principle — no new
  engine, no new dependency, one Lanczos resize, and no remapping cost
  because the daemon normalizes to whatever image it was handed. It is
  wired for use but NOT used by the app, because measurement says it does
  not help (below).

- **Anchor ROI cropping (OCR plan phase 4b), on by default
  (`settings.anchor_roi`; `false` restores full-frame OCR).** When the
  matched anchor chrome implies a screen kind, OCR reads only that
  kind's ROI — detector cost scales with area, and the ROI is the bottom
  two-thirds of the frame (the union of every band the profile needs:
  bands read off the profiles, HSR `y ≤ 0.62`, Genshin `y ≤ 0.66`, both
  full-width; derivations in plans/ANCHORS.md). The crop is written
  lossless (PNG — the frame is already one JPEG generation old, and a
  second lossy pass softens exactly the glyphs the crop exists to read),
  its cost is timed into `ocr_ms` so the on-vs-off comparison sees both
  sides of the trade, and every returned box is remapped to full-frame
  coordinates at the OCR call boundary, so classify and everything
  downstream never see crop space. The rules the change gate paid for
  apply unchanged: no anchor match → full frame (absence is weak
  evidence), and a bounded crop run (`ANCHOR_MAX_CROP_RUN`, ~2s) forces
  a periodic full-frame read so a wrong "crop here" can defer, never
  latch. The default is measured, both halves: replay decisions on/off
  sit inside the wall-clock harness's own off-vs-off noise floor (the
  audio bed carries the original session's TTS; details in
  plans/ANCHORS.md), and the Windows box measured the win it was built
  for — `ocr_avg_ms` 321 with 530 crops against its ~554 dialogue
  baseline, ~42% off the detector and inside the predicted 35–40% band,
  zero lost frames (2026-08-13 09:56 log). `roi_crops` and `anchor avg`
  on the dashboard metrics show the crop volume and match cost.

- **`Stuzha` → "STOO-zha", and `maam` → "mam".** Both engines read the
  Nod-Krai name as `stˈʌʒə`, "STUH-zhuh": the zh is already right and the u
  is the /ʌ/ of "cut" where the Russian Стужа has the /uː/ of "stool".
  `Stoozha` is `stˈuʒə` on both — the one wrong vowel fixed and nothing else
  moved. Unhyphenated deliberately: `Stoo-zhah` is `stˈuʒˈɑ`, a second
  stressed chunk and an open final a where the name ends on a schwa, and
  `Stoo-zhuh` (`stˈuʒˈʌ`) buys the same stress for the right vowel. She is
  on neither playable roster, so the entry sits with the other NPCs; the
  auto-caster's shape fallback already reads a final "-a" as feminine, so
  no gender entry was added. "ma'am" as the game writes it needs no entry —
  it is `mˈæm` on both engines already — but the apostrophe-less form an
  OCR miss leaves behind is `mˈɑm`, "mahm" with the open a of "father", so
  `maam` → `mam` is the entry that fires. Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

- **`Snezhnaya` → "snezh-NAH-yuh" (and `Snezhnayan(s)` → "-yun(s)").** Both
  engines read the raw name as `snˈɛʒnAə`, "snezh-NAY-uh" — the zh survives
  but "naya" collapses to /neɪə/. `Snezh-nah-yuh` is `snˈɛʒnˈɑjˈʌ` /
  `snˈɛʒnˈɑːjˈʌ`: every vowel lands and the ʒ is kept, which is what the
  ear-gloss "nehj" reaches for (a hard /ʤ/ variant, `Snej-nah-yuh`, was
  measured and recorded in the table comment as the swap if ʒ doesn't
  convince by ear). Chunked despite the stress cost because the
  unhyphenated tails pronounce their h (`Snezh-nahyah` is "snezh-NAH-hee-uh").
  The adjective is wrong the same way and substitution is word-bounded, so
  `Snezhnayan` and `Snezhnayans` get their own entries. Capitalised terms,
  so `--custom-words` pins them in the OCR vocabulary. Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

- **Genshin comms messages are read (Snezhnaya 6.x, "Eye of Graeae").**
  The new update delivers lines over the top of open gameplay with the
  sender's nameplate anchored to the LEFT edge of the line instead of
  centered, in a stylized font. Measured off shot #127 (2026-08-12): the
  plate sits at cx=0.401 — well left of the regular plate band's 0.45
  floor — so `find_plate` never took it, the line fell to the plate-less
  fallback band, and the no-story-chrome gate dropped it
  (`skipped (unknown speaker, no story chrome)` in the session log). A
  comms message floats over the live HUD, so there is no chrome to demand;
  the new `classify_comms` detector uses the geometry itself as the trust
  signal — exactly one plate-shaped block in the plate band, in the
  left-anchored x-band (0.30–0.45, whose ceiling is the regular band's
  floor, so a plate is either centered or comms, never both), anchored
  within (−0.02, +0.06) of the dialogue rows' left edge (the sender icon
  isn't OCR'd, which offsets the plate text 0.023 right), and nothing else
  in the band. The stylized font reads at conf 0.5 and misreads "Graeae"
  as "Gnaeae" — the plate slot already takes weak reads (PLATE_MIN_CONF
  0.3, the Tenoyollotzin precedent) and the caster's fuzzy speaker match
  owns the misspelling once the sender is cast. Wired into the
  unknown-speaker skip path only, so regular dialogue is untouched; swept
  against all 351 captured shots, the detector fires on exactly the one
  comms frame and nothing else. One frame of evidence so far — multi-row
  messages and other senders will need their own measurements when they
  appear.

- **`Ms.` → "Miss", `Imagenae` → "imagine-nay", `Gilgamesh` → "gil-GAH-mesh".**
  `Ms.` is Windows-only and the worst kind of wrong: espeak reads the LETTERS
  — `ˌɛmˈɛs`, "em-ess" (misaki says `mˈɪz`); "Miss" is `mˈɪs` on both. It is
  also the first pronunciation key ending in a period, which exposed a
  matcher bug fixed with it: the substitution wrapped every key in
  `\b…\b`, and after a trailing period the closing `\b` demands a word
  character where the following space is — a period-final key silently
  never fired. Its right edge is now the period itself (word-final keys
  keep their boundary), the same fix is mirrored in
  `pronounce_names.py --check`, and `--custom-words` skips period-bearing
  keys instead of pinning `Ms.` into the OCR vocabulary as a token the
  recognizer can never emit. `Imagenae` read "IM-ij-nee" (`ˈɪmɪʤnˌi`) on both
  engines; the literal `imagine-ay` was rejected because a standalone "ay"
  chunk is /aɪ/ ("im-AJ-in-EYE"), the same trap as chunk-final "eh" —
  `Imagin-nay` is `ɪmˈæʤɪnnˈA` on both. `Gilgamesh` is Windows-only like
  `shaman`: espeak said `ɡˈɪlɡAməʃ`, "GIL-gay-mush". Measured and left OUT as
  no-ops: `Mrs.` (already "misses" on both), `Dr.` (already "doctor" on
  both), and `Aeon`/`Aeons` (already "EE-on(z)" on both). Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

- **`Qucusaurus` (and `Qucusaur`, both plurals) → "koo-koo-SORE-us".** Both
  engines read the qu as /kw/ and the cu as /kju/ — `kwəkjusˈɔɹəs`,
  "kwuh-KYOO-sore-us" — where the bird is "koo-koo". Respelled unhyphenated
  (`Koocoosaurus`), the same move as `Asha`: the chunked
  `Koo-koo-soar-us` makes four stressed syllables ending "-USS", where the
  single word keeps the natural -saurus stress and schwa on both engines
  (`kˌukusˈɔɹəs` / `kˌuːkuːsˈɔːɹəs`). The short species form `Qucusaur` and
  both plurals are wrong the same way and substitution is word-bounded, so
  all four get entries. Capitalised terms, so `--custom-words` pins them in
  the OCR vocabulary. Run `python tools/pronounce_names.py --write` on
  **each** machine — `voices.json` is gitignored, and a pull never updates
  pronunciations.

- **Voice blending, on a new Voice packs page.** A Kokoro voice is a style
  tensor in a continuous embedding space, so a weighted average of several
  is another plausible speaker — the new **Blend voices** control does
  exactly that arithmetic (`tools/voicepack.py blend()`) and pushes the
  result through the same install path as an imported pack: verified by
  synthesizing a real line, auditioned immediately, rolled back on
  failure. Weights are relative and normalized before mixing (3/1 ≡
  75%/25%) because an unnormalized sum above 1 audibly overdrives the
  prosody and below 1 flattens it. The recipe is recorded as the voice's
  source — in the pack file's metadata and in `voices.json` — and shown as
  the pill's hover text, so a good mix can be reproduced. Blends of blends
  work. Style tensors come from a new `Tts.voice_style()` on both backends
  (macOS reads the HF snapshot's `voices/*.safetensors`, Windows pulls the
  voice out of `voices-v1.0.bin`), verified end to end on macOS: a
  0.75×af_bella + 0.25×jf_alpha blend synthesizes 2.4 s of audible audio.
  **Add voice file** moved to the same page (linked from the dashboard as
  **Voice packs — add & blend**) — neither importing nor blending is a
  mid-session activity, and the main page keeps only the live controls.

- **All ~54 of the model's voices are in the voice menu**, not just the 27
  English ones. The other 26 — Spanish, French, Hindi, Italian, Japanese,
  Portuguese and Mandarin speakers — were always in both runtimes'
  packaged voice data (the macOS snapshot's `voices/` directory, Windows's
  `voices-v1.0.bin`); only the dashboard's `VOICE_CATALOG` hid them. Both
  backends pin the phonemizer to American English (`lang_code="a"` on
  macOS, `lang="en-us"` on Windows) regardless of voice prefix, so these
  speak English text as differently-accented speakers — a timbre choice,
  not a language switch, and worth auditioning before casting since their
  English ranges from pleasant accent to barely intelligible. `af_nicole`
  stays out: broken in the packaged model.

- **`Diluc`** → `Dee-luke`. Both engines apply English short vowels end to
  end — `dˈɪlʌk`, "DILL-uck" — where the name is "dee-LUKE". Respelled, both
  vowels land on both engines: misaki `dˈilˈuk`, espeak `dˈiːlˈuːk`. Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

### Changed

- **Anchor templates self-calibrate from your own capture — the last
  game-derived pixels leave the repo.** The two anchor template PNGs
  (Star Rail's ✕-Continue glyph, Genshin's auto-play toggle) were crops
  of the games' chrome. The spec files now ship the numeric cut rect
  instead, and the first time the classifier trusts a game's dialogue
  chrome the app cuts the template from the live capture, holds it for
  three trusted frames, verifies it against a later frame at the
  measured threshold (a fade or blurred cut fails and is retried), and
  persists it under `captures/anchors/`. Self-cut templates measure the
  same margins as the originals (0.985+ own-game, ≤0.47 cross-game),
  and both regression replays self-calibrate at 1.00 and read
  identically. Anchors still gate cost, never speech: until
  calibration happens, every frame is read whole, exactly as a fresh
  install always was.

- **The frame loop stops paying quadratic fuzzy-match costs on open
  panels.** `same_line` now short-circuits on exact equality and runs
  difflib's `quick_ratio` bounds before the full `ratio()` — documented
  upper bounds, so no verdict can change — and the chat-panel dedupe
  tests set membership before its containment and fuzzy scans. On a
  motionless 10–30-row panel this was 100–900 full SequenceMatcher
  passes per frame (~10–45 ms of a 166 ms budget) doing nothing.
  `wordfreq` lookups in the run-on splitter are now cached the same way:
  the same line was re-scored on every frame it sat on screen.

  And the loop stops decoding the same JPEG twice: the change gate now
  exposes the half-scale gray it just decoded and the anchor matcher
  reuses it (same draft decode, byte for byte) instead of paying a
  second file read + decode on every fresh-OCR frame — `anchor_ms` was
  mostly measuring that decode, not the correlation. The dark-frame
  check decodes at 1/8 draft scale instead of full 1080p to average a
  48×48 thumbnail (mean shift measured ≤0.16 against a threshold of
  28); the best-variant vote's raw-read list is bounded at 60 (a line
  left on screen kept appending long after it fired — a two-minute
  pause accumulated ~700 entries); the pronunciation respellings are
  compiled once per settings change instead of ~85 regex builds per
  pass, twice per line; and the Windows OCR daemon's background
  flattening does its arithmetic in-place (bit-identical, ~32 MB of
  float32 intermediates per 1080p frame no longer allocated).

  Round two, after ROI cropping became the default path: the crop is
  written GRAYSCALE (both recognizers read from luminance and discarded
  the color on arrival — the RGB PNG paid encode here and decode+convert
  in the daemon for nothing, ~20ms per cropped frame across the two
  processes; both regression replays read identically off the gray
  crops), and it is cut from the change gate's own bytes rather than a
  re-read, so the crop, the gate and the anchors provably judge the SAME
  frame even when ffmpeg rewrites the file between them. The dashboard
  screenshot decodes at 1/2 draft scale with an aspect-correct target
  (21 → 9 ms; the square target was silently a no-op) and its 300-file
  prune keeps an in-process id deque instead of re-statting the whole
  directory per logged event. Textmap snapping halves again
  (`Counter.update` counts postings in C; a documented-upper-bound
  quick_ratio floor at `min_score − min_margin` prunes the shortlist
  with the verdict provably unchanged — measured ~10 → ~4 ms per spoken
  line on a 100k-line map). Anchor self-calibration no longer decodes
  the frame on untrusted frames (most of a session, until it fires),
  and the dashboard's 1 Hz recordings list re-walks the directory only
  when the directory's own mtime says something changed.

  The Windows daemon also stops stacking the gray frame into RGB — once
  it has proven that safe on YOUR machine. Whether RapidOCR reads a 2-D
  gray array identically to the 3-channel stack varies by version, so
  the first three texty frames of a session are read both ways: results
  byte-identical → the ~6 MB stack copy is dropped for the session
  (`[ocrd_win] gray input verified` in the log); any difference or
  error → the stack stays, permanently, and the caller always sees the
  stacked result while the trial runs. The decision logic is pinned by
  `tools/test_gray_input.py`.

- **No game text in the repo.** Test fixtures that carried verbatim
  passages (the reader-chunks page, the readable-article bodies, the
  textmap cases, the boot notice) now use invented prose with the same
  geometry, corruption shapes and matcher markers — the tests pin
  behavior, not wording, and all pass unchanged. A `NOTICE` file states
  that the games and their content are HoYoverse's and outside the MIT
  grant, the README leads with the non-affiliation disclaimer, and
  `voices.example.json` is regenerated from the shipped pronunciation
  tables (dropping a retired `Yae Miko` key and a stale `Sigewinne`
  respelling) and now seeds every setting the README documents —
  `textmap`, `player_name`, `change_gate`, `change_gate_frac`, `anchors`,
  `anchor_roi`, `ocr_engine` and `late_yield` — so a fresh install
  matches the documented settings shape.

- **A readable page starts speaking after one sentence's synthesis, not a
  whole page's.** A full inventory page (~340 words) was synthesized as
  one utterance before any sound — seconds of dead air that read as "it
  isn't going to read this." The reading pump now cuts a page into
  sentence-boundary chunks: the first chunk is the first sentence alone,
  and the next chunk synthesizes while the current one plays, so handoffs
  land on sentence pauses. The decision log, spoken count, dedupe and
  replay still treat the page as one item; closing the panel still stops
  the read and now also drops the unspoken chunks.

- **Two OCR ideas measured and NOT shipped.** Both were on the list of
  things that would obviously help. Neither does, and the benchmark is
  what says so rather than an opinion:

  - **Upscaling before OCR.** On 147 live frames, disagreement within a run
    went 49.7% at native scale → 45.6% at ×2 → 57.9% at ×3, and cropping to
    the dialogue band first made it *worse* at ×2 (52.4%). All of that is
    inside the sampling error of a 147-frame corpus. The instability is not
    a resolution problem: a Genshin dialogue row is already ~33px tall, and
    what moves between frames is JPEG noise and Vision's own grouping, not
    detail the recognizer lacks. The `scale` argument stays, unused, for
    whoever measures it against a different capture.
  - **Multi-frame consensus** (accept the text two of the last three reads
    agree on, instead of two consecutive). On the same corpus both policies
    emit exactly once per run — there is nothing to fix there — and against
    the alternating fused/clean reads that caused the forty-times bug it is
    provably no help either: a 50/50 alternation has no minority to
    outvote, at any window size. What worked there was the structural test
    (a box two rows tall cannot be one row), and it is already in.

- **Two-option prompts are now read aloud, not just lone ones.** A pair
  of options still reads as the player weighing their answer rather than
  as a menu (user preference, 2026-08-12); three or more remain
  logged-only UI. The two texts join with an ellipsis — punctuation, not
  invented words, and Kokoro reads it as the beat between alternatives.
  Each option enters the dedupe window separately, because the game
  echoes whichever ONE the player picks as the next dialogue line and a
  joined norm would match neither.

- **OCR stack review pass (four small fixes).** (1) The Windows RapidOCR
  path re-ran the full OCR on the raw frame whenever the
  background-flattened pass read nothing — a safety net for screens the
  filter hurts, but textless frames (loading, fades, overworld at night)
  arrive in long runs, and the net doubled per-frame cost exactly there.
  It now runs on every 4th consecutive empty frame instead of all of
  them: a filter-hurt screen is still seen within ~0.5s (under the
  2-read stabilization it needs anyway), and the bound means the net can
  never latch shut — the change gate's MAX_SKIP_RUN medicine. (2) The
  native Windows engine reported `confidence: 1.0` because it exposes
  none; live.py's confidence-aware stabilization read that as "the
  recognizer vouches for this" and skipped the sentence-streaming
  cushion read — the most trusted treatment, on the least accurate
  engine. It now reports a neutral 0.90 (below CONF_TRUSTED, above
  CONF_SHAKY) so no confidence rule fires on a made-up number. (3) The
  mac daemon hands Vision the file URL directly instead of decoding
  through NSImage/AppKit, and pins the recognizer revision so replay
  results stay comparable across macOS updates — output verified
  byte-identical on real capture shots. (4) Casting a voice from the
  dashboard now rewrites the OCR lexicon and restarts the Vision daemon,
  so a newly cast name helps recognition immediately instead of after
  the next app restart (Windows skips the restart — neither engine there
  reads the lexicon, and the model reload costs seconds).

### Fixed

- **The last verbatim game lines leave the test suite.** The 2026-08-13
  fixture sweep covered seven test files; a second review found the same
  passage it removed from one file still shipping in two neighbours, plus
  ~30 short lines across twelve files it never opened. All fixtures now
  carry invented prose on the original measured geometry and corruption
  shapes — the tests pin behavior, not wording, and the whole suite
  passes unchanged. With that, NOTICE's "ships no game text" claim holds
  without qualification.

- **The Windows engine no longer runs RapidOCR's per-row angle
  classifier — which was intermittently reading rows upside-down.**
  Session shots from 2026-08-13 caught `golden glow of "friendship."`
  coming back as `ajuspuerd. do Mons uapios` at conf 0.6, on a frame
  whose neighbors read the same row upright at 0.96 — the classifier
  (cls, running on DirectML) had flipped it 180°. Game UI text is
  always drawn upright, so cls can only ever hurt here, and this is the
  strongest lead yet on the long-open book-page bug (`hum`, `Ium`,
  `Culld.` rows spoken from static pages — same one-row-garbage class).
  Every engine call now passes `use_cls=False` and the cls DirectML
  session is no longer requested; an engine too old to accept the
  keyword keeps its old behavior instead of killing the daemon. Also
  hardened the gray-input trial against engines that report scores as
  strings (newer rapidocr does) — that comparison sat outside its
  try-block and a bare subtraction was an uncaught daemon-killing
  TypeError.

- **`Onigiri` → "oh-nee-GHEE-ree", `Tumaini` → "too-MY-nee".** The rice
  ball is wrong on both engines and worst on Windows: misaki keeps the hard
  g but clips the third vowel (`ˌOniɡˈɪɹi`, "oh-nee-GIH-ree") while espeak
  reads the gi as /ʤ/ and breaks the vowel too (`ˌɑnɪʤˈiəɹi`,
  "ah-nih-JEE-uh-ree"). The `gh` is what holds the g hard — the ear-gloss
  spelling "oh-knee-gee-ree" is `ˈOnˈiʤˈiɹˈi` on both, a j where the word
  has a g — and `oh-nee-ghee-ree` is `ˈOnˈiɡˈiɹˈi` identically on both.
  Chunked despite the stress cost, because unhyphenated "ohneegheeree"
  pronounces its h. Capitalised so `--custom-words` pins it in the OCR
  vocabulary; matching is case-insensitive, so the prose spelling is
  covered too. Tumaini is an Easybreeze Holiday Resort NPC (28 lines in the
  6.x TextMap, on neither playable roster): both engines read the ai as
  /eɪ/, `tˈumAni`, "too-MAY-nee", where `Too-mai-knee` is `tˈumˈInˈi`.

- **Shot block-dumps are pruned with their frames.** Every logged event
  with a screenshot also writes the raw OCR blocks to `shots/<id>.json`,
  but the 300-file cap only ever deleted the `.jpg` — the JSONs
  accumulated across every session ever run (and slowed the textmap
  seeding scan, which parses all of them). The dump now dies with its
  frame.

- **`./hoyovoice.sh start` writes the pidfile.** The two launchers are
  documented as interchangeable, but a `.sh`-started instance was
  invisible to `python hoyovoice.py status/stop` (pidfile vs pgrep).
  Both now maintain `hoyovoice.pid`; `stop`/`restart` clear it.

- **The world-object newspaper reads.** The Snezhnaya Vestnik article
  overlay draws the same column, title slot and scroll rules as the
  inventory readable, but its exit hint says **Leave** where every other
  readable says Return — and the hint word was a hard requirement, so the
  screen was never classified and a session sat on the page reading
  nothing. `leave` now joins `return` as an exit-hint word; the title, the
  three-plus prose rows on the column edge and the digit guards still
  carry the actual detection weight.

- **A setting added to `voices.json` by hand mid-session is no longer
  wiped.** The file is rewritten whenever casting changes — an auto-cast, a
  dashboard reassignment, an installed pack — from the copy the app read at
  STARTUP, so an edit made while the app was running lasted until the next
  auto-cast and then vanished with nothing said. Found the hard way:
  `settings.textmap` and `settings.player_name` were added at 20:03 on
  2026-08-12, wiped by the session that had been running since 19:50, and
  the restart meant to pick them up read a file that no longer had them —
  the map silently never loaded. Every write now goes through
  `save_voices()`, which re-reads the file first and keeps any `settings`
  key it doesn't have. Additions only, and only under `settings`: a key the
  app knows is the app's to write (the dashboard's own toggles live there),
  and casting is rewritten wholesale by design.

  Options that legitimately open with punctuation ("…Is that so?", "(Say
  nothing)") are unaffected — the pattern never ate those. Across the 307
  recorded frames carrying options, none now reaches the synthesizer with a
  glyph in it.

- **One log row per line, instead of three.** A line is handled twice by
  design — the first finished sentence, then the typewriter's remainder as
  an extension — and for a line the VAD gate SKIPS, those two passes are
  the same fact written twice: "we saw this and stayed quiet." A third row
  usually followed, because `last_spoken_norm` (which suppresses the
  repeat-log for the line still on screen) was only ever set when a line
  was *spoken*, so every voiced skip was chased by a "repeat (deduped)" row
  for its own line. Over the 2026-08-12 18:10–18:21 session that was 44 of
  77 events. A skipped line now grows the row it grew from rather than
  adding one (same action, same speaker, old text a prefix of the new — a
  jitter variant that is not a prefix still gets its own row, and a spoken
  line still logs both passes, because two pieces of audio were played),
  and the variable is now `last_handled_norm`, set for a deliberate silence
  as well as for speech. The repeat-log guard also accepts a prefix: the
  line handled a moment ago is still being typed, and past ~25 extra
  characters the similarity ratio falls under the cutoff (0.89 for one
  105-character line that grew by 26). Replayed over that session's own
  events: 77 rows become 44, one per line, with the two genuinely
  interesting repeats kept.

- **A choice prompt dropped for want of a nameplate now says so.** Genshin
  refuses a prompt with no speaker beside it — the teleport map lists its
  waypoints in the same column at the same left edge, with no nameplate,
  and would otherwise be read aloud as a three-option prompt. A real prompt
  over an empty dialogue box is refused by the same rule, and left no trace
  at all: nothing in the log to notice, which is the hardest kind of bug to
  report. It is now logged once per distinct prompt (`choice prompt
  (ignored — no speaker)`) with the option text and a shot. This is
  diagnosis, not a fix — the rule still drops the prompt.

- **Restarting with the dashboard open no longer refuses to start.** The
  port check binds a probe socket and exits loudly if the port is taken,
  which is right — a dead serving thread would otherwise leave the app
  running headless. But the probe bound without `SO_REUSEADDR` where the
  real server (werkzeug) sets it, so it was answering a different question:
  an open dashboard tab holds established connections, and when the app
  exits those sockets sit in TIME_WAIT for a minute or two, which a plain
  `bind()` reports as "address already in use" with nothing listening at
  all. Restarting promptly to pick up a fix — the normal way to restart —
  killed the new instance at startup with "another HoyoVoice instance is
  still running" while no such instance existed. The probe now binds the
  way the server will, which steps over TIME_WAIT remains and still refuses
  a port another process is genuinely listening on; both halves are pinned
  in `tools/test_port_probe.py`.

- **A frame where Vision fused two dialogue rows into one box is dropped
  instead of spoken.** On a motionless Genshin screen the OCR alternated
  between a clean two-box read of the line and a single box spanning both
  rows, whose text is the two rows *woven together* — a 26-word line came
  back as an interleave of its own two rows, alternating word fragments
  from each, ending on the second row's intact tail. The fused box reports
  full confidence, so nothing downstream doubted it, and because the two
  reads alternated every second or two each looked new against the other
  in the one-entry dedupe
  window — the line was spoken about forty times in two minutes
  (2026-08-12 17:39–17:41 session, shots 409–581, 48 fused reads of that one
  line). Not the change gate's doing: the screen never changed, and the gate
  correctly re-OCRs because the controller hints beside the box flicker.
  Not reproducible from the recording either — `rec_20260812_174047.mp4`
  replays the line once, cleanly — so it is Vision grouping observations on
  the live frame, not the frame's content.
  The height is the tell and it separates cleanly: across 6673 recorded
  blocks the tallest centered dialogue row that really was one row measured
  0.051, every fusion 0.055 or more, and these measured 0.067 against 0.034
  per real row. `profiles.base.fused_rows()` drops a frame carrying a
  centered dialogue-band box at least `FUSED_ROW_H` tall (Genshin: 0.054)
  with at least 20 characters in it, and the loop treats that frame the way
  it treats a lost one — the clean read comes back within a second or so,
  and a dropped frame costs only that wait. Deliberately no partial rescue:
  there is no honest way to unweave the box. The threshold is per-profile
  and unset for Star Rail, whose row heights have not been measured against
  a real fusion, so nothing changes there. Fused reads are counted on the
  dashboard and in the log's analytics line, and the drop logs an event
  carrying the fused box's own text, because a silent drop is what makes
  this class of bug undiagnosable. That event is written once per fused
  LINE, not per fused frame: the fusion alternates at the sampling rate for
  as long as the player leaves the line up, so the first rule here — one
  event in every twelve drops — still filled the log with 380 entries in
  two minutes on the very next session. It is keyed on the text instead,
  the same way the unknown-speaker skip is, and compared against what the
  log already says rather than the previous frame, since the weave drifts
  and would otherwise walk past the cutoff a step at a time. Over the 106
  fused frames recorded so far — four distinct lines — that writes seven
  events.

- **A choice option whose first word OCR keeps mangling is read once, not
  once per mangling.** Vision fuses Genshin's choice bullet into the
  option's first word, and the prompt stays on screen for as long as the
  player takes to click it — the gate re-OCRs the whole time, because the
  controller hints beside the bubble flicker even while the text doesn't.
  One static option, "I'll go rescue them.", came back as `T'ul` / `@ILL` /
  `I'I` / `TIL` / `TU` / `rIgo` / `TIl` across ten reads in 40 seconds
  (2026-08-12 15:48 Snezhnaya session, shots 795–804; the dialogue line
  under it and the classification were identical on every one of them —
  only the first word moved). An option is short, so a wrong first word
  drags whole-string similarity under the 0.9 cutoff that suppresses a
  re-read (`tugorescuethem` against `rigorescuethem` is 0.86): the prompt
  read as a new option, re-armed, and was spoken again. Prompt identity is
  now decided by `same_option`, which falls back to comparing the option
  with its first word dropped — the part OCR gets right. The same test
  guards the pending prompt's stale clock, which was also failing to
  recognize the option still on screen. Two guards against the opposite
  error, dropping a real option as a repeat: the tail must be at least 12
  characters, so "Yes." and "No." can never collapse onto each other, and
  the whole-string comparison still runs first. The single garbled read
  stands — the word under the bullet is genuinely unrecoverable, and the
  repeats were the complaint.

- **An option under a long voiced line is no longer dropped as "too
  late".** The stale window (8s) started counting at arming, and arming
  happens when the line under the option clears the gate — which for a
  voiced line is the *start* of its voiceover, not the end. Any option
  sitting over a line voiced longer than ~8s was deterministically
  dropped mid-sentence ("choice prompt (not read — too late)" twice in
  a row in the 2026-08-12 11:52 Snezhnaya session, both under long
  voiced lines, while the short-VO "Feeling better now?" case read
  fine). The clock now refreshes on every frame the prompt is still on
  screen — the game is paused waiting for the player, so no wait is
  late — and only runs once the option leaves the screen, which is the
  scene-moved-on case the 8s bound was written for.

- **A choice read no longer evicts the on-screen line from the dedupe
  window — which was re-speaking that line.** The window was one slot
  deep, deliberately ("immediately before" is the contract; deeper
  windows swallowed a character's legitimate second "Let's go!"), and
  the choice read appends the option texts so the game's echo of the
  picked one dedupes. But in one slot, the option evicted the dialogue
  line still on screen — and that line's next OCR jitter variant
  ("Obviousk…" for "Obviously…" at 12:02:00, a mid-render "help us,
  bui" at 13:0x, both 2026-08-12, both right after choice reads) beat
  the exact-match `fired_norm` re-fire guard, found an empty window,
  and was spoken again, minutes after its voiceover. The window is now
  4 deep with the eviction moved into `remember_line()`: a dialogue
  line still REPLACES the window (the old one-slot semantics exactly,
  so the second-"Let's go!" behavior is unchanged — pinned in
  test_window_verdict.py), while choice reads stack alongside, so the
  window holds both option texts and the line still on screen.

- **An option can no longer die unarmed while its prompt is still on
  screen.** The first session after the fix above hit the OTHER expiry
  path (12:02:49): arming compares the fired line against a norm of the
  line-under captured when the option first settled — but the bubble
  renders whole while that line is still typewriting (or while the
  previous line is still up), so the frozen snapshot never matched the
  completed line and the option sat unarmed to its 20s TTL. Two
  repairs: the tracked line-under now follows the box as it types
  instead of freezing the first sighting, and if the TTL expires with
  the prompt visibly still on screen anyway, the option is armed and
  read at the next quiet gap rather than dropped — a rare talk-over
  beats a skipped line, which is this repo's standing preference.

- **A choice option no longer reads its bubble icon aloud — including
  mid-option on a wrapped one.** Vision fuses the option marker into a
  text block, and the misread varies by frame: shot #35 (2026-08-12)
  spoke "registered sign — Feeling better now?" from `® Feeling better
  now?`, and the shots corpus also holds `® Inspection?` and
  `# Goodbye.`. On an option that WRAPS to two rows the glyph sits
  beside the middle, so it lands in the text two ways the first strip
  (leading glyph off the joined option) couldn't reach: as its own box
  it sorts between the two rows, and fused into the row it touches it
  rides in with that row's words (108 shots across the 2026-08-12
  sessions). The strip therefore runs per BLOCK, at 1–2 leading
  SYMBOL-class characters — by class, not literal glyph, because the
  icon reads differently every time — and the choice branch of
  `classify()` requires letters in a block, the rule `choice_blocks()`
  documents for exactly this ("a block with no letters is an option's
  icon"). Leading quotes, ellipses, dots, parens and brackets survive:
  "...Is that so?" and "(Say nothing)" are real option text. Swept all
  351 captured shots through both profiles: exactly the icon-fused
  strings change, nothing else — no speaker, dialogue, or trust
  decision moved.

- **The mac OCR daemon wedged after ~45 seconds of dialogue — every frame
  then read as lost and nothing was spoken.** The URL-decode change in
  the review pass above (`VNImageRequestHandler(url:)`) turned out to
  leak one file descriptor per request, permanently open on
  `live_frame.jpg`: 242 leaked fds observed on a live session's daemon,
  right at zsh's default 256 limit, after which every `open()` fails
  instantly — Vision throws in ~2ms, the daemon answers `[]` forever,
  and the app counts `lost_frames` at full frame rate (the session's
  metrics read `ocr_avg_ms: 2`, `lost_frames: 2732`, one line spoken at
  startup before the limit hit). The daemon now decodes the frame itself
  via CGImageSource (`ShouldCache=false`) inside a per-frame
  autoreleasepool and hands Vision a bare CGImage: 0 leaked fds over a
  510-frame soak, output byte-identical to the previous binary. Vision
  on macOS 26.5 also retains ~6 MB RSS per recognized frame regardless
  of how the image is handed over — mostly purgeable, so footprint grows
  far slower than RSS — and a footprint-bounded self-recycle
  (1.5 GB → clean exit, live.py's existing respawn path restarts it)
  insures against that ever becoming real dirty memory on a future OS.

- **An uncorroborated centre-energy burst can no longer silence a
  line — neither a click's transient nor a scene's rumble.** Two
  sessions drew the rule. A dialogue-advance click (2026-08-12, 10:00
  log) — centre-panned against quiet music, mid+13.0 side+1.8, VAD peak
  0.00 — cleared the decisive centre-burst cut and skipped a streamed
  first sentence as voiced; a first fix required the burst to LAST like
  speech (≥0.35s; the click sustains ~0.26s), but the Snezhnaya train's
  engine rumble (61dB ambience, 2026-08-13 09:56 log) lasts forever, and
  four unvoiced NPC lines were silenced at `peak=0.00` — each false skip
  also RECORDING a voiced observation for a just-met speaker, feeding
  the per-speaker prior that makes the next skip easier, a spiral aimed
  at exactly the characters the game never voices. The shipped rule:
  centre energy is believed only WITH corroboration — faint speechiness
  (VAD peak ≥ 0.15) or a usually-voiced record. The model-deaf-vocoder
  case (Paimon) this layer exists for keeps its skips, since that
  record is exactly what it has; without corroboration the line is
  spoken, because a rare talk-over beats a skipped line. Poisoned
  histories self-heal (`usually_voiced` demands a consistent record),
  and both the skip and speak paths log `sustain=` as a diagnostic, so
  the next borderline case is measurable from the session log alone.

- **Paimon auto-casts female — documented gender now beats the name-shape
  guess.** Session hoyovoice-20260812-084224 (0.10.4, macOS) logged
  `[auto-cast] Paimon → am_liam (male guess)`: Genshin's most common
  speaker read in a male voice until recast by hand. The auto-caster's
  gender guess was a name-shape suffix heuristic and nothing else — "-on"
  is not on the feminine suffix list — and no documented gender could
  overrule it: the roster fetch (`tools/pronounce_names.py`) collected
  names only, and Paimon isn't even in it, because both rosters list
  PLAYABLE characters exclusively. Two-part fix. The Genshin roster's own
  gender record (`bodyType`: GIRL/LADY/LOLI female, BOY/MALE male — 119
  characters as of today) now merges into `settings.genders` on `--write`,
  and a shipped `NPC_GENDERS` table covers the named NPCs no roster lists
  (Paimon, Enjou, Katheryne — "-yne" trips the same suffix wire — and
  Gilgamesh). `pick_voice` consults documented gender first,
  case-insensitively, and falls back to the suffix guess only for
  genuinely unknown names; StarRailRes documents no gender, so HSR names
  keep the fallback. Paimon is fixed by the shipped table alone — no
  fetch needed — but run `python tools/pronounce_names.py --write` on
  **each** machine to get the roster genders; `voices.json` is gitignored.
  Pinned by `tools/test_gender_guess.py` (Paimon → female, including
  case-jittered and quote-bearing nameplates; documented-male Venti beats
  the "-i is feminine" guess; unknown names still get the heuristic).

- **An OCR ghost box no longer splices itself into a line — or gets the
  same line spoken four times.** During the Snezhnograd station cutscene
  (rec_20260812_083939, shots #289/#292/#310/#313) Vision returned Paimon's
  two-row line plus a THIRD, double-height box re-reading row one ("Wow,
  its so majestic Just Flyin") that sat straddling the gap between the real
  rows. The existing ghost filter compares boxes within LINE_H row buckets,
  and the straddler quantized into row two's bucket where it overlapped
  nothing horizontally — so it assembled into the middle of the line. The
  garbage variant then beat every dedupe rule (a 25-char mid-line splice
  into an 83-char line scores 0.869 against the 0.90 ratio, and breaks the
  contiguity the substring rules need), and with the deliberately 1-deep
  window each miss evicted the clean entry: clean line and ghost variant
  ping-ponged, and one line went out four times in fifteen seconds, over
  Paimon's own voiceover. Two independent fixes, either sufficient for this
  recording: the ghost filter now judges overlap on the boxes' real
  geometry instead of row buckets (kills the ghost at the source — replayed
  against all 303 captured shots, the only dialogue that changes is this
  ghost line, four shots of it), and `window_verdict` gained a
  pure-insertion rule — a line that is a recent line with junk spliced in,
  surviving in order and in full, is a dup, not news. Replay A/B over the
  failing 32 seconds: unpatched re-fires the line three times after first
  speak; patched re-fires zero and stops polluting Paimon's voiced prior
  with repeat observations of one line.

- **Standalone `Yae` no longer reads "Yee".** The table keyed the respelling
  on the full `Yae Miko`, but dialogue says "Yae" and "Miss Yae" more often
  than the full name, and those read `jˈi` on both engines. The entry is now
  keyed on `Yae` alone — word-bounded substitution covers the full name too,
  and `Miko` by itself already reads right (`mˈikO` / `mˈiːkoʊ`), so its half
  of the old entry is dropped. The requested literal `Ya-ey` was measured and
  rejected: a chunk-final `ey` is /aɪ/ on both engines — "ya-EYE" — the
  mirror of the header's `eh`-reads-/eɪ/ trap; `Yah-eh` (`jˌɑˈA` /
  `jˈɑːˈeɪ`, "yah-ay") is the spelling that lands the sound. The old
  full-name key is retired, so `--write` also prunes it from `voices.json`
  instead of leaving dead config. Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

## [0.10.4] - 2026-08-09

### Added

- **The downloaded log names its screenshots.** Every event that saves a
  frame now carries `shot #<id>` in the decision log, naming the files
  under `captures/shots/` (`<id>.jpg`, `<id>.json` — the raw OCR blocks).
  "Which shot ids do you need?" was previously unanswerable from the log
  alone: ids are internal event numbers the log never printed, so relaying
  the right evidence meant guessing by position in a folder of 300.

- **`Serenitea`** → `Serenity`. Both engines read the pun's spelling
  literally — `sˌɛɹənˈIɾiə`, "seren-EYE-tee-uh", the tea split into two
  vowels behind an /aɪ/ — where the word is meant to be *heard* as
  "serenity" (`səɹˈɛnəɾi`). Respelled to the ordinary word, the same move
  as `Reignbow` → `Rainbow`: the pun lives on screen, not in the
  synthesizer. Word-bounded, so `Serenitea Pot` reads "Serenity Pot".
  Capitalised, so `--custom-words` pins it in the OCR vocabulary. Run
  `python tools/pronounce_names.py --write` on **each** machine.

- **`Katheryne`** → `Katherine`. The guild receptionist's stylized -yne
  rhymes with "wine" on both engines — misaki `kˈæθəɹɹˌIn`, espeak
  `kæθɚɹaɪn`, "kath-er-RYNE" — where the name is plain Catherine. Respelled
  to the ordinary spelling rather than hyphen chunks: `Kath-er-rin` makes
  three stressed syllables (`kˈæθˈɜɹˈɪn`) where the name has one, and both
  engines already read `Katherine` as `kˈæθɹɪn` / `kæθɹɪn`. Run
  `python tools/pronounce_names.py --write` on **each** machine —
  `voices.json` is gitignored, and a pull never updates pronunciations.

### Fixed

- **A long choice list is read whole, one option at a time.** The Genshin
  choice band's ceiling was Star Rail's (0.62), kept while unverified
  because both prompts in the calibration capture were a single two-row
  option — the `CALIBRATE` note this entry retires. The awaited capture
  (rec_20260809_143259, Katheryne's 7-option guild menu) shows the stack
  grows upward from a fixed bottom (~0.277) to cy 0.622 at seven options,
  so the old ceiling clipped the top option out of the prompt: the session
  log carries it as a six-option list missing "Claim Daily Commission
  Reward". The ceiling is now 0.66 — clear of the measured top edge by half
  a row, with the pitch recorded (an 8th option needs another +0.06, not
  taken on faith, the same way 0.62 wasn't).

  Grouping rows into options moves to an absolute center-to-center gap
  (0.034) for Genshin. The height-relative rule (1.5× the taller row) sat
  on a knife edge: wrapped rows of one option are 0.023 apart and adjacent
  options 0.044–0.057, but Vision's heights for the same drawn rows span
  0.018–0.034 — and the log shows three options fused into one ("Check
  Valiant Chronicles information We meet again, Katheryne…"). Centers, not
  bottom edges, because an icon glyph fused into a block inflates its box
  and shrank one real option gap to 0.039 while the drawn pitch stayed
  0.044. And a block with no letters at all is an option's icon, not its
  text — Vision returned the chat-bubble glyph as its own `®` block inside
  the left-edge band, where it joined an option as a leading word. A/B'd
  over 1725 frames of both games with `tools/sweep_frames.py`: the only
  frames that moved are the prompt's own, plus one Genshin-profile reading
  of an HSR gameplay frame — a screen that profile never reads live.

## [0.10.3] - 2026-08-09

### Added

- **UI anchors, as log-only evidence (phase 4a of the OCR plan).** A small
  grayscale template of game chrome — Star Rail's ✕-circle by `Continue`,
  Genshin's auto-play toggle — matched by normalized cross-correlation on the
  same half-scale decode the change gate uses, in 4–5ms a frame. Nothing
  reads the result yet: `[anchors]` log lines and an `anchor_ms` metric are
  the whole feature, and the score distributions they produce are what will
  earn (or refuse) ROI cropping in phase 4b. Design, coordinate gotcha table
  and sequencing: [plans/ANCHORS.md](plans/ANCHORS.md). Measured over 1560
  frames of both games: the HSR anchor agreed with the classifier on 819 of
  819 trusted-dialogue frames (worst score 0.981) and cleared every negative
  by a ±0.27 margin; the Genshin anchor's misses are the frames where the
  game genuinely hides the chrome (choice prompts) — and on three mid-fade
  frames the anchor saw chrome the OCR text couldn't, both of which are the
  "presence strong, absence weak" rule the design leans on. A choice-glyph
  anchor was tried and rejected — the option pill's rendering varies with
  hover and wrap; the numbers are in the plan doc. `settings.anchors: false`
  turns it off.

- **Four place names get spoken forms.** `TERMS` has carried lore words and creatures; these are the first locations, and they are wrong the same way every other pinyin or romaji word is — English spelling rules applied end to end.

  - **`Liyue`** → `Lee-wey`. Was `lˈɪju` / `lˈɪjuː`, "LIH-yoo": the i of "lit", and the *ue* collapsed into a single dropped vowel. Spelled `-wey` rather than `-way`, which gives the same phones but splits the stress (misaki `lˌiwˈA`, espeak `lˈiːwˈA`) — the same split `Ah-shah` was rejected for.
  - **`Guili`** → `Gway-lee`. Was `ɡˈɪli` on both, "GILL-ee". Not `Guay-lee`, which reads `ɡwˈIlˈi` — "GWY-lee", the /aɪ/ of "guy": *ua* is that diphthong to both engines, a trap in the same family as a chunk-final "eh".
  - **`Orobaxi`** → `Oh-roh-bak-shi`. Was `ˈɔɹəbˌæksi` / `ˈɔːɹəbˌæksi`, "OR-uh-BAK-see" — an open "or" where the word opens on "oh", and a schwa swallowing the second syllable. The last chunk is `-shi` and not `-shee` because `-shee` takes a stress of its own (`ˈækʃˈi`) where the name ends unstressed.
  - **`Narukami`** → `Nah-roo-kah-mee`. The one here whose vowels were already close: what was wrong is that *ru* doubled the rhotic, `nˌɑɹɹukˈɑmi`, a trill the name doesn't have. The respelling is `nˈɑɹˈukˈɑmˈi` / `nˈɑːɹˈuːkˈɑːmˈiː` — one r, and even stress across the four syllables instead of a peak on "kah".

  All four are capitalised, so `--custom-words` pins them in the OCR vocabulary as well; substitution is word-bounded, which is what leaves `Liyue Harbor`, `Guili Plains` and `Narukami Island` intact around them. Run `python tools/pronounce_names.py --write` to pick them up — `voices.json` is yours, and a pull never updates it.

- **`tools/sweep_frames.py` — the frame-corpus classification A/B, as a
  tool.** The check that cleared the 0.10.2 world-dialogue fix — classify
  every saved frame before and after a profile change, diff the outputs,
  require zero unintended changes — existed only as a scratch script; now
  it is `ocr` (recording → one raw-OCR json per frame, via the platform's
  real daemon, cached so a corpus is a one-time cost), `snapshot` (every
  frame through every profile's full detector set) and `diff`, which prints
  each moved field and exits 1 if anything moved — so "zero unintended
  changes" is an exit code, not a claim. Every frame is classified with
  BOTH games' profiles on purpose: a Genshin band change that moves an HSR
  menu frame is exactly the regression this exists to catch. Verified on a
  1560-frame corpus from three recordings: back-to-back snapshots diff
  clean, and a single planted change is caught and named.

### Fixed

- **HoyoVoice talked over Paimon's own voiceover, and the layer built to prevent exactly that had never once fired.** Game voiceover is mixed to the stereo centre, so a mid-channel burst with flat sides is voiceover even when the speech model can't recognise the voice — that is what the centre-energy layer is for, and it is the only thing standing between a processed game voice and a talk-over. Across thirteen sessions of logs it fired **zero times**.

  Two guards were refusing real voiceover rather than the sound effects they were written for. The side-flat cap (2.5dB) alone rejected **24 of the 46** lines the VAD had independently called voiced — their side channel runs p50 3.8dB, well over it. The speechiness floor (`vad_peak >= 0.15`) rejected nearly every line we spoke, including the repro: Paimon at `mid+17.3 side+5.2`, a 12.1dB centre burst, scoring `0.00` to a model trained on human speech, because her voice is processed into a squeak.

  A burst that lopsided is not an explosion — explosions are broadband — so above `ENERGY_DECISIVE_OVER_SIDE` (8dB) neither guard applies; below it both survive unchanged. The cut is measured, not chosen: over 1107 spoken and 46 known-voiced lines from thirteen sessions, mid-over-side runs p50 0.5 / p90 4.2 on lines HoyoVoice read aloud and p50 8.8 / p90 11.4 on lines the VAD called voiced, so 8 sits between the two populations rather than inside either. At that cut 18 of 1107 spoken lines (1.6%) become voiced, and 27 of the 46 known-voiced lines become reachable with no VAD agreement at all.

  Replay cannot settle this one and did not: a recording muxes HoyoVoice's own speech into the bed, so every VAD decision in a replay of one is an artifact — the same limitation the OCR plan already records. The evidence here is the live console log, where `mid`, `side` and `gate` are printed for every line. `tools/test_center_energy.py` pins the rule on the real triples, in both directions.

- **A character the game starts voicing could never earn the sensitive gate.** The per-speaker prior asked whether a speaker had been voiced in at least 75% of their whole recorded history — a lifetime tally that outlives every restart. That cannot describe a character whose voicing *changes*, and in these games it changes per quest: Paimon goes hundreds of lines unvoiced and is then fully voiced for a scene. With hundreds of unvoiced lines behind her, 0.75 was unreachable no matter how thoroughly the current quest voiced her, so every line of it was judged at full-strength thresholds and read aloud over her own voiceover. The same tally, pointed the other way, decides whether cutting our own playback needs sustained speech or a blip will do — and that side used `voiced == 0`, so one voiced line anywhere in her recorded life would have spent the protection permanently.

  The prior now reads a speaker's **last 8 observations** rather than all of them. Paimon reaches the soft gate part-way into a quest that voices her and loses it again a few lines after one that doesn't, and the firm-gate protection re-arms instead of being spent once and gone. Eight because the ratio needs enough slots to express 0.75 (6 of 8) while still turning over inside a single conversation.

  The change is narrower than it sounds. Replayed across thirteen sessions and 944 spoken lines, windowing moves the gate on **four** of them — the three Paimon talk-overs from the reported session and one Sigewinne line — and nothing else changes. State written by an older version carries lifetime tallies with no order in them, so it seeds a window from the ratio they imply: a long unvoiced record becomes an all-spoken window, which re-arms the firm gate that record earns, and a reliably voiced character keeps their soft gate across the upgrade. The window is persisted alongside the counts, so downgrading reads the old field and behaves as before. `tools/test_voiced_prior.py` pins all of it, including a quest that voices Paimon and then stops.

- **OCR garbage stops earning casting rows.** Windows session logs show `iii`
  auto-cast as a character, and `Lv. 90`, `Liv, 9.`, `255771/25577`,
  `1v.90 2557` reaching the speaker slot — HUD readouts and half-drawn rows
  that, once cast, sit in `voices.json` forever, can never match a real
  nameplate again, and each claim a voice from the auto-cast pool. A junk
  name is now refused at **auto-cast time, not in the plate slot**, and the
  placement is the point: Genshin's unnamed characters carry the literal
  plate `???` and Star Rail has `March 7th`, so filtering plates by shape
  would eat real speakers, and a rejected plate can silence a line — the one
  error this project treats as worse than any talk-over. A refused name
  still *speaks*, in the narrator's voice (the right voice for a character
  the game isn't naming), and a manual cast row beats the filter outright —
  it runs only after the cast-table lookup misses. The rules are exactly the
  junk classes in the logs (fewer than two letters, digit-heavy, comma or
  slash, one repeated letter, lowercase first letter), each pinned with the
  real strings in `tools/test_casting_filter.py`. `Crafting Bench` is left
  alone on purpose: it is lexically indistinguishable from the real NPC
  `Strange Guard` — keeping menus unread is the menu detector's job.

- **A quote-mangled nameplate no longer casts as a second character.** The
  20260809 casting table carries both `"Tenoyollotzin"` and
  `'Tenoyollotzin"` — OCR read the opening quote as a single, the mismatch
  put the read in the unquoted class, and the fuzzy match (which compares
  only within a quoting class, so a character literally named `"Narrator"`
  can't merge with true narration) never saw the original. A plate with
  quote glyphs at *both* ends is now canonicalized to double quotes before
  the class is decided; a quote on one end only is left alone — that is an
  apostrophe or a clipped read, not a quoting style.

- **`Sigewinne` was over-corrected into three syllables.** The shipped respelling `See-guh-win` phonemized to `sˈiɡˈʌwˈɪn` — "see-guh-WIN", with the `g` hardened back and a syllable the name doesn't have. The raw name was never wrong in that way: both engines read `Sigewinne` as `sˈIʤwɪn`, "SIJE-win", where the `ge` is already soft and what is actually wrong is the first vowel (the /aɪ/ of "sigh") and the clipped last one. `Seej-ween` is `sˈiʤwˈin` / `sˈiːʤwˈiːn` — two syllables, soft `g`, both vowels long. Not `Siege-ween` or `Seege-ween`: same phones, but the stress on the second chunk splits the engines (misaki `wˌin`, espeak `wˈiːn`).

  `--write` overwrites an entry whose value has changed, so `python tools/pronounce_names.py --write` picks this up on each machine — `voices.json` is yours, and a pull never updates it.
## [0.10.2] - 2026-08-09

### Fixed

- **A companion talking while you walk is read.** Genshin draws its nameplate at two heights, and they are separate clusters rather than a spread: boxed NPC dialogue at cy 0.2261-0.253, and the world dialogue special quests use — no box, no chrome, full HUD on screen — at cy 0.2093-0.2097. The plate band was sized for the first and missed the second **by 0.0003**. That is not a quiet miss: without a plate the line falls through to the plate-less band, which reaches up to 0.21 and so read the nameplate itself as words (`Paimon These bobbing lil' buoys… They won't tip us over out of nowhere, will they?` (prose invented; the geometry and the 0.0003 miss are the measurement)), and the line was then dropped as an unknown speaker, because world dialogue carries no story chrome to fall back on either. Six of them went unread in one session.

  The floor is now 0.204, placed in the 0.0103 of clear air between the world plate and the highest role subtitle ever measured (0.1990 across 79 sightings) — that subtitle being what the old floor was really defending against. The role-line test is switched off below a plate cy of 0.215, between the two clusters: a job title belongs to the boxed layout, and the world line sits 0.0370 below its plate's baseline against a `SUBTITLE_MAX_DROP` of 0.0360, so a single OCR wobble would have had it eaten as a role line — and with `REPARSE_PLATELESS` off, an eaten line leaves the plate with nothing under it and vanishes without so much as a log entry.

  Dialogue rows also gained a hard floor (`DIALOGUE_MIN_Y`, 0.10 for Genshin). The span is measured *down from* the nameplate, so the lower plate reached 0.018 further into the permanent bottom HUD and welded `Lv. 90` onto the end of a line. The deepest dialogue row ever measured is 0.134, so the floor costs nothing and also keeps out the HP readout, which the log shows arriving as its own would-be line.

  Verified against `captures\shots\98/100/101/102.json` — the exact frames from the report — and A/B'd across 1030 frames of dialogue, menus, readables and both games: **not one changed classification**, so nothing that worked before moved.

## [0.10.1] - 2026-08-09

### Fixed

- **`Mavuika` was read with a syllable she doesn't have.** The `vu` is a w, not a v followed by a vowel. Both engines read the raw name as `mˈævjuˌɪkə`, "MAV-yoo-ick-uh", and the respelling that shipped fixed the vowels but kept the v — `Mah-vooee-kah` is `mˈɑvˈuikˈɑ`, "mah-voo-EE-kah", four syllables where the name has three. `Mah-wee-kah` is `mˈɑwˈikˈɑ` / `mˈɑːwˈiːkˈɑː`. Changing a respelling needs nothing but the edit: the table always wins over what is already in a `voices.json`, so `--write` carries a correction through the same way it carries a new entry. Run `python tools/pronounce_names.py --write` on **each** machine — a pull does not update anyone's pronunciations.

## [0.10.0] - 2026-08-09

### Added

- **New pronunciations this release: `Fatui`, `Fatuus`, `Nahida`, `Wayob`, `Wayobs`.** `voices.json` is gitignored and per-machine, so a pull does *not* update anyone's pronunciations — run `python tools/pronounce_names.py --write --custom-words` on **each** machine. The second machine is always the one that reports the fix "not working".

- **`Fatui`** → `Fah-too-ee`, **`Fatuus`** → `Fah-too-oose`. Wrong on *both* engines and the same way, unlike `shaman` or `Archon`: the a is the flat a of "fat" and the t is flapped — misaki `fˈæɾui`, espeak `fˈæɾuːi`, "FAT-oo-ee". The singular also loses a syllable (`fˈæɾuz`, "FAT-ooz", where the word has three). Both are spelled with `-oose` rather than `-oos`, because `-oos` comes out voiced on both engines (`fˈɑtˈuˈuz`, "fah-too-OOZ") where the word ends on a hiss. Capitalised, so `--custom-words` pins them in the OCR vocabulary too — an invented word is what OCR fuses worst.

- **`Nahida`** → `Nah-hee-dah`. Both engines apply English spelling rules end to end: `nˈæhɪdə`, "NAH-hid-uh" — a flat first a and a schwa where the name ends open. `Nah-hee-dah` is `nˈɑhˈidˈɑ` / `nˈɑːhˈiːdˈɑː`. In `FIXES` rather than `TERMS`, being a playable character: the roster fetch lists her, so the coverage report can check her.

- **`Wayob`** → `Wah-yohb`, plus **`Wayobs`** → `Wah-yohbs`. Read as English "way" with a flat "ob" on both engines — misaki `wˈAɑb`, espeak `wˈeɪɑːb`, "WAY-ahb". The plural gets its own entry because substitution is word-bounded, and it has to be spelled `-yohbs`: `Wah-yobes` splits the engines (misaki `wˌɑjˈɑbz`, straight back to the flat ob) where `-yohbs` is `wˈɑjˈObz` / `wˈɑːjˈoʊbz` on both.

- **`--write` can now withdraw an entry it once shipped.** It only ever added, so a respelling this repo later retracted sat in every `voices.json` forever — and `voices.json` is gitignored, which makes "pull the fix" no help and hand-editing the other machine's copy the only way out. `RETIRED` in `tools/pronounce_names.py` lists withdrawn entries with the exact value that shipped, and `--write` removes those and drops them from `custom_words`; an entry whose value has since been changed by hand is the user's own and is left alone. Its first occupant is `Fatus`, which is not a word in either game — the singular of Fatui is `Fatuus`.

- **Genshin's readable articles are read aloud.** The full-screen reading panel ("Investigative Report: Bakunawa") — a gold title over a prose column, clipped top and bottom by two ornate rules, with `Return` alone in the hint strip. It hooks into the same reader Star Rail's Quick Read books use, so it is read incrementally as you scroll, survives the panel briefly vanishing, and stops mid-sentence when you close it. The title is spoken as a heading (a period is appended when it has none of its own) rather than running into the first line. Every band is measured off a 1080p capture, including the two rules themselves, found by scanning row brightness across the column: title cy=0.924, body rows left-aligned at x=0.266 at a pitch of 0.033, rules at cy=0.896 and cy=0.052. Logged as `readable` rather than `quick read` — the label is the profile's now.

  **The column is what identifies the screen**, not the screen around it. An article opened from the *inventory* is an overlay: the bag stays on behind it and OCRs right through — `Quest`, `Inventory capacity 1185/2300`, item counts, and the item's own name and description panel to the right of the column. A first cut demanded that nothing be on screen but the panel, which is true of the world-opened article and false of that one; measured against rec_20260809_080614, it detected the article on **0 of 546 frames**, and only luck — a frame where OCR happened to miss the dimmed chrome — ever got a word out of it. Keying on the column instead (three or more rows of prose sharing one left edge, under a centered title, with a `Return` hint) detects **481 of 546**, and still nothing across 484 frames of dialogue, menus and both games. Rows whose leftmost block isn't on the column edge are dropped, which is what keeps the bag's own text out of the read; rows are clustered by their own baselines rather than quantized onto a grid, because a grid put `ash itself.` and the item panel's `Quest Item` — 0.018 apart, either side of a bucket edge — in one row and read the panel aloud.

  The `Return` hint is matched on words, not exactly: its ◯ glyph is not always a separate block, and Vision returned `Return e`. The same merge shows up all over this pipeline (`R Scroll`, `O Back`, `5 Quick Read`), so `return` must be present and anything else in the block has to be single-glyph noise — `Return to Title` is still rejected.

  **A row still drawn in half is deferred**, because half a row OCRs as garbage or as a fragment dedupe can't match against the whole row it becomes — it would be read, then read again complete. The body band runs the *full* span between the rules, well below the `Return` hint: a band that stopped at the hint would swallow the end of every scrolled article, and a swallowed row is never read again, unlike a deferred one. A row mid-slide is not allowed to disqualify the panel either — the visible half sits at a center of ~0.897, between the body band's ceiling and the title band's floor, and a sliver there once killed detection outright for as long as the row was moving.

  Body rows are taken down to confidence 0.3, the floor the nameplate slot already uses. `Tenochtzitoc.` came back at 0.50 on both frames of the capture while every other row scored 1.00, and at the 0.8 default the word vanished silently from the middle of a sentence. The column is as tightly constrained as the plate.

  One artifact is left alone: on macOS, Vision sometimes merges the dimmed item name beside the column *into* the article's first row, as one block (`…could have disappeared. vestigative Report: Mare Jivart`), and one block can't be split by geometry. Windows' RapidOCR returns them separately — the same frame reads clean there — so this stays a known macOS wart rather than a guessed-at trim that could clip real words.

### Changed

- **A player dialogue option waits half a second after the line above it.** The option is the player answering, and it fired the instant our own playback stopped — so the other character's last syllable and the reply ran together as one breathless stretch, both halves ours, in different voices, with nothing between them. It now waits `CHOICE_LEAD_IN` (0.5s) of silence past the end of our own audio, measured from when playback actually ended rather than when the line was queued: both platforms report `playing` until the device has finished, macOS on the `afplay` process and Windows on the stream. The wait costs the option nothing — it may hold for up to 8 seconds looking for a gap, and both options in a replayed 90s Genshin conversation still read.

- **A line is a repeat only against the line spoken immediately before it, and only from the same character.** The window was three deep and deduped long lines across speakers, so two things went unheard: a character saying the same words again a moment later (the second "Let's go!" of a scene), and one character repeating another's question back at them — an ordinary exchange, of which only the first half was ever read. Now anyone else speaking in between makes a line fresh, and only the same nameplate can make it a repeat. An unknown nameplate on either side still counts as the same character, because the plate flickers out mid-line and the re-read that follows is the same line, not a new speaker's. What the window is actually for — the line still on screen re-stabilizing after we spoke it — is covered completely by the one entry behind us. A/B'd over 90s of a Genshin conversation: the same 27 decisions either way, with the differences down to VAD and OCR jitter between runs.

### Fixed

- **A reading panel's rows are read a frame late, not the instant they appear.** The settle check that message panels already had — a row must survive one more frame before it is spoken — now covers books, info screens and articles too. It was there because a frame caught mid fade-in gets read verbatim (`started shan ing (ocation`); it does the same job for a row caught mid-scroll. The rows it compares against are held for the same two seconds the rest of the panel's state is, rather than being dropped on any frame that missed the panel: cleared eagerly, a detector that merely *flickers* — one frame lost to a confidence dip — can never satisfy the check, because the row to compare against was thrown away in between, and nothing is read for as long as the flicker lasts.

## [0.9.2] - 2026-08-08

### Added

- **`Archon`** → `Ahr-kon`, plus `Archons` → `Ahr-kons`. Windows only, like `shaman`: misaki says `ˈɑɹkɑn` already, espeak says `ˈɑːɹtʃˌɔn` ("AR-chon", the *ch* of church). The plural gets its own entry because substitution is word-bounded.

### Fixed

- **`Wh-What's going on?` was read as "DOUBLE-YOU-AITCH-what's".** The stammer repair only ever looked at a single letter, so a stammer on a whole onset — `Wh-What's`, `Sh-She's`, `Th-That's`, `Str-Strange` — fell through to the phonemizer, which spells the cluster out (`dˌʌbᵊljˌuˈAʧ—wˌʌts`). An onset of up to three letters now takes the same `uh` ending as a single one: `Whuh-What's` (`wˈʌ—wˌʌts`). A multi-letter onset has to be **all consonants**, which is what separates a stammer from an ordinary prefix that repeats the word's opening — `re-read`, `co-conspirator` and `de-dented` all carry a vowel and are untouched. An all-caps onset is title-cased first, because `WHuh` is read as letters all over again. (0.9.0 listed `Wh-what` among the stammers it fixed; it never was — the pattern couldn't match it.)

- **`Tch` was read as "T-C-H".** `tˌiːsˌiːˈeɪtʃ` on Windows, and a bare `ʧ` on macOS. It joins `Tsk` in the interjection table and reads as `tisk` — the same tut, since Kokoro can't click.

## [0.9.1] - 2026-08-08

### Added

- **`Phlogiston`** → `flo-jiston`, a `TERMS` entry. Wrong on one platform only, like `shaman`: misaki says `flOʤˈɪstən` already, espeak says `flˈɑːdʒɪstən` ("FLAH-jis-tun"), and the respelling is `flˈOʤˈɪstən` on both — the reading macOS already had. The last syllable is joined on purpose: `flo-jis-ten` makes a third stressed chunk (`flˈOʤˈɪstˈɛn`, "-TEN") where the word ends in a schwa. Capitalised, so `--custom-words` also pins it in the OCR vocabulary.

- **`Enjou`** → `En-joe`. Kokoro read the Abyss Order clerk as "en-JOO" (`ɛnʤˈu`). Not `ehn-joe`, which reads "AYN-joe" (`ˈAnʤˈO`) — a chunk-initial "eh" is /eɪ/ on both engines, the trap `tools/pronounce_names.py` already records for "Freh". Run `python tools/pronounce_names.py --write` to pick it up: `voices.json` is yours, and a pull never updates it.

### Fixed

- **`I—It's Enjou!?` was read as two sentences.** The stammer respelling leaves `E`, `I` and `O` alone — they read as sounds already — but it was leaving the *dash* alone with them, and the dash is a fault of its own. To espeak, the g2p behind kokoro-onnx and so the Windows reading, an em dash is punctuation: `I—It's` is `aɪ ɪts`, two words with a pause between them ("Aye. It's Enjou!?"), while `I-It's` is `aɪɪts`, the run-together the stammer actually is. Every stammer now gets its dash normalized to a plain hyphen, whether or not the letter itself is respelled. Misaki reads both spellings as `ˌI—ˌɪts`, the same break `Wuh-what` already gets, so macOS is unchanged.

- **`Urgh` was read as "erg".** `ˈɜɹɡ` — an actual English word, not a groan. It joins `Ugh` in the interjection table and reads as `ug` (`ˈʌɡ`) on both engines; doubled spellings (`Urrgh`) match too.

## [0.9.0] - 2026-08-08

### Added

- **`*cough*` can be an actual cough.** `settings.sound_effects` maps the inside of a stage direction to an audio file, spliced into the line where the direction sat — `{"cough": "sounds/cough.wav"}` — or to words to speak in its place, `{"sigh": "Ahem."}`, for the sounds Kokoro can manage on its own. Relative paths resolve from the project directory, any sample rate and channel count is accepted (decoded once, mixed to mono, resampled to 24 kHz and cached), and a file that won't load costs the effect, not the line: the read goes ahead without it and the reason is logged once. A direction with no entry is read as the bare word, exactly as before; mapping one to `""` cuts it silently.

  A first attempt at the same class of problem — collapsing `Huh!?` to a single terminal mark, on the theory that Kokoro slurs the rare `!?` token pair into the following word — shipped and was then removed: A/B'd against the real line in the cast voice, the two are indistinguishable. The slurring is real but the punctuation isn't causing it.

  This needed asterisks to survive OCR repair, which used to strip them as decoration. They now do, but only in pairs around a short phrase — that's the games' notation for a noise the character makes, where a lone asterisk is ornament or a multiplication sign and still goes. So the dashboard log shows `*cough*` as written, and `＊` normalizes to `*`.

- **Interjections and stammers are respelled for the synthesizer.** `Uhm` phonemized to `ˈum` ("oom"), `Ugh` split the two engines (`ˈʌh` on macOS, `ˈʌɡ` on Windows), and `Aaah` came out `ˈææə`. They now read as `um`, `ug` and `ah`.

  The bigger one is stammers, which these games write constantly: a lone initial is read as the **letter's name**. `W-what` was "DOUBLE-YOU-what" (`dˈʌbᵊljuwˌʌt`), `N-no` was "EN-no", `H-hey` was "AITCH-hey", `Wh-what` was "DOUBLE-YOU-AITCH-what", and `A-aah` was "AY-ah". Spelling the stammer as a syllable fixes it — `Wuh-what`, `Nuh-no`, `Ah-ah` — and the repair only fires when the initial matches the word it precedes, so `X-ray`, `T-shirt` and `e-mail` are untouched. `E`, `I` and `O` are left alone: they already read as sounds (`I-I'm` → `ˌIˌIm`), and every respelling tried for them was worse.

  All of this moved from `fix_ocr_text()` to `spoken_form()`, where the name respellings already live, because it is the same kind of change: what the line SOUNDS like, not what it says. So the log, dedupe and casting now keep `Shh` and `W-what` as the game wrote them, and the `synth heard:` line is where the respelling shows up. `Pfft` lost its entry entirely — it phonemizes to `ˈft`, roughly the right noise, while the `pfff` respelling it used to map to came out as "P-E-F-E-F".

- **Lore terms get shipped respellings too, in their own table.** `settings.pronunciations` never cared whether a word was a name, but `tools/pronounce_names.py` did: everything in it was checked against the two character rosters, so a term would have sat in a coverage report that can't say anything about it. `TERMS` is that home — the same map at synthesis, audited the same way and printed as `[term]`, merged by `--write`, and reported by `--check` alongside the names. `--custom-words` picks up the *invented* ones, since a word the recognizer has never seen is the one it fuses into its neighbour; a term that is ordinary English is already in its vocabulary and stays out. Capitalisation is the tell.

  - **`Asha`** → `Ahshaa` (`ˈɑʃɑ`), was "uh-SHA" (`əʃˈæ`). Unhyphenated on purpose: `aa-shah` phonemizes to `ˈɑˌɑʃˌɑ`, an extra syllable, and `Ah-shah` splits the engines (misaki `ˌɑʃˈɑ`, espeak `ˈɑːʃˈɑː`).
  - **`Reignbow`** → `Rainbow` (`ɹˈAnbˌO`), was "ree-EYE-n-bow" (`ɹˌiˈInbO`) — the phonemizer takes "eign" as its own syllable.
  - **`Wishpower`** → `Wish power`, which is *not* a phonetic fix: the compound already reads correctly as `wˈɪʃpWəɹ`. It's a delivery choice between two stressed words and one, A/B'd against the compound and kept because the difference is audible — the one deliberate exception to this file's rule that an entry changing nothing is config to maintain for free.
  - **`shaman`** → `shahmon` (`ʃˈɑmən`), plus `shamans` → `shahmons`, because substitution is word-bounded and `\bshaman\b` never matches inside the plural. The first entry that is wrong on one platform only — misaki says `ʃˈɑmən`, espeak says `ʃˈæmən` ("SHAM-un", rhyming with salmon) — so `shahmon` is the reading macOS already had, now on both engines rather than a new approximation. Also the first that is an ordinary English word, hence lowercase: case doesn't change the phonemes, but a capitalised replacement mid-sentence reads as a proper noun.

  `Reignbow` and `Wishpower` were already hand-written in `voices.example.json` or the README; shipping them in `TERMS` is what makes `--write` and `--check` know about them. Run `python tools/pronounce_names.py --write` to pick any of this up — `voices.json` is yours, and a pull never updates it.

- **The startup health warning is skipped.** Both games open on an unskippable ~150-word epilepsy notice, and it was the first thing HoyoVoice read aloud every session. It renders as a chrome-free title + prose card — structurally identical to a real lore card — so it's matched on content, checked before mid-line streaming can speak its first sentence, and logged as `skipped (legal notice)` rather than dropped silently. The markers are all medical and several rather than one, so a single OCR slip inside a word can't hand you the whole wall of text; none come from the title, because `before playing` also matches ordinary lines and eating real dialogue is the worse failure. `tools/test_boot_notice.py` pins both directions.

- **The log now says what the synthesizer actually heard.** Respellings and delivery fixes are deliberately invisible — the log, dedupe and casting all keep the line as the game wrote it — which left no way to answer "is that fix even running on this machine?" from a session log. A line the TTS path changed now carries a second `↳ synth heard:` line in both the console and the downloaded log, showing the line after respellings, punctuation collapse and stage-direction substitution, with a mapped sound file shown as `[path]`. A line that comes through untouched adds nothing, so the logs don't double in size.

- **Pick which speakers HoyoVoice talks through (Windows).** Playback went to the Windows default output, so on a machine with two sets of speakers the only way to move the reads was to move the whole system — game audio and everything else with them. The dashboard's device row now has a third picker, **speaks to**: any output device, or **System default** to keep following Windows. It's persisted as `settings.output_device` ("" = system default), and it only affects our own speech — capture is untouched, so the setting applies to the next line with no restart, and unlike a video/audio swap it's allowed mid-recording.

  The picker stores a device *name*, never an index: PortAudio indices shift as devices come and go (an index has already, once, turned into a webcam). Resolution is shared with the existing input matching — WASAPI's view of a device is preferred, because sounddevice lists each physical device once per host API and MME truncates names at ~31 chars ("Headphones (Arctis Nova Pro Wire"), so an exact-name match against the wrong host API's list silently fails. The resolved index is cached across lines (querying the device table per line is slow), re-resolved at once when the setting changes, and after a miss re-checked only every 10s — a headset that's off shouldn't print the same complaint under every spoken line.

  **A missing device never costs you a line.** If the saved name doesn't resolve, or the stream refuses to open (device asleep, or held in exclusive mode), the line is spoken on the system default and the log says why, with the outputs it could see. The dashboard also keeps a chosen-but-missing device listed as "(not found)" rather than quietly resetting the setting to System default on the next Apply. `tools/test_output_device.py` covers all of it against a fake sounddevice — host-API preference, "" meaning default, the cache, both failure paths, and the dashboard round trip — so it runs on either platform with no sound card.

  macOS plays through `afplay`, which has no device selection, so that backend reports no output list and the picker shows System default alone (route per-app from Sound settings there). Backends now take the live devices dict in `create_player(devices)` and `list_devices()` returns a third list; see `hv_platform/base.py`.

  Naming a device is also what exposed a format problem the default never had: the system default reaches PortAudio through a host API that resamples whatever it's given, while a *named* WASAPI endpoint in shared mode requires the stream to match its mix format — so 24 kHz mono TTS was rejected outright (`-9997 invalid sample rate`) and the never-lose-a-line fallback spoke on the default anyway. The Player walks the same format ladder `AudioCapture` already needed for input: WASAPI auto-convert, the audio as-is, then resampled to the endpoint's native rate and duplicated to stereo. The rung that works is remembered, so only the first line of a session pays for the search, and the conversion is lazy — nothing is resampled on the common path where the endpoint takes the audio directly.

### Fixed

- **A shopkeeper's job title was read as the start of her line.** Blanche said "Shopkeeper, Mondstadt General Goods Please have a look around." The role line under a Genshin nameplate is already recognized as part of the plate — it sits closer to the name (0.023–0.031 below its baseline) than a dialogue row does (0.041–0.063), and it is centered on the name's axis to within 0.008 — but both tests were applied to each OCR box, and a long role does not arrive as one box. Vision returned this one as "Shopkeeper," and "Mondstadt General Goods", and a piece of a centered line is not itself centered: neither piece was within 0.012 of the axis, so neither was recognized, and Genshin accepts dialogue rows across the whole text column (the typewriter puts a half-typed row anywhere left of center), which left both free to seed a row of their own. The test now runs on the **row's** bounding box, which has the geometry the game drew however Vision cut it up, and a row that passes is dropped whole. A role that arrives as one box is tested exactly as before. `tools/test_genshin_chrome.py` pins both forms, plus a plain nameplate and a two-row line, so the row under the title can't be swallowed with it.

- **The crafting and inventory screens read out their item grids.** The Convert screen's "Conversion Material" banner sits dead in the nameplate band (cx=0.47, cy=0.27) and the material grid under it lands in the dialogue band, so the screen classified as a line of dialogue: "Shadow of… Dragon Lo… 9/1 1/1". What kept it quiet was the unknown-speaker gate — the frame carries no story chrome, so nothing was spoken — but that gate is one name collision away from failing, it fills the log with skip rows, and it is the same reason a shop screen logged "90 Owned: 80". Genshin now identifies these screens outright, from the button hints every screen draws in the bottom-right corner: dialogue shows Auto/Confirm there and narration cards Continue, while a menu shows its own verbs ("Item Details", "Convert", "Leave"). A frame whose hint strip advertises actions the story never has is classified as a menu — no speaker, no dialogue, no choices, and not trusted as story. The test is deliberately one-sided: any story chrome in the strip wins, so a stray read down there costs a menu that stays readable rather than a line that goes unread. The UID shares that corner and is excluded by being digits.

- **The third row of a Genshin dialogue box was never read.** Pucli's "That way, we might just find our invisible Asha." was spoken without the "Asha." — and the word was never lost in dedupe or beaten by the typewriter, it was never OCR'd at all. The dialogue band's floor is `plate["y"] - DIALOGUE_SPAN`, measured from the plate's **bottom edge**; the 0.10 span was derived against its **center**. On the frame that reported it the floor landed at 0.140 and the third row sat at cy=0.136 — outside by 0.005, about five pixels at 1080p. The profile's own comment already recorded the deepest row it had seen as cy=0.134, so the constant had been contradicting its own measurement since it was written; a two-row line never noticed. Row offsets below the plate edge are stable at 0.045 / 0.076 / 0.105, so the span is 0.125 now, which clears three rows with margin and stays well above the chrome row at cy≈0.067 — where the bottom-left icon strip misreads as text ("134)") inside the dialogue column. A four-row line would need 0.15 and is still uncovered: no capture of one exists, and raising it that far eats most of the chrome margin. Checked by replaying 41 frames of the reporting session through the real OCR and classifier: two frames change, both gaining the missing word, and nothing else in the band moves.

- **"A—Ahh!" was read as "AY-ah".** The stammer respelling only knew the hyphen, and Genshin writes this one with an em dash — so the pattern walked past it and the phonemizer read the lone `A` as the letter's name. Every dash counts now, and all of them come out as a plain hyphen (`Ah-Ah`, which reads `ˌɑˈɑ`). A spaced dash — the punctuation kind, as in "the humble vegetable — it is the eyes of the earth" — still can't match: the letter and the dash have to be adjacent.

- **A line was cut off 0.8s in with nothing taking over.** "Can you please just start already!?" got as far as "Can you please just" before the mid-play yield decided the game had started talking. It hadn't: scanned end to end, the capture behind that session (400s, 47 lines) contains no game speech at all — every speech-like stretch in it is our own playback — and the yield fired on three 32ms chunks peaking at 0.66.

  The per-speaker prior that softens the yield for a character the game usually voices now has a mirror image: a character the game has **never once** been heard to voice, over at least three lines and across sessions, needs sustained speech (~192ms above the confident threshold) or one decisive spike before we cut our own read. A scene with the voice acting off is the case where every yield is a false one and the reading is all the player has. The log line says `firm` when this applied, next to the `soft` it already said.

- **A line answering the question before it lost its opening words.** Paimon asked "And then?"; Leyla answered with a full sentence beginning "And then I…" and was read from its second word onwards (prose invented here; the shape is the measurement). The recent-lines window spans speakers, and the extension rule — a line that grew after we spoke a stable prefix is read from the remainder — only tested that the new text *starts with* a windowed line, so one character's short line could swallow the head of another's. A line grows by typewriter and the typewriter never changes nameplate mid-line, so an extension now needs the same speaker. An unknown speaker on either side still counts: the plate flickers out mid-line, and a real extension must not be re-read from the top. Cross-speaker echoes still dedupe as before — they go through the fuzzy checks, which is where they always belonged. The verdict moved into `window_verdict()` so it can be tested; `tools/test_window_verdict.py` pins all three outcomes.

- **A lone choice option often went unread — over a wordless line, always.** Two faults stacked, and the recording of the session that reported it has both.

  The hold was rebuilt from scratch several times a second. An option is marked as seen when it is read (or when it finally goes stale), but the bubble stays on screen for as long as the player takes to click it, and every one of those frames read as "settled, and not one we've seen" — so the hold was recreated with its arm flag cleared and its clock reset. Nothing that has to survive a frame could: the read only ever landed when arming and a gap in the talking fell on the same pass, which is why an option sometimes read and sometimes didn't. It is now marked as seen when the hold is created.

  Under that: the hold waits for the line beneath it to clear the gate, matched by text — and Paimon's `...` normalizes to nothing (Vision returns no block for it at all), which `same_line()` never matches, so that wait could not end however long the hold survived. With nothing readable underneath, the option now arms itself after a two-second grace; a real line turning up inside that window is adopted and waited for as before, since the bubble renders whole while the line under it is still typing. The read is still gated on our own voice being idle and the game's having stopped, so an option can't land on top of VO.

- **A long "Huh!? You... !"-shaped line hissed through its interjection into the next word.** Kokoro predicts prosody for a whole utterance in one pass, so a long line degrades its own opening — `Huh!?` and the rest of that line each synthesize cleanly on their own, and only the two together fail. A settled line is now split at sentence ends, each sentence synthesized separately, and the pieces spliced with an 80 ms pause. A single-sentence line is one call and one piece exactly as before, so nothing but a genuinely multi-sentence line pays anything; the extra invocation measured at ~50 ms, because it is call overhead rather than synthesis.

  Three earlier theories died against A/B tests on the real line in the voice it's cast to, and are recorded here so nobody re-derives them: the `!?` token pair (collapsed and uncollapsed are indistinguishable — shipped, then reverted), the `…` at the `You… You're` junction (every replacement punctuation sounded identical), and the name's respelling (`Pie-mahn` phonemizes with two primary stresses, `pˈImˈɑn`, but the unrespelled `Paimon` fails the same way). Bisecting growing prefixes of the line is what actually located it. Beware synthesizing fragments while bisecting: Kokoro trails off into noise on text with no terminal punctuation, which reads exactly like the bug being chased.

- **Sentiment pacing scored the respelled line, not the written one.** Speed was picked after `spoken_form()` had already turned names into nonsense words. It now scores the line as the game wrote it.

### Changed

- **Clear now empties the dedupe window too, not just the log.** The recent-lines window outlives a restart for 10 minutes on purpose — a crash mid-scene shouldn't re-read the line still on screen — but that also means restarting *into* the same content inside the TTL has those lines silently skipped as repeats, with nothing in the dashboard to reset. Clear is what you reach for when you want what follows read as new, so it now forgets the window and rewrites `spoken_cache.json` (the per-speaker voiced history in it is kept — that's a different thing, and it takes real evidence to rebuild). The line already on screen is not re-read: it has already fired, so Clear can't make the app start talking at you.

- **Paimon is now respelled `Pie-mahn` (`pˈImˈɑn`), not `Pah-ee-mahn` (`pˈɑˈimˈɑn`).** The old form spelled the diphthong out as two syllables; this one is the way the games say it. Hyphenated rather than spaced: `Pie mahn` phonemizes to the same sounds but as two words (`pˈI mˈɑn`), which puts a word break in the middle of the name.

## [0.8.0] - 2026-08-08

### Added

- **`tools/pronounce_names.py` — spoken forms for both games' casts, and the rosters to check them against.** Kokoro phonemizes English spelling rules, so Chinese and Japanese names fail in a specific, predictable way: pinyin x reads as /z/ ("Xiao" → `zˈIəˌO`, "ZY-ah-oh"), q as /k/ ("Qiqi" → `kˈɪki`), zh as /ʒ/ ("Zhongli" → `ʒˈɑŋɡli`), and a final -e vanishes ("Shenhe" → `ʃˈɛnh`). The script fetches the live Genshin (119) and Star Rail (84) rosters, holds a respelling for the 66 names the phonemizer gets wrong, and prints every one with its reading before and after so the table can be *audited* rather than trusted; `--write` merges it into `voices.json`, `--custom-words` also feeds both rosters to the OCR vocabulary. Names it already says correctly ("Ningguang", "Hu Tao", "Yao Guang") deliberately have no entry.

  A name that is also an ordinary English word needs `settings.pronunciations_exact`. Matching is case-insensitive so OCR case jitter can't miss a name, which means the "Gaming" entry would also respell "gaming" in ordinary prose — listing the name there matches the capitalised spelling only. The same trap is waiting for Jade, Sunday, Hook, Blade, Archer, Robin and March 7th, all of which are Star Rail characters.

  Respellings, not IPA. misaki accepts inline phonemes, but the Windows backend (kokoro-onnx) doesn't, and markup that only works on one platform is worse than an approximation that works on both. Each respelling was checked against the same g2p Kokoro runs, which has three traps worth knowing: a hyphen chunk is its own word, so a chunk-final "eh" reads /eɪ/ ("Freh-mee-nay" → "FRAY-mee-nay", fixed as "Frem-ee-nay"); an unreadable initial cluster is spelled out letter by letter ("Shway" → "S-H-way", so shw/chw/hw/lw are avoided); and "ge" is soft, so Gepard needs "Ghep-ard" to keep its hard g.

- **"Add voice file" in the dashboard: import a Kokoro voice pack, and have it verified before it can be cast.** Using a voice the app didn't ship with meant editing `VOICE_CATALOG` in the source, and there was no way at all to use a pack downloaded from a voice repo. Now it's a file picker: choose a `.pt` / `.safetensors` / `.npy` / `.npz` / `.bin`, and the voice joins the menu, castable to anyone, surviving restarts (the canonical copy is kept in `voices_custom/`, so deleting the download doesn't silence a character). ✕ removes one and hands any character cast to it back to the auto-caster. The picker uploads, so it works from a dashboard open on another machine; leaving it empty asks for a path instead, which skips the copy when the file is already on the machine running HoyoVoice.

  **Verified means synthesized.** Shape-checking the tensor is not enough — a (510, 1, 256) float32 array can still be noise, zeros, or a style vector from a different model, none of which is visible until something is spoken with it, and the failure mode is a character who silently produces nothing mid-quest. So a pack is installed, registered with the real engine, run on a real line, and checked for audible output (rms) before it is written into `voices.json`; anything short of that is rolled back to no trace — no file, no registration, no entry — and the reason is shown next to the button. What passes is auditioned immediately, because the only check that answers "is this the voice I wanted" is hearing it.

  **Reading a `.pt` without torch.** Voice packs ship in whatever format their repo used, and the most common is a torch pickle — i.e. arbitrary code in the general case. This project has no torch dependency (the VAD is onnx for the same reason) and adding ~200 MB of it to read 522 KB of floats is a bad trade, so `tools/voicepack.py` reads the zip and unpickles it under a restricted unpickler that resolves exactly two things, a storage id and the tensor rebuilder, and refuses every other global. `tools/test_voicepack.py` builds its fixtures by hand-emitting pickle opcodes (Python's own pickler won't write a global it can't import) — including a hostile file that names `os.system`, pinning that reading it neither imports nor runs it. Verified against the real upstream `af_bella.pt`: byte-identical to the packaged macOS voice.

  Both runtimes learned `register_voice` / `forget_voice`. macOS passes mlx-audio the installed file's path, which is why everything is normalized to single-tensor `.safetensors`; Windows can't add to the read-only `voices-v1.0.bin`, so it keeps the array and passes it to kokoro-onnx in place of a name.

- **README: "Adding your own voice actors."** The casting section documented the *shape* of `voices.json` but not how to actually cast someone, so each level of it now has a section: assigning voices from the dashboard (auto-cast, Add cast, the audition-on-assign behaviour, muted, the Test TTS box) and by hand — including the trap that the file is read once at startup and written back on every casting change, so hand-edits made while the app is running are overwritten; importing a voice pack, and where packs come from, including the model's own ~54 voices where the menu shows 28 (the rest speak English text through the American phonemizer — verified: a different-sounding speaker, not a language switch); and what is still a code change, with the `synth(text, voice, speed)` → mono float32 @ 24 kHz contract the two `Tts` classes hold.

### Changed

- **Reading now starts when the first sentence finishes typing, not when the line does.** Sentence streaming only fired when the typewriter happened to *pause* on a sentence end — the read waited out a full-line hold (`STABLE_READS + 4`, ~1s at 6fps) whenever the next sentence had already started rendering, which is most multi-sentence lines. A line whose text is still growing frame over frame is now clipped to its longest closed sentence, and the clipped head repeats identically while the rest types, so it stabilizes in the normal two reads (~0.3s) instead. The remainder is spoken afterwards through the existing extension path, which diffs against what was already said.

  Two guards keep it from chopping a single thought in half. The clip only applies while the raw read is actually *growing* — clipping a static line would be a trap, because its text never changes again, so the tail would never arrive as an extension and half the line would be lost (OCR does drop a final period). And a boundary is terminal punctuation followed by the start of a new sentence, so "3.50 mora" and "Mr. Ito" don't qualify; "…" is deliberately excluded, since in these games it is a pause the typewriter runs straight through. `tools/test_stream_prefix.py` pins both directions. Verified against a recorded HSR scene: same lines covered, each one's decision reached a sentence earlier.

- **Names Kokoro read wrong now have spoken forms — including 66 character names.** Paimon came out "PAY-mun" (`pˈAmən`) and is respelled `Pah-ee-mahn` → `pˈɑˈimˈɑn`; Reignbow came out "ree-INE-bow" (`ɹˌiˈInbO`) → `Rainbow`; Ishtar came out "ISH-tar" (`ˈɪʃtˌɑɹ`) → `Esh-taar`. `settings.pronunciations` applies at synthesis only, so logs, dedupe and casting keep the real spellings — and the substitution is case-insensitive and word-bounded, so possessives ("Ishtar's") carry through.

## [0.7.3] - 2026-08-08

### Fixed

- **Lines were cut off mid-sentence in a scene with no voice acting in it.** The late-VO yield stops playback the moment the game starts talking over us, and it was reading the feed at the most sensitive setting the app has, unconditionally — a VAD probability of 0.12 across three 32ms chunks. Natlan's vocal music clears that comfortably. Four lines of one Genshin quest were cut off partway with nothing audible taking over, and in the recording of it the captured audio is silent for eleven seconds after the cut. The comment justifying the setting said the worst case was "merely clips our own playback", which is the failure the feature exists to prevent, not an acceptable cost of it.

  The yield now reads the evidence at the same sensitivity that decided to speak in the first place — the per-speaker prior, so the faintest hint still stands us down for a character the game has voiced before, while a character it has never voiced needs real speech. `settings.late_yield: false` turns it off outright, which is the one-line way to prove whether a yield is involved at all. Every yield now logs how far into playback it fired and what it heard (peak probability, strong and weak hit counts): a yield that saved you from talking over the game and one that swallowed half a line were previously the same line in the log, and they want opposite fixes.

- **A stalled capture silently amputated the recording in progress.** One ffmpeg owns both the capture device and the recording, and the stall watchdog respawned it with no record path — so video stopped at the stall while `recording["on"]` stayed true, and clips and the audio slice kept accruing on wall clock. The session that found it muxed a 28.5s video against 264.9s of sound: every line of the dialogue it was recording had no picture, and the file was useless as a replay case. The recording now continues into a new segment, which the mux stream-copies back together, and the window where nothing was captured is cut out of the audio and out of the TTS clip offsets so everything after a stall stays in sync.

  How long that window was has to be **measured**, not inferred. The first attempt took it from how long the stall watchdog had been waiting, which sounds equivalent and isn't: the frame file stops updating before the encoder does, so a real stall that the watchdog timed at 10.4s had only lost 6.2s of video, 4.2s too much came out of the audio, and everything after the gap was 4.2s out — a recording that looks fine until the voices drift. The mux now ffprobes each segment and takes the gap as the wall time between the end of one segment's video and the start of the next. If ffprobe can't answer, nothing is cut rather than guessed. `tools/test_video_swap.py` pins the respawn, the measurement and the gap arithmetic.

- **The dashboard's feed preview returned a 500 on Windows.** ffmpeg replaces `live_frame.jpg` by rename, and opening it in the instant between the two raises `PermissionError` there rather than returning stale bytes — so a preview refresh landed a Flask traceback in the session log. One retry covers the rename window; a second failure returns a 503 the dashboard simply refreshes past. Also swaps `Image.getdata()`, deprecated and removed in Pillow 14, for its replacement where the installed Pillow is new enough to have it.

### Added

- **A pixel change gate skips OCR while the dialogue is static.** ffmpeg rewrites the frame file continuously, so mtime can't tell a static line from a new one — the loop paid a full OCR call per sampled frame (115ms on DirectML, a Vision call on macOS) even while text sat unchanged on screen, which is most of the time. `tools/change_gate.py` decodes the frame at half scale (~1ms) and compares the pixels under the blocks the last read built its line from, counting how many *bright* ones moved: game text is light-on-dark, so the world animating behind a static line moves dark pixels while any text change — including brand-new text — moves bright ones.

  Two things about that comparison are what make it safe, and a Genshin session taught both. It has to watch the line's own blocks rather than every block on the frame: Genshin's UID sits bottom-right and the HUD top-left, so the union of all of them is the whole screen, and the verdict ends up being about the scenery. And it has to count the pixels that moved rather than average them — a mean is diluted by everything in the region that didn't change, and on a daylit scene a few hundred new glyph pixels averaged out to 0.06 against a threshold of 6.0. Under those two faults the gate called a frame unchanged while the typewriter was still typing, and four of nineteen lines in that session were spoken half-typed ("…friends with the great sh", with "aman Citlali…" arriving after it as a separate line). The allowance for what may move is capped below a single glyph, so a box full of bright scenery can't buy itself one.

  An "unchanged" verdict replays the previous blocks through the normal pipeline rather than skipping the iteration, so stabilization counting, chat settle checks and panel-close detection tick exactly as before; every ambiguous case (torn frame, moved boxes, no box with text in it) fails open to a real OCR call.

  The gate may *defer* an OCR call but never cancel one, and that is a stronger guarantee than it sounds: a wrong "unchanged" replays blocks that describe the same boxes, which are still unchanged, so nothing inside the loop breaks the cycle. A session found exactly that — a screen with no dialogue left a lone nameplate-shaped block behind, the gate narrowed onto that one scrap of static UI, and the pipeline read nothing for 47 seconds until the capture respawned and broke it. So no more than twelve frames may be skipped in a row: any wrong verdict costs about two seconds instead of the rest of the session.

  It also does not run at all until there is a line on screen. Watching every block on a frame with no dialogue looked like the safe direction — more boxes, more ways to notice a change — but the gate can only see where text *already was*, so a line appearing on a screen that had none lands outside every box it is watching and reads as unchanged. Measured against ground-truth OCR over 1650 frames of a Genshin conversation, that accounted for 10 of 17 stale verdicts; waiting for a line costs 11% of the skips and removes 76% of them.

  `settings.change_gate: false` disables it, `settings.change_gate_frac` tunes it, and the dashboard shows OCR calls saved. `tools/test_change_gate.py` pins thirteen invariants — synthetic frames, no hardware, ~1s — including a bright scene with chrome in the block list walked through the typewriter one glyph at a time, and a frozen screen that must still be re-read. Measured over that same recording: 23% of OCR calls skipped, with lines spoken identical to 0.7.2 and settling about 0.12s sooner (numbers and method in `plans/OCR-INTEGRATION-PLAN.md`).

### Changed

- **Stabilization listens to the recognizer's confidence.** `classify()` now reports the weakest confidence among the blocks that made the line, and the stabilizer uses it two ways: a high-confidence read (≥0.97) at a typewriter pause skips the sentence-streaming cushion read — the cushion exists to ride out shaky mid-render reads, and the recognizer already vouches for this one — while a shaky read (<0.85, the mid-fade "started shan ing" class) must earn one extra sighting before it can be spoken. Confidence also breaks ties in best-read voting when the real-word fraction can't. Engines without confidences report 1.0, leaving behavior exactly as before; measured on an 81-shot corpus, settled lines sit at 0.97+ (55 of 78 with the English rec model) and only visibly damaged reads fall under 0.85.

- **Windows OCR reads English at the source.** RapidOCR's bundled recognition model is Chinese-trained; on English game text it drops spaces ("Everythingis going smoothlymy nobleKing.", "RinTohsaka") and the pipeline repaired the damage statistically after the fact. `tools/ocrd_win.py` now loads an English-trained recognition model (en_PP-OCRv5_mobile_rec, ONNX) when present — `setup.ps1` downloads it to `models\` (~8 MB), `HOYOVOICE_REC_MODEL`/`HOYOVOICE_REC_KEYS` override the path, and deleting the files falls back to the bundled model. Detection is untouched, so box geometry and every classify decision stay put. Measured over an 81-shot corpus: fusion-class defects 333 → 144, 22 frames of nameplate fixes ("MysteriousGoldy" → "Mysterious Goldy", "Sparxile" → "Sparxie"), two frames where a dropped nameplate came back, three info screens that had been misread as loading/dialogue now classify as reader panels with clean text, zero regressions.

## [0.7.2] - 2026-08-07

### Fixed

- **A spoken choice option had no speaker to cast.** It fell through to the narrator and logged with an em dash where the name goes, so there was no Casting row and no way to give the player character a voice of their own. Options are now cast under the player character's name for the active game — `Traveler` in Genshin, `Trailblazer` in Star Rail, `Player` otherwise — which auto-casts on first use and appears in Casting like any other character. `settings.choice_speaker` still overrides the name (for a Traveler you've named Aether, say).

## [0.7.1] - 2026-08-07

### Changed

- **A choice prompt with a single option is now read aloud.** With nothing to choose between, the game isn't offering a menu so much as putting words in the player character's mouth, and the option reads as part of the scene; two or more options are a real menu and stay logged-only, as before. `settings.choice_speaker` gives the option a voice — the Traveler, say — otherwise the narrator reads it.

  Getting the order right is the whole problem: the option bubble renders complete while the line beneath it is still typing, so a naive read speaks the answer before the question. The option is therefore held until the line under it has been through the gate (spoken, deduped, or skipped as voiced), then read into the first gap where our own voice is idle and the game's has stopped — the line may be voiced even when the option is not. It is deliberately not conditional on the option still being on screen: players click through while the line is still being read, and requiring it would mean the option is almost never read at a natural pace. What bounds it instead is time — an option that finds no gap within 8 seconds is dropped rather than arriving several beats late, and logged as `choice prompt (not read — too late)`. A spoken option also joins the dedupe window, since picking a lone option usually makes the game say it straight back as a dialogue line.

  Both paths verified against the calibration recording: the prompt in a stretch with a pause was read in order, after its line; the one in wall-to-wall dialogue found no gap and was logged unread.

## [0.7.0] - 2026-08-07

### Added

- **Per-game layout profiles (`tools/profiles/`), and the beginning of Genshin Impact support.** Screen classification was written against Honkai: Star Rail and had its geometry and chrome assumptions spread through one module — including the rule that gates every unknown speaker's line on the `✕ Continue` hint, which Genshin does not draw at all. That single check is why a Genshin frame whose nameplate and line both read correctly still ended in `skipped (unknown speaker, no Continue hint)`. The bands and detectors now live in a profile per game behind a shared base, and the gate asks the active profile what its story chrome looks like — Star Rail's Continue hint, Genshin's auto-play toggle. `settings.game` (`auto` | `hsr` | `genshin`) and a dashboard dropdown select one; `auto` switches on a sustained run of frames carrying chrome unique to the other game, deliberately sticky so a single misread can't swap layouts mid-conversation. `tools/replay.py --game` pins a profile for a replay. The Star Rail path is unchanged — verified by fuzzing 20,000 randomized frames through the pre-refactor classifier and the new profile side by side, all ten detectors exercised, zero differences.

- **The Genshin profile, calibrated against a real session** (a 4-minute Natlan world quest: 198 dialogue frames of 281). Dialogue screens, choice prompts, full-screen narration and loading-screen tips are all read from measurements off that capture; nothing is enabled on a guessed band, because a wrong one doesn't fail quietly — it narrates menus. Each `CALIBRATE` comment in `tools/profiles/genshin.py` names the capture still needed for what remains. What the capture changed, measured over those frames — 0 lines readable before, 196 parsed cleanly after:
  - Genshin's nameplate can carry a second, smaller line: the speaker's role ("Pucli" over "Entertainment Supervisor"). It lands exactly where the first dialogue row would, and was being read aloud as the opening words of every one of that NPC's lines — 100 frames of the capture. What separates it from a real row is how tightly it hugs the plate (0.023–0.031 below its baseline, against 0.041–0.063 for a first dialogue row); font size does *not*, since Vision returns anything from 0.016 to 0.029 for the same subtitle depending on which glyphs it catches.
  - Rows are accepted across the whole text column instead of by Star Rail's centered-seed test. Genshin centers each row, but only once it is fully typed — the typewriter reveals a row rightward from its final left edge, so a half-typed row's center sits far left of the axis, and the centered test dropped those rows entirely.
  - Stylized nameplates read weakly: 25 of 197 plate reads came back at confidence ≤0.5 (`"Tenoyollotzin"` on 22 of them) against 1.0 for the dialogue rows. The plate slot now has its own lower floor — it is constrained by geometry rather than by text — because at 0.8 those frames lost their speaker *and* fell back to the plate-less band, which is what pulled the role subtitle in.
  - Loading-screen tips ("Elements", "Elemental Reaction") are read by the narrator. These were being caught by the Star Rail *lore card* detector, which happens to work only when the OCR engine misses the permanent bottom-right UID — true for the Windows recogniser on that art, false for Apple Vision, so the same screen read on one platform and was silent on the other. Genshin's own detector tolerates the bottom strip, which is on screen in every context here. It needs two signals to fire, not geometry alone: once the strip is discounted, a loading card and a dialogue box have the *same* shape — a short centered heading over centered prose, in the same band — so a loose rule doesn't merely miss loading screens, it swallows every line of dialogue and narrates it, nameplate included (measured: 117 of 281 frames, before the chrome and plate-floor tests were added; 1 after, the loading frame itself).
  - Choice prompts are parsed: options float right of the box, left-aligned past a chat-bubble icon at x 0.686–0.689. A wrapped option's second row is set smaller than its first (0.019 against 0.024), so Star Rail's 0.020 height floor cut it off mid-sentence. Two findings came out of the same frames: a pending choice **hides** the auto-play toggle, so `trusts_dialogue` counts an on-screen option as story chrome in its own right — otherwise a not-yet-cast speaker is skipped at exactly the moment the game is asking the player something — and the teleport map lists its waypoints in the same column at the same left edge, reading as a three-option prompt, so both the trust rule and the choice list require a nameplate, which the map has none of.
  - Star Rail's "a plate with nothing under it is not a plate" re-parse is off here. Genshin's plate band starts above any dialogue row, so the re-parse has nothing to rescue and would read the plate's own rows as speech.

- **Choice prompts appear in the log, and are never spoken.** The options are not reliably one kind of text — sometimes a menu the player picks from, sometimes the player character's own lines about to be said aloud — so reading them would be right half the time, and wrong here means talking over the scene. They're logged as `choice prompt (not read)`, once per prompt, before the branches that might skip the line itself, so the options are visible even when the line is not. Applies to both games; a prompt has to survive two frames before it is logged, since OCR jitters the first sighting.

### Fixed

- **`tools/replay.py` could not replay anything on macOS.** The replay backend imported the *Windows* OCR daemon unconditionally ("same daemon, runs anywhere") — but it needs `rapidocr`/`winsdk`, so on macOS it died on every frame and respawned in a loop until the replay ended, having read no text at all. The host's daemon is chosen now; both speak the same protocol. The documented claim that replays run on either platform is true for the first time.

- **Stopping a recording froze reading for several seconds.** The main loop closed the recording MKV and respawned the capture inline, so `finalize()` — which waits for ffmpeg to flush, seconds on a long take — held up OCR and every reading decision at exactly the moment a line is usually on screen. Both steps now run on a worker; the loop reads straight through the handover, and the stall watchdog stands down while a swap is in flight rather than respawning on top of it. Because one ffmpeg owns both the capture device and the live frame file, every restart and finalize — on the loop or off it — is serialised behind a single lock, the mux is sequenced after the MKV is genuinely closed instead of racing it, and shutdown waits out an in-flight swap so the worker can't respawn an orphan capture over the next run's frames. `tools/test_video_swap.py` pins all four invariants against a fake capture with ffmpeg-like timing, in about two seconds and with no hardware.

- **Short dialogue lines were read as the nameplate, and vanished.** The nameplate was picked as the *tallest* candidate in the plate band — but HSR renders dialogue in a larger font than the nameplate, and a short line ("The beach!", "A bicycle station.") is narrow enough to pass the plate width filter and sits at cy≈0.189, just inside the plate band. So the line itself became the speaker and the dialogue band, anchored below it, came up empty. Un-nameplated narration was dropped in complete silence — the skip log only fires when there *is* text — while a nameplated short line flickered between correct and hijacked frame to frame, resetting stabilisation until it eventually read tens of seconds late. The nameplate is now the *topmost* candidate, a plate that yields no dialogue is discarded and the frame re-parsed without it, and the fallback dialogue band was widened to 0.21 so a row jittering upward is not clipped. Measured on a session recording: "A bicycle station." 0 → 34 usable frames, `"?" you wonder.` 0 → 24, "The beach!" 15 → 39.

## [0.6.1] - 2026-08-03

### Fixed

- `setup.sh` did not install `flask` or `vaderSentiment`, and nothing else pulls them in — a fresh macOS clone installed cleanly and then failed at import. Both are now declared, along with `numpy`, which `live.py` imports directly but only received as a transitive dependency. The no-capture-device warning also pointed at a `live.py` constant removed several releases ago; devices are chosen by name from the dashboard.

### Changed

- README documents what 0.6.0 actually shipped: message/group-chat panel reading, sentence streaming, screen-kind labels in the log, and the log download button. OCR repair is now split by platform, since the Windows text repairs (space restoration, run-on splitting, best-read selection) exist for a recogniser macOS doesn't use. Adds a **Debugging a session** section covering the log download and `tools/replay.py`. `setup.sh` records why `wordfreq` is deliberately absent there but present in `setup.ps1`.

## [0.6.0] - 2026-08-03

### Added

- **Windows 10/11 support.** The pipeline now has a platform backend layer (`hv_platform/`) and runs natively on Windows: DirectShow video capture, in-process WASAPI audio, an OCR daemon (`tools/ocrd_win.py`) speaking the same protocol and coordinate convention as the Apple Vision one, Kokoro TTS through ONNX Runtime, `setup.ps1`, and a cross-platform `hoyovoice.py` launcher. `voices.json` carries over unchanged — the voice IDs are identical on both platforms. RapidOCR on DirectML is the recommended engine (~120ms/frame); the built-in Windows OCR is a fallback. Getting there meant solving a series of platform-specific problems, all handled internally: frames are read as validated complete images (a JPEG caught mid-rewrite yields no text at all), the background is flattened before recognition so light subtitles survive a blown-out sky, playback tracks the duration implied by its own sample count because PortAudio reports a stream idle while WASAPI is still sounding, and the Chinese-trained recognition model's habit of dropping spaces is repaired in post. See `plans/WINDOWS-TESTING.md` for the first-run checklist and the platform quirks worth knowing.

- **Message/group-chat panel reading.** Phone conversations are read incrementally as you scroll, each sender in their own cast voice, with system notices ("… started sharing location") read by the narrator since they're events rather than speech. Sender labels are canonicalised per conversation — OCR renders the same small label several ways — and messages whose label has scrolled off-screen inherit the conversation's name rather than falling back to the narrator.

- **Lore cards** — full-screen title-and-prose screens carrying no UI chrome — are recognised and read by the narrator. Their title reads as a nameplate to the dialogue classifier, so they were previously skipped as an unknown speaker.

- **Sentence streaming.** The typewriter pauses at sentence boundaries, so a completed sentence is spoken at that pause instead of waiting for the whole line; the remainder follows once it renders, after the first part finishes.

- **Per-speaker voiced prior ("soft gate").** Some voiceover sits below every audio threshold that can safely be used: measured on a real capture, a voiced line peaked at 0.18 on the speech detector while a genuinely *unvoiced* line in the same scene showed more sub-threshold activity — no global threshold separates them, and lowering one would silence the unvoiced lines this app exists to fill in. HoyoVoice now tracks how often each speaker turns out to be voiced and, once that's consistent, accepts much weaker evidence before talking over them. For a character with a real voice, silence is the safer error. It self-corrects: every line spoken for a character counts against the prior.

- **Session replay harness (`tools/replay.py`).** Any dashboard recording replays through the real pipeline — actual OCR daemon, classification, stabilisation, dedupe, VAD gate and yield, with only capture, TTS and playback simulated — in a throwaway state directory that can't touch real casting or caches. Every reported problem becomes a reproducible test case.

- **"⤓ Download log" button** in the dashboard. Saves one text file with the environment, live analytics, the casting table, the full decision log and the noise-filtered console log — enough to diagnose a session without a screenshot.

- **Screen kinds are labelled in the log** (`loading screen`, `lore card`, `narration`, `overlay`, `chat`, `chat notice`), on skips as well as reads, plus a `lost frames` analytic counting frames the OCR daemon couldn't read at all.

### Changed

- Platform code (capture, audio, OCR daemon, TTS, playback) moved out of `live.py` into `hv_platform/darwin.py` and `hv_platform/win32.py` behind a shared interface (`hv_platform/base.py`). macOS behaviour is intentionally unchanged.

### Fixed

- **Real voiceover was spoken over when the audio reader fell behind.** Under load the VAD tail-reader could trail the live edge, stamping stale audio with fresh timestamps — so the gate judged "now" against sound from minutes earlier. Backlogs over a second are dropped and the dashboard shows `LAG Xs`.

- **HoyoVoice kept talking when voiceover started mid-line.** The late-VO yield used the same strict thresholds as the gate, so it often never fired. Our own TTS is not in the capture — it plays on the computer's speakers — so any speech heard during playback is game voiceover by definition, and the yield now acts on much weaker evidence.

- **Loading-screen lore was silently skipped as a repeat.** The dedupe window persists across restarts so that restarting mid-scene doesn't re-read the line still on screen, but it never expired — so a loading screen seen every session was suppressed by a read from the previous one. It now goes stale after ten minutes.

- **A line already on screen could re-trigger, and a partly-read nameplate could split a character in two.** Stabilisation was keyed on speaker *and* text, but the nameplate read jitters independently of the line ("Goldy" for "Mysterious Goldy"), restarting the cycle. Jittered re-reads now continue stabilising the same line, and partial nameplates snap to the cast member by containment instead of auto-casting a duplicate with a different voice.

## [0.5.1] - 2026-07-27

### Fixed
- **False "skipped (voiced)" on fast subtitle transitions**: the VAD gate's 2s lookback could reach back before the current line appeared, so the *previous* speaker's voice-over tail counted as evidence that the new line was voiced (confirmed by replaying a session recording through the gate). The gate window — including the wait loops, center-energy speechiness floor, and the `gate=` log value — is now anchored to when the line first appeared on screen.

## [0.5.0] - 2026-07-26

### Added
- **Center-energy VO detector**: mid/side stereo analysis with a speechiness floor catches robot and vocoder voices the speech model can't recognize — music swells (both channels) and center-panned SFX (no speechiness) are rejected
- `settings.pronunciations`: spoken-form substitutions applied at synthesis only ("Wishpower" → "Wish power")
- `settings.custom_words` + casting names fed to Apple Vision as a recognition vocabulary
- Reading repairs: OCR-dropped apostrophes restored via a safe contraction dictionary ("youre" → "you're"), decorative glyphs stripped ("~"), interjections voiced as words ("shh" → "shush"), expanded I/l fixes incl. capitals and stutters
- Bright cutscene narration reads via prose self-certification (previously only black screens)

### Fixed
- Ghost-box double reads (text fade-in makes Vision return overlapping stale + full boxes)
- Tail-fragment re-reads when VFX briefly hide a text row (substring/containment dedupe)
- Dialogue split across OCR fragments rejoins its visual row
- Log text selection is no longer interrupted by the refresh; recordings list is a fixed scrollable panel

### Removed
- Legacy `tools/ocr.swift` one-shot (superseded by the `ocrd` daemon)

## [0.4.0] - 2026-07-26

### Added
- **Auto-casting**: every newly met character claims a distinct voice from a gender-guessed pool instead of sharing one default — scenes full of new NPCs sound like an ensemble. Auto-cast entries show as "(auto)" in Casting and persist; a manual assignment clears the tag. Pools reuse the least-assigned voice only when exhausted.

## [0.3.0] - 2026-07-26

### Added
- Pre-cast characters from the dashboard (**Add cast** form) before they appear in-game
- `settings.text_fixes` lexicon for proper nouns OCR mangles ("lason" → "Iason")
- Gender guess from name shape for unknown speakers (casting table remains authoritative)
- `settings.dashboard_bind` — open the dashboard to other machines you trust
- Dashboard: version in header, friendly voice labels ("Heart (AF)"), scrollable recordings panel, paused-feed placeholder

### Changed
- Dialogue detection is anchored to the nameplate — overworld and cinematic layouts both parse, wherever the box sits
- Split OCR fragments rejoin their visual row ('Error: Term' + '"Berserker"…')
- Typewriter-aware pacing: lines still growing (or ending mid-sentence) wait to be spoken whole; when a split does happen, the remainder is spoken after the prefix finishes instead of being skipped or interrupting it
- Kokoro clip silence trimmed: snappier line starts, tight extension handoffs
- Black narration screens with only the ▼ glyph (no "Continue" text) are read, gated by a dark-frame check

## [0.2.0] - 2026-07-25

### Added
- Web dashboard at http://127.0.0.1:8470 — live log (voice used, per-event 📷 screenshot previews, replay, Hide/Clear), casting table (assign with instant re-read, mute checkboxes, delete), pause/resume, test-speech box
- Live video preview with paused placeholder; video/audio **device pickers** with hot-swap, persisted in settings
- In-app **recording**: game video + game audio + TTS clips muxed at exact wall-clock offsets (+8dB TTS boost, yield-trimmed clips), crash-safe MKV raw, configurable save folder
- Performance analytics: VAD health, OCR/synth timings, spoken/skipped/yielded counts, lines per minute
- Sentiment-aware delivery: line sentiment nudges speech pace (excited faster, somber slower)
- New screen types: Quick Read books (incremental scroll reading), info screens (Participant Details), loading-screen lore, floating host bubbles (`settings.overlay_speaker`), system screens silenced
- Menu/board rejection: dialogue must be centered; unknown speakers and narration require the ✕ Continue hint
- Speaker hygiene: quoted names are distinct characters, org/location names route to narrator, sentence fragments can never register
- App starts paused; resume from the dashboard

### Changed
- Dedupe is a sliding 3-message window (fuzzy-matched) instead of permanent — replayed quests re-voice
- Latency reduced to ~0.5–0.7s (6 fps sampling, speculative synthesis during the VAD gate, 0.2s wait)
- Capture devices selected by name, not index

### Fixed
- Recording audio ran ~12% fast with crackling: ffmpeg's AVFoundation audio input silently drops ~12% of capture-device samples. Audio moved to sox/CoreAudio (bit-perfect); ffmpeg is video-only; recordings slice the continuous sox stream — no resampling anywhere
- Two-tier VAD gate catches short/soft VO that never crosses the strong threshold; VAD pipeline made non-blocking and lag-free
- OCR "l"/"I" confusion repaired before synthesis
- Capture auto-recovers from device resolution changes, unplug/replug, and OCR daemon crashes

## [0.1.0] - 2026-07-25

### Added
- Live capture pipeline: PS5 → Genki ShadowCast 3 → ffmpeg (4 fps frame sampling + 16 kHz audio tap)
- On-device OCR via Apple Vision (`tools/ocrd` daemon, compiled Swift)
- Dialogue classification for Honkai: Star Rail standard layout (speaker / dialogue / choices)
- Full-screen black narration layout detection
- Kokoro-82M local TTS via mlx-audio with per-character voice registry (`voices.json`)
- Voiced-line gate: Silero VAD (onnx, no torch) skips lines the game already voices
- Late-VO yield: our playback cuts instantly if game VO starts mid-line
- `always_voiced` registry list for characters whose VO evades speech detection
- Fuzzy line dedupe (normalized text + similarity match) persisted across restarts
- Startup audio warmup to ignore capture-stream transients
- `hoyovoice.sh` control script (start / stop / status / log / restart)

### Known issues
- `af_nicole` voice is broken in the prince-canuma/Kokoro-82M package
- Genshin Impact layout profile not yet implemented
- Choice options are detected but not spoken
