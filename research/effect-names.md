# Stock v5 effect names

Verified against the original firmware backup, not the Windows driver's LedOpt
label table. These are descriptive names inferred from code behavior, not strings
recovered from firmware. No lighting commands or firmware writes were used for
this audit. Visual timing and direction have not been re-tested on hardware.

Sources in `historical-investigation/`:

- `outputs/hi75/stock-v5-decompiled/stock-v5.pseudo.c`
- `work/hi75/stock-lighting-research/v5-expanded.asm`
- `outputs/hi75/stock-audit-20261015/effect-dispatch.json`
- `outputs/hi75/v5-backup-20261010-155858-2173101f/full-1.bin`
  (SHA256 `c72398567294743c236e5bc07bbed9245fe6147ac718375bb80d76c8f673f6bb`)

The decompiler has an imperfect 8051 calling convention. Follow the dispatch
entries, assembly and ROM tables rather than trusting inferred C arguments.

| Native ID | UI name | Evidence |
|---|---|---|
| 0 | Off | 1B73 calls AB5A to clear LEDs. |
| 1 | Solid / Static rainbow | 6CB5 draws fixed groups, palette 7 uses rainbow colors. The app's custom Solid is still a separate host RGB feature. |
| 2 | Breathing | 7290 applies the global phase through brightness modulation (98A4); columns have fixed palette offsets for multicolor. |
| 3 | Color cycle | 94D0 advances one global palette phase and applies a uniform color. |
| 4 | Reactive horizontal wave | 17F4 seeds the pressed key in 013B/0001 masks; 5108 shifts those masks across columns, with 5C49 fading the trail. |
| 5 | Falling rain | 91B1 randomly starts a column at row 0 and advances down six rows; 5C49 fades prior pixels. |
| 6 | Split wave | 9F2E loads ROM phase grids 26ED/276B. Top three rows progress across columns in the opposite order to the bottom three; 5821 advances per-key phases. |
| 7 | Reactive ripple | 187E seeds all four masks (08C2/02E8/013B/0001); 5108 spreads vertically and horizontally from the key. |
| 8 | Twinkling stars | A3AD calls 55E8 to seed randomly selected keys, with 5A3E fading them. |
| 10 | Snake trail | 84C6 traverses the six-row, fifteen-column grid in a serpentine path; 5C49 fades the trail. |
| 11 | Horizontal wave | 65C4 assigns a phase per column, same color across rows; advances global phase. |
| 12 | Reactive fade | 194A handles key events; 1CE6 schedules only 5C49 fading. |
| 13 | Alternating ripples | 5108 periodically seeds all four masks at column 6, alternating row 0 and row 5. |
| 15 | Per-key color cycle | 7A72 advances individual key phases through the 128-entry palette at 2A2C. Exact spatial pattern depends on the RAM phase table loaded by A434; this label deliberately does not assert its geometry. |
| 16 | Vertical wave | 8D4D advances global phase and offsets each row by 25, with the same color across columns. |
| 17 | Radial wave | 6CB5 advances palette phase through nine groups at ROM 2618; groups start at (7,2) and expand outward. |

## Removed menu entries

9 and 14 have no initialization case and their scheduled dispatch entries return
at 1DEC. The mode-cycle code also explicitly skips both IDs. ID 9 has residual
key-related branches in shared helpers, but that does not establish a usable
standalone effect. Neither is offered as a working effect.

18 is not a renderer. The mode-cycle handler translates its ordinal 18 into
selected_effect=32 and switches profile banks (0312=1). Sending native effect=18
with the ordinary bank does not select that profile. It is removed until profile
selection is implemented properly.

The UI now translates dropdown positions to native IDs explicitly, so removing
these entries cannot shift the commands for subsequent effects. Static rainbow
remains a UI alias (19) for native effect 1, palette 7. Unknown readback IDs display an explicit unsupported-mode item instead of
falsely labeling another effect; selecting this fallback cannot send a command.
