# Inspect an instrument and discover its controls

These setup tools discover parameters exposed through Logic's Mackie interface,
not necessarily every plug-in control. They do not infer MIDI CC assignments,
absolute ranges, or parameter meanings. Names may be abbreviated and preset-specific.

Commands below assume an installed checkout and an activated virtual environment.
Use `inspect` for an interactive console and `scan` to save a parameter catalog.
Run only one Mackie program at a time.

## Start without parameter names

```bash
cp configs/examples/logic_discovery.yaml configs/my_discovery.yaml
```

Set `track` and `controller` to your one-based Logic track and Mackie numbers.
The template uses track 2 and controller 2. No keyboard or IAC note bus is needed.
Configure the matching LogicProGym To/From endpoints using the [setup guide](renaming.md).
Virtual ports exist only while connected. Stop other agents/scanners first.

The tools connect only Mackie endpoints: no notes, audio capture, or configured
episode-reset commands. They do change selection and Instrument pages. Save your
project first; selection, pages, and manually changed knobs are not restored on exit.

## Interactive inspector

```bash
logicprogym logic inspect configs/my_discovery.yaml --track agent
```

Run this command in an interactive terminal (including the IDE's Terminal tab).
The `scan` command is not interactive and does not accept `lcd`. The inspector
briefly attempts Instrument view on startup; if detection fails, it prints a
warning and still opens the prompt so you can inspect incoming display text.

At `mackie>`, type a command and press Enter. For example, type `lcd`, not
`mackie> lcd`; the prefix is the program's prompt.

| Command | Effect |
| --- | --- |
| `lcd` | Print cached LCD text |
| `left` / `right` | Browse one Instrument page |
| `instrument` | Recover Instrument view |
| `track agent` | Switch to a configured YAML alias |
| `vpot 2 1` | **Change** slot 2 by one positive relative tick |
| `vpot 2 -1` | **Change** slot 2 by one negative relative tick |
| `help` / `quit` | Show commands / disconnect |

Slots are 1–8; ticks are -63–-1 or 1–63 (zero is not a turn). Only `vpot` sends knob changes. The inspector
accepts either header/name or name/value Instrument views. `left`/`right` can
request a page display when only values are visible; `vpot` still requires a
recognized track/page. Some controls change presets
or generate sound: inspect before testing. Ctrl-C and EOF also exit.
Output is on demand, so incoming messages do not flood your prompt. LCD text is
cached diagnostic text, not guaranteed fresh or verified parameter values.

## Automatic discovery

Quit the inspector, then run:

```bash
logicprogym logic scan configs/my_discovery.yaml --track agent --all --output configs/my_instrument.yaml
```

Each completed page is printed. `--all` uses Logic's reported total, capped at 256
pages. If Instrument Edit shows values instead of the header/name layout, the
scanner requests the latter with one Name/Value toggle and verifies the returned
track header before collecting names. It does not treat numeric values as names.
Large instruments take longer. For a short scan use:

```bash
logicprogym logic scan configs/my_discovery.yaml --track agent --pages 2 --output configs/my_instrument.yaml
```

Without either flag the scanner reads one page. Scans ordinarily start at page 1.
The catalog is saved only after the complete scan succeeds. Existing catalog
entries for other tracks are preserved; the scanned alias's entry is replaced.
Ctrl-C closes endpoints. Scanning navigates pages but does not turn V-Pots.

If the total is truncated, use an explicit `--pages N`. If the current page is
also truncated, `--start-page N` asserts its identity: **it does not navigate to
page N**. Use it only when you independently know that page. Without a usable
header, the inspector deliberately refuses knob tests, but permits browsing an
Instrument view. This does not relax the automatic scanner's identity checks.

## Using an existing shared-instrument session

If you already followed the [shared-instrument walkthrough](walkthrough-shared-instrument.md),
reuse that configuration rather than creating another controller setup:

```bash
logicprogym logic inspect configs/my_shared_track.yaml --track shared
```

Enter `quit` before running the scanner:

```bash
logicprogym logic scan configs/my_shared_track.yaml \
  --track shared --pages 2 \
  --output configs/my_shared_parameters.yaml
```

Replace `--pages 2` with `--all` for all reported pages. `shared` and `agent`
are configuration aliases, not names that Logic must display. Use the alias
configured for the instrument you want to inspect. MIDI-only/audio-only sessions
cannot inspect Mackie pages; they need a Mackie configuration.

## Understand the display and troubleshoot

Logic can show several different screens on the same controller:

| Display | Meaning |
| --- | --- |
| Track/instrument header with `Page 1/71`, parameter names below | Header/name view used by the scanner |
| `Robotc`, `Cutoff`, etc. above percentages or labels | Instrument name/value view; valid for inspection, but not enough to establish page identity |
| Track names and `0`, `Pan`, or `Inst` below | Mixer/assignment view, not an Instrument parameter page |
| `Select` and an instrument/preset name | Selection overlay, not a parameter page |

The scanner automatically requests the header/name layout with Name/Value when
it recognizes the Instrument value view. You do not need to turn knobs to scan.
It verifies the returned track header before saving names; it will not substitute
percentages for parameter names or guess an unavailable page identity.

- **No `mackie>` prompt:** make sure you ran `inspect`, not `scan`, in an
  interactive terminal. Allow the brief startup attempt to finish. Detection
  failures should leave a warning and an available prompt.
- **Mixer or `Select` screen:** enter `instrument`, then `lcd`. If it persists,
  check the track/controller numbers and the matching To/From port pair. Do not
  rename parameters to match the mixer screen.
- **Values are visible but scanning fails:** this is not proof of incorrect
  parameter names. Read the error for a missing header or page count. The scanner
  makes one Name/Value attempt; it stops if the requested header does not arrive.
- **Stale or wrong-track feedback:** stop other bridge programs and follow the
  [reconnection guide](renaming.md). Do not delete unrelated controller assignments.
- **A knob test is refused:** `vpot` requires a recognized track/page even when
  values are visible. Use `left`/`right` and `lcd` to inspect the resulting page;
  do not assume a cached number belongs to the requested track.

Scans collect names and addresses, not continuous value recordings. For agent
readings and validity masks, see [parameter observations](parameter-observations.md).

## Reference the catalog in YAML

Create `configs/my_catalog_session.yaml` after scanning:

```yaml
adapter:
  type: logic_mackie
  controller_count: 2
  controllers:
    - id: agent
      track: 2
      controller: 2
      catalog:
        file: my_instrument.yaml
        track: agent
        select:
          - {page: 1, slot: 2}
          - {page: 1, slot: 6}
tracks:
  - alias: agent
    observe: [plugin_parameters]
    actions:
      mackie: true
```

Choose addresses from **your** scan; these are examples, not universal knob
addresses. `file` resolves relative to the session YAML. Catalog `track` selects
the saved entry and defaults to the controller's `id`. Session track/controller
numbers determine routing; saved catalog routing metadata does not override them.

`select` is mandatory and ordered. Only selected entries are loaded.
`mackie: true` generates `agent/parameter_vector` with shape `[2]` here and range
`[-1, 1]`, in selection order. It can accompany an action `preset` and `add` list,
but do not also define a manual `parameter_vector`. Omit it to observe without
generated actions. Inline `parameters` remain supported instead of `catalog`;
do not specify both on one controller.

```bash
logicprogym preview configs/my_catalog_session.yaml
logicprogym doctor configs/my_catalog_session.yaml --live
```

Rescan after changing instruments or presets. Discovery does not automatically
enable every control. Existing example policies may require a specific vector
length/order; selecting a new vector does not automatically adapt those policies.
