# HI75 stock V5 capabilities audit — 2026-10-21

This audit started with Scan's stock firmware backup and now includes
read-only live captures and offline execution of stock instructions. No keymap,
macro, installed app or device firmware was changed. Firmware presence and
simulator results are not end-to-end validation of a GTK feature.

## Sources and confidence

All paths below are relative to
`historical-investigation/`:

- `outputs/hi75/stock-v5-decompiled/stock-v5.pseudo.c`
- `outputs/hi75/stock-v5-decompiled/stock-v5.instructions.asm`
- `work/hi75/stock-lighting-research/stock-switch-tables.json`
- `outputs/hi75/v5-backup-20261010-155858-2173101f/full-1.bin`
  SHA256: `c72398567294743c236e5bc07bbed9245fe6147ac718375bb80d76c8f673f6bb`.

The pseudocode uses an imperfect generic 8051 ABI; original symbol names are not
available. In particular, the giant false switch inferred inside 4F8A is NOT a
capability inventory. This audit uses the recovered 7016 switch, relevant helpers,
actual ROM bytes, and assembly to establish record byte order.

## Confirmed firmware mechanisms

| Capability | Code evidence | Remaining work for GTK |
|---|---|---|
| Ordinary key remapping | 3108 loads four-byte flash records; 6FFD dispatches the action type; 8B23 applies keyboard usages | Readback/upload transport, physical key mapping, preservation and restoration tests |
| Modifier combinations and two-key chords | 8B23 applies 0D12 as modifier bits and both 0D10/0D11 as usages | UI encoding and real press/release verification |
| Alternate/Fn mappings | 3108 uses alternate banks with zero-record fallback; A564 maintains Fn state | Label exact bank/mode relationships; do not assume four arbitrary user profiles |
| Media/consumer controls | Action type 2 calls 001E, producing a two-byte consumer report value | Validate individual usage assignments |
| Mouse actions | Action type 1 calls 7CCB; button and repeated-action state is handled there | Finish motion/repeat dispatch, especially unreliable 4F8A decompilation |
| Onboard macros | Type 3 -> 9B1F; 4A1E reads sequences from flash; 7FED schedules playback | Validate storage allocator, delays, upload/readback, repeat and cancellation behavior |
| Macro keyboard/modifier/mouse events | 4A1E branches to 943A, A4F2, A9C4 and motion report fields | Offline execution tests and controlled hardware validation |
| Windows-key lock | System action 1 at 2D65 toggles flag 9.6; A4F2 masks modifier bits with 77; 8B23 also filters usage 65 | Expose the correct config bit with readback |
| General action lock | System action 2 at 2D88 toggles flag 9.5, checked by multiple action handlers | Verify exact physical-key behavior before naming it in UI |
| Layout/OS-style modes | System actions 24–27 set 0324 to 0–3; 3108 selects base/Fn mappings according to that state | Determine user-facing mode names and override rules |
| Knob's stock dual behavior | 2F9B handles system action 29: consumer mute or lighting-mode cycling depending on state 0323 | Arbitrary knob remapping is not established by this audit |
| Stock lighting, direction, speed, brightness and palettes | 9E11 and its branches; existing lighting audit | Some controls are already implemented; arbitrary onboard color edits remain incomplete |
| Persistent custom lighting | Command 6 at 0505 targets CA00 plus bank offset, preserving bytes beyond 378; mode 32 calls 8C98 | Trace activation/profile selection and validate save/readback before replacing host-streamed Solid |
| Persistent color palette data | Command 10 at 0584 targets C800 plus bank offset | Determine safe palette record editing and preserve unrelated page bytes |
| Keyboard report variants | A20A sends the eight-byte keyboard report; 63F8 also sends the bitmap report built by 943A | Do not infer the active rollover mode merely from code presence |

Shared firmware contains alternate transport/channel branches, including guarded
0317 paths and channel selection. This does not prove the wired HI75 has radios
or supports Bluetooth/2.4 GHz. The driver's KB.ini is supporting context only;
its lighting labels were already shown to mismatch this firmware.

## Key record format

Flash record bytes in address order:

`[action_type, arg2, arg1, arg0]`

4345 loads the four bytes into R4..R7 in that order. 3108 stores the low byte in
0D10, then shifts by 8/16/24 to fill 0D11/0D12/0D13. The 7016 switch uses 0D13.
This is why a normal Escape record is `00 00 00 29`, not type 29.

| Type | Meaning | Arguments |
|---|---|---|
| 0 | Keyboard | arg0/arg1: key usages; arg2: modifier mask |
| 1 | Mouse | Partially decoded; do not build encoder from assumed HID bytes |
| 2 | Consumer/media | arg0 + (arg1 << 8) is the consumer usage |
| 3 | Macro | arg0: macro index; arg1: repeat count; arg2: playback mode |
| 4 | Vendor host notification | Not an onboard program launcher; A706 emits vendor report state |
| 7 | System action | arg0 selects the 2D1E switch |
| 8 | Lighting action | 9E11 dispatches on arg2 |
| 9 | Four-state selector | 7089 changes 030A in the range 0–3; full semantics unresolved |
| 13 | Fn state | A564 changes Fn flags according to arg2 |

Eight 512-byte tables occupy CC00..DBFF. Each has space for 126 four-byte logical
positions plus eight trailing bytes. These are logical matrix positions, not 126
physical keys. Do not overwrite the trailing bytes or treat unused positions as
visible keys. Tables are selected by alternate-key state, OS/layout state and
0309; eight tables does not mean eight user profiles.

The generated `backup-inventory.json` confirms:

- CC00: 82 nonzero actions, including 80 keyboard records, Fn and knob/system.
- CE00: 84 nonzero actions, including consumer and lighting actions.
- D000 / D200: 30 / 29 nonzero alternate actions.
- D400 / D600 / D800 / DA00: no nonzero action records in this backup.

An all-zero alternate record can mean fallback, so it is not necessarily a way
to disable a key. Physical layout conversion and Fn/OS overrides must be handled
before introducing a remapping UI.

## Macro storage and playback

4A1E reads a four-byte directory entry at `DC00 + macro_index * 4`. The first
pair is a little-endian offset relative to DC00; the second pair supplies a
length. At the referenced location, a leading byte specifies a header/prefix
length. Playback skips that byte and prefix and processes four-byte events.
Do not assume the prefix is a UTF-8 name; its contents have not been established.

The command-5 write handler (04E5) targets `DC00 + page * 0200`; the smaller-report
handler at 0AAC explicitly covers eight pages DC00..EA00, suggesting a 4 KiB
macro storage window. This does NOT establish eight macro slots. Directory
capacity, allocation rules and boundary checks are still to be determined.

In a macro event `[flags, delay_part_1, delay_part_2, value]`:

- flags bit 7 selects release versus press for key/modifier/button events.
- flags bits 4–6 select the event category:
  - 0: keyboard usage, helper 943A.
  - 1: modifier index, helper A4F2.
  - 2: mouse button mask, helper A9C4.
  - 3/4: signed movement fields X/Y, expanded into 16-bit report fields.
  - 5/6: two scrolling fields in the mouse report.
- Delay setup is at 4BFA onward; 7FED decrements counters before the next event.
  The decompiler's shift/sign-extension expression is unreliable. Even the
  decoded 16-bit shift loop needs execution validation. No milliseconds encoding
  or maximum duration is claimed yet.

9B1F and the end-of-sequence path in 4A1E implement:

- Mode 1: counted repetition, decrementing the requested count.
- Mode 2: repeat with a stop-on-subsequent-key path in 6FFD.
- Mode 4: repeat with a release-stop path in 9B1F.

These are code-derived semantics, not hardware-tested UX names. Repeat count zero
must not be offered as “play once”: the decrement behavior can underflow.

The entire DC00..EBFF window is zero in the historical backup. Thus there is no
saved real macro example here to validate allocation, timing or round-trip
encoding against. The previous Studio SMK editor's eight slots / 32 events per
slot are for custom firmware and must not be copied into the stock backend.

## Persistence / implementation boundary

The large feature-report command dispatcher contains:

- 3 -> 04AD: table destination CC00 / D000 / D400 / D800 according to header state.
- 4 -> 04DF -> ABD3: configuration page C600 (already used by GTK lighting).
- 5 -> 04E5: macro page DC00 + page * 0200.
- 6 -> 0505: custom lighting page CA00 + page * 0200.
- 8 -> 056E: live RGB in RAM (existing host-streamed Solid).
- 10 -> 0584: palette page C800 + page * 0200.

AB3E/A252 perform a 512-byte page operation through the erase/write helpers.
A remap edit therefore needs a full-page read, backup, preserved-byte patch and
readback verification. The presence of these write handlers is not a validated
USB upload recipe: header offsets, read commands, bank bounds and activation
behavior still require tracing. This audit deliberately adds no write commands.

Recommended implementation order: read-only keymap view, single ordinary-key
remap with exact restoration, modifiers/media/Fn, then a small balanced macro
with deterministic delay and repeat semantics. Macro editing can follow once
storage and cancellation have been validated. Keep all functions on stock
firmware; a firmware replacement is not required by the mechanisms found here.

## Reproduce the offline inventory

Run `python3 inspect_backup.py /path/to/full-1.bin > backup-inventory.json`.
The script opens only its input file and prints JSON. For this audit its output
hash was matched to the original backup; known Escape and Shift records were
checked against the recovered byte order. This is a table inspection, not a
macro execution test or device compatibility test.


## Follow-up: live reads and instruction execution

### Live transport

`live-tables.json` contains all eight 512-byte keymap pages (CC00–DBFF) and
all eight macro pages (DC00–EBFF). Each page was read twice and compared exactly.
Both regions match the historical backup byte for byte; macro storage is empty.
Configuration before and after these reads was identical.

Read request header (followed by 512 zero bytes):

- Keymap: `06 83 group 00 01 page 00 02`, group = bank // 2, page = bank % 2.
- Macro: `06 85 00 00 01 page 00 02`, page = 0..7.
- GET_FEATURE returns 520 bytes including the eight-byte echoed header.

The capture needed 38 attempts for 32 valid page reads. Failures included EPROTO
and incorrect headers. Their cause remains unresolved. A reader must check the
actual ioctl return length, exact header and repeated payload agreement, not just
whether ioctl raised. The bounded retry is for read requests only; it does not
justify replaying an uncertain flash write. Research reader:
`historical-investigation/work/read_hi75_tables.py`.

### Remap write addressing

Offline execution of 04AD stops at AB3E, before any erase/write operation.
For group 0..3, destination is CC00, D000, D400 or D800 respectively.
Changing the page field to 0, 1 or 7 has no effect on that destination.
Thus the large command-3 writer is NOT symmetric with command-83 read addressing.
The smaller command path (0884–098E) also selects these four bases. Odd pages
CE00/D200/D600/DA00 must not be offered as editable through this assumed recipe.
This conclusion is about these handlers, not proof that no other path exists.

### Macro execution tests

`execution-results.json` records 72 passing stock instruction executions:

- 32 delay encodings, including low-nibble and signed-boundary cases.
- 12 remap destination combinations.
- 14 press/release category cases (keyboard, modifier, button, X/Y, two scroll fields).
- One directory/prefix/event decoding case using synthetic simulator ROM data.
- Three counted-repeat endings, including count-zero underflow to 65535.
- Four scheduler countdown cases.
- Six pending-report flags which pause the delay countdown.

The delay is encoded in event bytes 1 and 2, high byte first. The flags byte's
low nibble is shifted out by the actual instruction sequence; it adds no delay.
Values 0000..7FFF produce that unsigned count. Values 8000..FFFF become
FFFF8000..FFFFFFFF, so a straightforward unsigned 16/20-bit delay encoder is wrong.
The useful single-event delay range is therefore at most 0..32767 ticks; longer
waits need a separately validated representation, not truncation or wraparound.

Clock evidence: interrupt vector 0063 jumps to 7B9F, which calls 7FED. The
SH68F90 datasheet identifies vector 0063 as PWM4. Initialization at 6039 passes
1 to A841; A841 sets period 0BB8 (3000) and PWM40CON=C3 (system clock / 8).
AA18 selects PLL/2 and no system divider: nominal 24 MHz. The resulting period is
3000 / (24 MHz / 8) = 1 ms. Datasheet sections 7.5.4 and 8 PWM registers support
these register meanings; local source is
`historical-investigation/work/hi75/sh68f90-datasheet.txt`.
This is a code-and-datasheet derivation, not measured USB event timing. Report
pending flags 3F,56,38,50,3B,37 stop decrementing the macro countdown, extending
wall-clock time. USB transmission and scheduling must still be measured.

Execution harness:
`historical-investigation/work/emulate_hi75_macro.py`.
It uses a locally extracted Fedora sdcc 4.5.0 simulator, based on
[uCsim](https://github.com/danieldrotos/ucsim), without installing system packages.
No instruction patches were required. The synthetic directory exists only in
simulator ROM memory. Keyboard/modifier tests stop before USB send routines;
flash-address tests stop before the flash helper. These limits are intentional:
C52 emulation does not reproduce the SH68F90 peripherals.

### Still required before shipping

A controlled full-page remap backup/write/readback/restore test; verification of
physical key press/release behavior and reconnect persistence; a macro allocator
with established directory bounds; a balanced macro's hardware execution and
cancellation; and robust recovery for uncertain USB write completion. No Keys or
Macros tabs were added on the strength of these partial results.

## Implementation and hardware follow-up

Keys and Macros are now implemented in the GTK app. See `hardware-write-validation.json`
and `hardware-event-validation.json`: the connected V5 keyboard accepted and read
back a temporary remap and an unassigned macro; a subsequent assigned macro
produced an actual F13 press/release from a physical F12 press, with a measured
19 ms hold for a 20-tick event. Every original keymap/macro byte and the lighting
configuration was restored. These controlled tests supersede the earlier
“no hardware writes” limitation for the tested paths only.

The macro allocator reserves a directory entry for every possible 8-bit macro
index (256 entries / 1024 bytes), allocates outside that region, preserves existing
allocations while saving, and commits the directory last. It rejects incompatible
existing layouts. The shipped editor supports balanced key/modifier sequences,
play-once assignment, main/Fn keymaps, and whitelisted media controls; it does not
expose mouse macros, alternate OS tables, or speculative repeat modes. Startup
readback was verified with the installed helper. A cold power-cycle was not tested.
