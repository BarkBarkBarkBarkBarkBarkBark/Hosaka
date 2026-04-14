from hosaka.offline.assist import classify_intent


def test_offline_intent_rules() -> None:
    result = classify_intent("help me get this on wifi")
    assert result.intent == "network_help"

    fallback = classify_intent("unknown request")
    assert fallback.intent == "general_help"
