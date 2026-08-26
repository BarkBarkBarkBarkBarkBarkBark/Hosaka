# hosaka-social-cognition

Provider-agnostic social cognition middleware. Speech is scarce; silence is a successful outcome. The LLM proposes thoughts. A deterministic `SocialGovernor` authorizes speech.

v0 is a library with a mock LLM, fake clock, one-slot chamber, and conversation simulations. It does not implement ASR, TTS, or vendor SDKs.

## Install

```bash
pip install -e packages/social_cognition
pip install -e "packages/social_cognition[dev]"
```

## Public API

```python
from hosaka_social import (
    SocialEngine,
    SocialConfig,
    FakeClock,
    MockLLMProvider,
    MockSpeechSink,
    NullFaceController,
    ConversationSimulator,
    ThoughtCandidate,
)
```

`hosaka_social` does not import Hosaka. Hosts inject `LLMProvider`, `SpeechSink`, `Clock`, and `FaceController`.

## Demo

```bash
python packages/social_cognition/examples/party_simulation.py
python packages/social_cognition/examples/minimal.py
```

## Tests

```bash
cd packages/social_cognition
python -m pytest
```

Later iterations (providers, voice, Cavasik, `yap`) are specified in `cognition/cognition_play.yaml`.
