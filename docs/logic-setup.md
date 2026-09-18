# Logic Pro setup guide

This guide configures a common two-track session: a musician plays an
instrument on Logic Track 1 while a Gymnasium agent plays and controls an
instrument on Logic Track 2.

To let an agent control a Logic plug-in knob by sending MIDI CC messages, see
[the MIDI learning and testing instructions](control-modes.md#let-the-agent-control-a-logic-plug-in-knob-using-midi).
For absolute MIDI knob assignments, use **Format: Unsigned** and **Mode: Scaled**.
For agent audio observations, see [audio input setup and testing](audio-input.md).

## 1. Install LogicProGym

With Git and Python 3.10+ installed on macOS, open Terminal in the parent folder
where you want to keep the project. Clone the repository and install it:

```bash
git clone https://github.com/ziyunliu4444/LogicProGym.git
cd LogicProGym
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Already cloned or downloaded the project? Open its `LogicProGym` folder and skip
the clone command. If `.venv` already exists, activate it instead of recreating it.
Run subsequent commands from this project folder with the virtual environment
active. In a new terminal, return to the folder and activate `.venv` again.

The editable installation only needs to be repeated after recreating the
virtual environment or changing package configuration. Ordinary Python source
changes become available immediately.

## 2. Create a session configuration

Run `logicprogym devices` to list exact MIDI input/output names without sending
messages. Replace all `YOUR_...` placeholders with your own device names.
Device discovery does not configure routing inside Logic.

Do not edit the shared example for each experiment. Copy it first:

```bash
cp configs/examples/logic_human_agent.yaml configs/my_session.yaml
```

Edit `configs/my_session.yaml` and set:

- the musician's physical MIDI keyboard input name;
- the IAC bus routed to the agent instrument;
- the one-based Logic track number for the agent;
- the Mackie controller assigned to that track; and
- the instrument parameter page, slot, and displayed name mappings.

Port names must match macOS MIDI names exactly. YAML quotes are recommended but
are not part of the port name itself.

## 3. Configure Logic Pro

Create or open a Logic project with:

1. A human instrument on Track 1.
2. An agent instrument on Track 2.
3. Track 2 receiving agent notes from `YOUR_AGENT_OUTPUT`, or the IAC port used
   in the session YAML.
4. A Mackie Control device for each configured LogicProGym controller.

For Mackie Control 2, use:

```text
Input:  LogicProGym Control 2 To Logic
Output: LogicProGym Control 2 From Logic
```

The LogicProGym Mackie ports exist only while a LogicProGym program is connected. Stop
other LogicProGym Mackie scripts before starting a doctor, scanner, or environment
so two processes do not compete for the same endpoints.

## 4. Check the configuration

Check YAML, Gymnasium spaces, keyboard ports, IAC ports, and Mackie assignments:

```bash
logicprogym doctor configs/my_session.yaml
```

With Logic open and the control surfaces assigned, verify live Mackie feedback:

```bash
logicprogym doctor configs/my_session.yaml --live
```

The live check verifies configured names at their page/slot addresses. A failure
can mean a changed preset, incorrect routing, or unavailable display feedback;
do not rename parameters merely to suppress an error. Use the
[Mackie troubleshooting guide](mackie-discovery.md#understand-the-display-and-troubleshoot)
to distinguish these cases. A successful check does not prevent later preset changes.

## 5. Scan instrument parameters

Use the [setup tools catalogue](../tools/README.md) to choose between interactive
inspection and scanning. The [discovery guide](mackie-discovery.md) covers starting
without known names, browsing pages, and referencing selected catalog entries
directly in YAML. Inline parameter names remain an alternative. Run the live
doctor again after changing mappings.

## 6. Create a Gymnasium environment

Through LogicProGym's convenience constructor:

```python
import logicprogym

env = logicprogym.make("configs/my_session.yaml")
observation, info = env.reset(seed=0)
```

Or through Gymnasium's registry:

```python
import gymnasium as gym
import logicprogym  # Registers LogicProGym/Logic-v0.

env = gym.make(
    "LogicProGym/Logic-v0",
    config_path="configs/my_session.yaml",
)
observation, info = env.reset(seed=0)
```

Always stop the agent cleanly and call `env.close()` when the application owns
the environment. Live example programs also send sustain-off, note-off,
all-notes-off, and all-sound-off messages during shutdown.
