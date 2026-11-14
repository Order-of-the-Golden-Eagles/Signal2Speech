# Integration

Route keyboard, simulated and live EEG input through one confirmation handler.

**Active work** · [#4](https://github.com/Order-of-the-Golden-Eagles/Signal2Speech/issues/4)

## Rehearse without a headset (#21)

`SimulatedDecoder` drives the handler through the same `arm_capture()` / `select_captured()` path as live EEG, labelled `simulated`. To wire it into `app.py` (#25):

```python
from signal2speech.eeg.simulated import SimulatedDecoder

decoder = SimulatedDecoder(handler, picks=[2, 1])  # or picks=() and decoder.set_next(cls)
decoder.start()                                    # g.Pype Generator stream; call decoder.close() on exit
window.set_input_source(InputSources.SIMULATED)
handler.begin_choice_round(choices)                # auto: each opened round starts a sequence
```

Standalone: `python -m signal2speech.eeg.simulated --ui --picks 2,1`. See [EEG Hardware](../eeg-hardware/README.md#simulated-input-21--works) for the threading details and the stale-decision rule.
