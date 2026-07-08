"""Full coverage matrix for the certified multi-day dive plan resolution.

Covers every valid dive-count package (2/3/4/5/7/9) crossed with every way the
customer can give their location:
  - stated upfront in Cartagena ("... desde cartagena")
  - stated upfront on the islands ("... en la isla rosario")
  - not stated at all (bot asks location first, then resolves once answered) —
    for both a Cartagena and an island answer.

Also covers every day-count package (1/2/3/4 dias), since a customer may name
the trip length instead of the dive count:
  - 3 dias / 4 dias map to exactly one plan (7 / 9 dives) -> resolved directly.
  - 1 dia / 2 dias are each shared by two plans (1 day = 2 or 3 dives; 2 days =
    4 or 5 dives) -> a short 2-option follow-up is asked instead of guessing.

And the two "not a clean auto-pick" edges:
  - 4 dives while on the islands is genuinely ambiguous (all-daytime vs
    3-daytime + 1 night-dive variant) — reachable both directly ("4 inmersiones")
    and via the cascading "2 dias" -> "4 inmersiones" -> island sub-menu path.
  - dive/day counts we don't sell as packages (1, 6, 8, 10 dives) must NOT be
    guessed — the flow safely falls back to asking instead of picking a wrong
    plan.

This locks in src/flows/decision_tree.py's _resolve_or_ask_cert_plan /
_cert_dives_to_multiday_choice / _mixed_cert_multi_day_service_map behavior end
to end (via supervisor.route_message), not just the pure detection regexes.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.flows.decision_tree import ConversationState, Step
from src.agents.supervisor import route_message
from src.agents import orchestrator
from src.state_store import serialize_state, deserialize_state

VALID_DIVE_COUNTS = [2, 3, 4, 5, 7, 9]

# Exact service_id the flow must land on for each valid dive count, off-island.
CARTAGENA_SERVICE = {
    2: "2_dives_1_day",
    3: "3_dives_1_day",
    4: "4_dives_2_days",
    5: "5_dives_2_days",
    7: "7_dives_3_days",
    9: "9_dives_4_days",
}

# Same, but on the islands — every count EXCEPT 4 maps to exactly one plan.
ISLAND_SERVICE_UNAMBIGUOUS = {
    2: "2_dives_1_day_already_on_island",
    3: "3_dives_1_day_already_on_island",
    5: "5_dives_2_days_already_on_island",
    7: "7_dives_3_days_already_on_island",
    9: "9_dives_4_days_already_on_island",
}

UNAMBIGUOUS_DIVE_COUNTS = [d for d in VALID_DIVE_COUNTS if d != 4]


def _dive_message(dives: int, location_suffix: str = "") -> str:
    return f"quiero bucear, soy certificado, {dives} inmersiones{location_suffix}"


def _day_message(days: int, location_suffix: str = "") -> str:
    return f"quiero bucear, soy certificado, un paquete de {days} dias{location_suffix}"


async def _finish_island_hotel_step_if_asked(state: ConversationState) -> None:
    """After the island is picked, the bot may ask which hotel to coordinate
    pickup. Answer with the first option so the flow keeps moving."""
    if state.step == Step.ISLAND_HOTEL_MENU:
        await route_message(state, "1")


def _group_dive_message(people: int, dives: int, location_suffix: str = "") -> str:
    return f"somos {people}, todos certificados, {dives} inmersiones{location_suffix}"


def _group_day_message(people: int, days: int, location_suffix: str = "") -> str:
    return f"somos {people}, todos certificados, un paquete de {days} dias{location_suffix}"


async def _complete_booking_to_cart(state: ConversationState) -> None:
    """Drive the flow from wherever mixed_pending_qty_plan was just resolved all
    the way into the cart: answer the quantity if it's still being asked
    (skipped automatically when the group size was already known), say "no" to
    the last-dive question (skip the refresher branch), then confirm add-to-cart.
    """
    if state.step == Step.MIXED_ADD_QTY:
        await route_message(state, "1")
    assert state.step == Step.MIXED_CERT_LAST_DIVE, state.step
    await route_message(state, "2")  # recent dive -> no refresher needed
    assert state.step == Step.MIXED_ADD_PREVIEW, state.step
    await route_message(state, "1")  # confirm add to cart


# ---------------------------------------------------------------------------
# 1) Location stated upfront, in Cartagena — every valid dive count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("dives", VALID_DIVE_COUNTS)
async def test_cartagena_upfront_resolves_exact_plan(dives):
    state = ConversationState(conversation_id=f"ctg-upfront-{dives}")
    resp = await route_message(state, _dive_message(dives, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_QTY, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan == CARTAGENA_SERVICE[dives]
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 2) Location stated upfront, on the islands — every valid dive count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("dives", UNAMBIGUOUS_DIVE_COUNTS)
async def test_island_upfront_resolves_exact_plan(dives):
    state = ConversationState(conversation_id=f"isl-upfront-{dives}")
    resp = await route_message(state, _dive_message(dives, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.step == Step.MIXED_ADD_QTY, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan == ISLAND_SERVICE_UNAMBIGUOUS[dives]


@pytest.mark.asyncio
async def test_island_upfront_4dives_shows_narrow_menu():
    state = ConversationState(conversation_id="isl-upfront-4-narrow")
    resp = await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "4dive_island"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
async def test_island_upfront_4dives_narrow_daytime_variant():
    state = ConversationState(conversation_id="isl-upfront-4-daytime")
    await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await route_message(state, "1")  # all-daytime
    assert state.mixed_pending_qty_plan == "4_dives_2_days_already_on_island"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_island_upfront_4dives_narrow_night_variant():
    state = ConversationState(conversation_id="isl-upfront-4-night")
    await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await route_message(state, "2")  # 3 daytime + 1 night dive
    assert state.mixed_pending_qty_plan == "4_dives_2_days_mixed_already_on_island"
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 3) Location not stated at all -> bot asks -> answered as Cartagena
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("dives", VALID_DIVE_COUNTS)
async def test_deferred_location_then_cartagena_resolves_exact_plan(dives):
    state = ConversationState(conversation_id=f"deferred-ctg-{dives}")
    resp = await route_message(state, _dive_message(dives))
    assert state.step == Step.MIXED_LOCATION, (dives, resp)
    resp = await route_message(state, "cartagena")
    assert state.step == Step.MIXED_ADD_QTY, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan == CARTAGENA_SERVICE[dives]


# ---------------------------------------------------------------------------
# 4) Location not stated at all -> bot asks -> answered as islands
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("dives", UNAMBIGUOUS_DIVE_COUNTS)
async def test_deferred_location_then_island_resolves_exact_plan(dives):
    state = ConversationState(conversation_id=f"deferred-isl-{dives}")
    resp = await route_message(state, _dive_message(dives))
    assert state.step == Step.MIXED_LOCATION, (dives, resp)
    await route_message(state, "isla")
    await route_message(state, "Isla Rosario")
    resp = await route_message(state, "1")  # first hotel option
    assert state.step == Step.MIXED_ADD_QTY, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan == ISLAND_SERVICE_UNAMBIGUOUS[dives]


@pytest.mark.asyncio
async def test_deferred_location_then_island_4dives_shows_narrow_menu():
    state = ConversationState(conversation_id="deferred-isl-4-narrow")
    await route_message(state, _dive_message(4))
    await route_message(state, "isla")
    await route_message(state, "Isla Rosario")
    resp = await route_message(state, "1")  # first hotel option
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "4dive_island"

    await route_message(state, "1")  # all-daytime
    assert state.mixed_pending_qty_plan == "4_dives_2_days_already_on_island"


# ---------------------------------------------------------------------------
# 5) Dive counts we don't sell as packages must NOT be guessed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("dives", [1, 6, 8, 10])
async def test_unsupported_dive_count_falls_back_to_question_cartagena(dives):
    state = ConversationState(conversation_id=f"unsupported-ctg-{dives}")
    resp = await route_message(state, _dive_message(dives, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_CERT_PLAN, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
@pytest.mark.parametrize("dives", [1, 6, 8, 10])
async def test_unsupported_dive_count_falls_back_to_location_question(dives):
    """Same, but with location unknown too — must ask location, never crash
    or silently pick a plan we don't offer."""
    state = ConversationState(conversation_id=f"unsupported-deferred-{dives}")
    resp = await route_message(state, _dive_message(dives))
    assert state.step == Step.MIXED_LOCATION, (dives, resp)
    resp = await route_message(state, "cartagena")
    assert state.step == Step.MIXED_ADD_CERT_PLAN, (dives, state.step, resp)
    assert state.mixed_pending_qty_plan is None


# ---------------------------------------------------------------------------
# 6) Day-count phrasing ("un paquete de N dias") instead of dive-count
# ---------------------------------------------------------------------------
# 3 dias -> 7 dives (only plan that long) and 4 dias -> 9 dives (ditto) resolve
# directly, same as an explicit dive count. 1 dia and 2 dias are each shared by
# two plans, so a short 2-option follow-up is asked instead of guessing.

@pytest.mark.asyncio
@pytest.mark.parametrize("days,dives", [(3, 7), (4, 9)])
async def test_unambiguous_day_count_resolves_exact_plan_cartagena(days, dives):
    state = ConversationState(conversation_id=f"days-ctg-{days}")
    resp = await route_message(state, _day_message(days, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_QTY, (days, state.step, resp)
    assert state.mixed_pending_qty_plan == CARTAGENA_SERVICE[dives]


@pytest.mark.asyncio
@pytest.mark.parametrize("days,dives", [(3, 7), (4, 9)])
async def test_unambiguous_day_count_resolves_exact_plan_island(days, dives):
    state = ConversationState(conversation_id=f"days-isl-{days}")
    resp = await route_message(state, _day_message(days, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.step == Step.MIXED_ADD_QTY, (days, state.step, resp)
    assert state.mixed_pending_qty_plan == ISLAND_SERVICE_UNAMBIGUOUS[dives]


@pytest.mark.asyncio
@pytest.mark.parametrize("days,dives", [(3, 7), (4, 9)])
async def test_unambiguous_day_count_resolves_after_deferred_location(days, dives):
    state = ConversationState(conversation_id=f"days-deferred-{days}")
    resp = await route_message(state, _day_message(days))
    assert state.step == Step.MIXED_LOCATION, (days, resp)
    resp = await route_message(state, "cartagena")
    assert state.step == Step.MIXED_ADD_QTY, (days, state.step, resp)
    assert state.mixed_pending_qty_plan == CARTAGENA_SERVICE[dives]


# ---------------------------------------------------------------------------
# 7) "1 dia" — ambiguous between the 2-dive and 3-dive plans
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1day_shows_narrow_menu_cartagena():
    state = ConversationState(conversation_id="1day-ctg")
    resp = await route_message(state, _day_message(1, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "1day"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
async def test_1day_narrow_pick_2dives_cartagena():
    state = ConversationState(conversation_id="1day-ctg-2dives")
    await route_message(state, _day_message(1, ", desde cartagena"))
    await route_message(state, "1")  # 2 dives
    assert state.mixed_pending_qty_plan == "2_dives_1_day"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_1day_narrow_pick_3dives_cartagena():
    state = ConversationState(conversation_id="1day-ctg-3dives")
    await route_message(state, _day_message(1, ", desde cartagena"))
    await route_message(state, "2")  # 3 dives
    assert state.mixed_pending_qty_plan == "3_dives_1_day"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_1day_narrow_pick_2dives_island():
    state = ConversationState(conversation_id="1day-isl-2dives")
    await route_message(state, _day_message(1, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await route_message(state, "1")  # 2 dives
    assert state.mixed_pending_qty_plan == "2_dives_1_day_already_on_island"


@pytest.mark.asyncio
async def test_1day_deferred_location_then_cartagena():
    state = ConversationState(conversation_id="1day-deferred")
    resp = await route_message(state, _day_message(1))
    assert state.step == Step.MIXED_LOCATION, resp
    resp = await route_message(state, "cartagena")
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "1day"
    await route_message(state, "2")  # 3 dives
    assert state.mixed_pending_qty_plan == "3_dives_1_day"


# ---------------------------------------------------------------------------
# 8) "2 dias" — ambiguous between the 4-dive and 5-dive plans (and picking the
#    4-dive branch on the islands cascades into the daytime/night sub-menu)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_2day_shows_narrow_menu_cartagena():
    state = ConversationState(conversation_id="2day-ctg")
    resp = await route_message(state, _day_message(2, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "2day"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
async def test_2day_narrow_pick_4dives_cartagena():
    state = ConversationState(conversation_id="2day-ctg-4dives")
    await route_message(state, _day_message(2, ", desde cartagena"))
    await route_message(state, "1")  # 4 dives
    assert state.mixed_pending_qty_plan == "4_dives_2_days"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_2day_narrow_pick_5dives_cartagena():
    state = ConversationState(conversation_id="2day-ctg-5dives")
    await route_message(state, _day_message(2, ", desde cartagena"))
    await route_message(state, "2")  # 5 dives
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_2day_narrow_pick_5dives_island_resolves_directly():
    """5 dives is unambiguous even on the islands, so picking it from the
    2-day sub-menu resolves immediately without a second question."""
    state = ConversationState(conversation_id="2day-isl-5dives")
    await route_message(state, _day_message(2, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == "2day"
    await route_message(state, "2")  # 5 dives
    assert state.mixed_pending_qty_plan == "5_dives_2_days_already_on_island"
    assert state.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_2day_narrow_pick_4dives_island_cascades_to_4dive_variant_menu():
    """4 dives IS ambiguous on the islands — picking it from the 2-day
    sub-menu must cascade into the daytime/night-dive sub-menu instead of
    silently picking one variant."""
    state = ConversationState(conversation_id="2day-isl-4dives-cascade")
    await route_message(state, _day_message(2, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == "2day"

    resp = await route_message(state, "1")  # 4 dives
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "4dive_island"
    assert state.mixed_pending_qty_plan is None

    await route_message(state, "2")  # 3 daytime + 1 night dive
    assert state.mixed_pending_qty_plan == "4_dives_2_days_mixed_already_on_island"
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 9) "Back" from every narrow sub-menu must clear the pending narrow state and
#    return to the initial cert-plan question — never leave a stale kind
#    lingering that would misroute the next free-text message.
# ---------------------------------------------------------------------------

_NARROW_MENU_STARTS = [
    (_day_message(1, ", desde cartagena"), "1day"),
    (_day_message(2, ", desde cartagena"), "2day"),
    (_dive_message(4, ", en la isla rosario"), "4dive_island"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("start_message,narrow_kind", _NARROW_MENU_STARTS)
async def test_back_from_narrow_menu_clears_state(start_message, narrow_kind):
    state = ConversationState(conversation_id=f"back-{narrow_kind}")
    await route_message(state, start_message)
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == narrow_kind

    resp = await route_message(state, "back")
    assert state.step == Step.MIXED_ADD_CERT_PLAN, (narrow_kind, resp)
    assert state.mixed_pending_cert_narrow_kind is None
    assert state.mixed_pending_qty_plan is None


# ---------------------------------------------------------------------------
# 10) Garbage/out-of-range input at a narrow sub-menu must re-ask, not crash
#     or silently resolve a plan.
#
# A raw out-of-range digit ("9") is routed straight to the decision tree by
# supervisor.route_message's own isdigit() check, bypassing the LLM intent
# classifier entirely — that's what the first test below exercises, and it's
# real production behavior for numeric input, not a workaround.
#
# Genuine free text ("no se, cualquiera") does NOT take that shortcut: these
# narrow steps aren't in supervisor.py's "critical steps" allowlist that forces
# unclassified text back to the decision tree, so free text goes through
# classify_menu_intent (the LLM classifier) same as anywhere else in the cart
# flow. The second/third tests mock that classifier — same pattern already
# used in test_conversations.py — to cover both of its real outcomes:
#   - classifier can't map it either -> returns "RAG" -> the bot answers via
#     RAG instead of the tree's "not_understood", but state/plan stay intact.
#   - classifier DOES map it to a button value -> the narrow menu resolves
#     via that value, exactly like a literal digit would.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("start_message,narrow_kind", _NARROW_MENU_STARTS)
async def test_invalid_digit_at_narrow_menu_reasks(start_message, narrow_kind):
    state = ConversationState(conversation_id=f"invalid-digit-{narrow_kind}")
    await route_message(state, start_message)
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == narrow_kind

    resp = await route_message(state, "9")
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, (narrow_kind, resp)
    assert state.mixed_pending_cert_narrow_kind == narrow_kind, "must stay in the same sub-menu"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
@pytest.mark.parametrize("start_message,narrow_kind", _NARROW_MENU_STARTS)
async def test_unclassifiable_free_text_at_narrow_menu_falls_back_to_rag(start_message, narrow_kind):
    state = ConversationState(conversation_id=f"invalid-freetext-{narrow_kind}")
    await route_message(state, start_message)
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == narrow_kind

    with patch("src.agents.supervisor.classify_menu_intent", new_callable=AsyncMock, return_value="RAG"), \
         patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        resp = await route_message(state, "no se, cualquiera esta bien")

    assert resp == "CANNED_RAG_ANSWER", (narrow_kind, resp)
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, "RAG answers mid-flow without abandoning the sub-menu"
    assert state.mixed_pending_cert_narrow_kind == narrow_kind, "the pending choice must not be lost"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "start_message,narrow_kind,classifier_value,expected_plan",
    [
        (_day_message(1, ", desde cartagena"), "1day", "2", "3_dives_1_day"),
        (_day_message(2, ", desde cartagena"), "2day", "2", "5_dives_2_days"),
        (_dive_message(4, ", en la isla rosario"), "4dive_island", "1", "4_dives_2_days_already_on_island"),
    ],
)
async def test_llm_classifier_resolves_free_text_at_narrow_menu(
    start_message, narrow_kind, classifier_value, expected_plan
):
    """When the LLM classifier DOES map free text to one of the sub-menu's own
    button values, the narrow menu must resolve exactly as if that value had
    been typed directly — this is the real path a natural-language answer
    ("la de cinco inmersiones porfa") takes in production."""
    state = ConversationState(conversation_id=f"classifier-{narrow_kind}")
    await route_message(state, start_message)
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == narrow_kind

    with patch(
        "src.agents.supervisor.classify_menu_intent", new_callable=AsyncMock, return_value=classifier_value
    ):
        await route_message(state, "la que me recomiendes, prefiero esa opción")

    assert state.mixed_pending_qty_plan == expected_plan
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 11) Word-form numbers ("dos inmersiones", "un dia de buceo") must resolve
#     exactly like their digit equivalents — the regex supports both, but only
#     digits were exercised above.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_word_form_dive_count_resolves_like_digit():
    state = ConversationState(conversation_id="word-dive-count")
    resp = await route_message(state, "quiero bucear, soy certificado, dos inmersiones, desde cartagena")
    assert state.step == Step.MIXED_ADD_QTY, resp
    assert state.mixed_pending_qty_plan == "2_dives_1_day"


@pytest.mark.asyncio
async def test_word_form_day_count_resolves_like_digit():
    state = ConversationState(conversation_id="word-day-count")
    resp = await route_message(
        state, "quiero bucear, soy certificado, un paquete de tres dias, desde cartagena"
    )
    assert state.step == Step.MIXED_ADD_QTY, resp
    assert state.mixed_pending_qty_plan == "7_dives_3_days"


@pytest.mark.asyncio
async def test_word_form_ambiguous_day_count_shows_narrow_menu():
    state = ConversationState(conversation_id="word-day-narrow")
    resp = await route_message(
        state, "quiero bucear, soy certificado, un dia de buceo, desde cartagena"
    )
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "1day"


# ---------------------------------------------------------------------------
# 12) Day counts we don't sell as packages (0, 5, 6+ days) must NOT be guessed.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("days", [0, 5, 6])
async def test_unsupported_day_count_falls_back_to_question(days):
    state = ConversationState(conversation_id=f"unsupported-days-{days}")
    resp = await route_message(state, _day_message(days, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_CERT_PLAN, (days, state.step, resp)
    assert state.mixed_pending_qty_plan is None
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 13) Quick-reply content for every narrow sub-menu — locks in the exact
#     titles/values shown, so a copy change is caught even if the state
#     machine keeps routing correctly.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_1day_narrow_menu_quick_replies_content():
    state = ConversationState(conversation_id="qr-1day")
    await route_message(state, _day_message(1, ", desde cartagena"))
    assert [(r["title"], r["value"]) for r in state.quick_replies] == [
        ("🤿 2 inmersiones", "1"),
        ("🌙 3 inmersiones (con nocturna)", "2"),
        ("🔙 Volver", "back"),
    ]


@pytest.mark.asyncio
async def test_2day_narrow_menu_quick_replies_content():
    state = ConversationState(conversation_id="qr-2day")
    await route_message(state, _day_message(2, ", desde cartagena"))
    assert [(r["title"], r["value"]) for r in state.quick_replies] == [
        ("🤿 4 inmersiones", "1"),
        ("🤿 5 inmersiones", "2"),
        ("🔙 Volver", "back"),
    ]


@pytest.mark.asyncio
async def test_4dive_island_narrow_menu_quick_replies_content():
    state = ConversationState(conversation_id="qr-4dive-island")
    await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert [(r["title"], r["value"]) for r in state.quick_replies] == [
        ("🌞 4 diurnas", "1"),
        ("🌙 3 diurnas + 1 nocturna", "2"),
        ("🔙 Volver", "back"),
    ]


# ---------------------------------------------------------------------------
# 14) English phrasing — every test above uses Spanish; confirm the same
#     dive/day-count parsing and narrow-menu behavior works in English too.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_english_dive_count_resolves_exact_plan():
    state = ConversationState(conversation_id="en-dive-count")
    resp = await route_message(
        state, "I am a certified diver, I want 5 dives, from cartagena"
    )
    assert state.step == Step.MIXED_ADD_QTY, resp
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.language == "en"


@pytest.mark.asyncio
async def test_english_day_count_resolves_exact_plan():
    state = ConversationState(conversation_id="en-day-count")
    resp = await route_message(
        state, "I am a certified diver, I want a 3-day dive package, from cartagena"
    )
    assert state.step == Step.MIXED_ADD_QTY, resp
    assert state.mixed_pending_qty_plan == "7_dives_3_days"
    assert state.language == "en"


@pytest.mark.asyncio
async def test_english_ambiguous_day_count_shows_narrow_menu_in_english():
    state = ConversationState(conversation_id="en-day-narrow")
    resp = await route_message(
        state, "I am a certified diver, I want a 1-day dive package, from cartagena"
    )
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "1day"
    assert state.language == "en"
    assert [(r["title"], r["value"]) for r in state.quick_replies] == [
        ("🤿 2 dives", "1"),
        ("🌙 3 dives (with a night dive)", "2"),
        ("🔙 Back", "back"),
    ]


# ---------------------------------------------------------------------------
# 15) Dive-count and day-count phrased in the same message — the explicit
#     dive count must win (it's unambiguous; the day count is redundant here).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dive_count_wins_over_day_count_in_same_message():
    state = ConversationState(conversation_id="conflict-dive-wins")
    resp = await route_message(
        state,
        "quiero bucear, soy certificado, 2 inmersiones en un paquete de 3 dias, desde cartagena",
    )
    assert state.step == Step.MIXED_ADD_QTY, resp
    assert state.mixed_pending_qty_plan == "2_dives_1_day"


# ---------------------------------------------------------------------------
# 16) End-to-end: the resolved plan must survive all the way into the actual
#     cart line (qty -> last-dive question -> preview -> confirm add), not
#     just sit correctly in mixed_pending_qty_plan. A real risk here is some
#     later step silently overwriting the plan before it's booked.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cartagena_dive_count_reaches_cart():
    state = ConversationState(conversation_id="e2e-ctg-dive")
    await route_message(state, _dive_message(5, ", desde cartagena"))
    await _complete_booking_to_cart(state)
    assert state.mixed_cart == [
        {"type": "cert", "qty": 1, "plan": "5_dives_2_days", "label": state.mixed_cart[0]["label"]}
    ]


@pytest.mark.asyncio
async def test_island_dive_count_reaches_cart():
    state = ConversationState(conversation_id="e2e-isl-dive")
    await route_message(state, _dive_message(7, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["qty"] == 1
    assert state.mixed_cart[0]["plan"] == "7_dives_3_days_already_on_island"


@pytest.mark.asyncio
async def test_island_4dive_narrow_daytime_reaches_cart():
    state = ConversationState(conversation_id="e2e-isl-4dive-daytime")
    await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await route_message(state, "1")  # all-daytime variant
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["plan"] == "4_dives_2_days_already_on_island"


@pytest.mark.asyncio
async def test_island_4dive_narrow_night_reaches_cart():
    state = ConversationState(conversation_id="e2e-isl-4dive-night")
    await route_message(state, _dive_message(4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    await route_message(state, "2")  # 3 daytime + 1 night dive
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["plan"] == "4_dives_2_days_mixed_already_on_island"


@pytest.mark.asyncio
async def test_unambiguous_day_count_reaches_cart():
    state = ConversationState(conversation_id="e2e-day-unambiguous")
    await route_message(state, _day_message(3, ", desde cartagena"))
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["plan"] == "7_dives_3_days"


@pytest.mark.asyncio
async def test_1day_narrow_menu_pick_reaches_cart():
    state = ConversationState(conversation_id="e2e-1day-narrow")
    await route_message(state, _day_message(1, ", desde cartagena"))
    await route_message(state, "1")  # 2 dives
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["plan"] == "2_dives_1_day"


@pytest.mark.asyncio
async def test_2day_narrow_menu_pick_reaches_cart():
    state = ConversationState(conversation_id="e2e-2day-narrow")
    await route_message(state, _day_message(2, ", desde cartagena"))
    await route_message(state, "2")  # 5 dives
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["plan"] == "5_dives_2_days"


# ---------------------------------------------------------------------------
# 17) Group size already known (e.g. "somos 3, todos certificados, ...") must
#     skip the quantity question entirely, landing straight on the last-dive
#     question with the correct headcount — while still resolving the exact
#     plan from the dive/day count, including through the narrow sub-menus.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_group_qty_known_skips_qty_question_cartagena():
    state = ConversationState(conversation_id="group-ctg-dive")
    resp = await route_message(state, _group_dive_message(3, 5, ", desde cartagena"))
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_cert_total_qty == 3
    assert state.mixed_pending_qty_plan == "5_dives_2_days"


@pytest.mark.asyncio
async def test_group_qty_known_with_unambiguous_day_count():
    state = ConversationState(conversation_id="group-day-unambiguous")
    resp = await route_message(state, _group_day_message(2, 3, ", desde cartagena"))
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_cert_total_qty == 2
    assert state.mixed_pending_qty_plan == "7_dives_3_days"


@pytest.mark.asyncio
async def test_group_qty_known_with_1day_narrow_menu():
    """Group size is known, but the plan itself is still ambiguous (1 day):
    the narrow sub-menu must show BEFORE the qty is used, and picking from it
    must still skip the qty question afterwards (it was already known)."""
    state = ConversationState(conversation_id="group-1day-narrow")
    resp = await route_message(state, _group_day_message(2, 1, ", desde cartagena"))
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "1day"
    assert state.mixed_pending_cert_total_qty == 2

    resp = await route_message(state, "2")  # 3 dives
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "3_dives_1_day"
    assert state.mixed_pending_qty_value == 2


@pytest.mark.asyncio
async def test_group_qty_known_with_island_4dive_cascade():
    """Group size known + ambiguous 4-dive-on-island count: must cascade
    through the daytime/night sub-menu and still carry the known qty through
    to the last-dive question without re-asking it."""
    state = ConversationState(conversation_id="group-island-4dive-cascade")
    await route_message(state, _group_dive_message(2, 4, ", en la isla rosario"))
    await _finish_island_hotel_step_if_asked(state)
    assert state.mixed_pending_cert_narrow_kind == "4dive_island"
    assert state.mixed_pending_cert_total_qty == 2

    resp = await route_message(state, "2")  # 3 daytime + 1 night dive
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "4_dives_2_days_mixed_already_on_island"
    assert state.mixed_pending_qty_value == 2


@pytest.mark.asyncio
async def test_group_qty_known_reaches_cart_with_correct_headcount():
    state = ConversationState(conversation_id="group-e2e-cart")
    await route_message(state, _group_dive_message(3, 5, ", desde cartagena"))
    await _complete_booking_to_cart(state)
    assert len(state.mixed_cart) == 1
    assert state.mixed_cart[0]["type"] == "cert"
    assert state.mixed_cart[0]["qty"] == 3
    assert state.mixed_cart[0]["plan"] == "5_dives_2_days"


# ---------------------------------------------------------------------------
# 18) The overnight-stay lodging note must appear even when the plan was
#     resolved via a DAY count instead of a dive count — the note text is
#     built purely from the resolved dive number, but this was only ever
#     asserted for the dive-count entry path (test_intent_robustness.py's
#     "noche" check), never for "paquete de 3 dias" etc.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("days,night_phrase", [(3, "2 noches"), (4, "3 noches")])
async def test_unambiguous_day_count_shows_lodging_note(days, night_phrase):
    state = ConversationState(conversation_id=f"lodging-day-{days}")
    resp = await route_message(state, _day_message(days, ", desde cartagena"))
    assert "noche" in resp.lower(), (days, resp)
    assert night_phrase in resp, (days, resp)


@pytest.mark.asyncio
async def test_1day_narrow_pick_3dives_shows_lodging_note():
    """The 1-day sub-menu's "3 dives" branch includes a night dive, so it
    carries the same overnight-stay note as picking it via dive-count would."""
    state = ConversationState(conversation_id="lodging-1day-3dives")
    await route_message(state, _day_message(1, ", desde cartagena"))
    resp = await route_message(state, "2")  # 3 dives
    assert "noche" in resp.lower(), resp


@pytest.mark.asyncio
async def test_2day_narrow_pick_shows_lodging_note():
    state = ConversationState(conversation_id="lodging-2day")
    await route_message(state, _day_message(2, ", desde cartagena"))
    resp = await route_message(state, "1")  # 4 dives
    assert "noche" in resp.lower(), resp


# ---------------------------------------------------------------------------
# 19) Refresher split (some of the group need it, some don't) combined with a
#     plan resolved from natural-language day/dive-count text, not literal
#     button clicks. Mirrors test_conversations.py's
#     test_refresher_split_adds_full_cert_group_with_correct_plan, which only
#     exercises the button-driven path.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresher_split_with_day_count_and_natural_language_group():
    """3 people, group + plan given as free text ("un paquete de 3 dias"),
    2 of them need the refresher. Final cart must have one cert line for all
    3 (correct plan) and one refresh line for exactly 2."""
    state = ConversationState(conversation_id="refresh-split-day-count")
    resp = await route_message(
        state, _group_day_message(3, 3, ", desde cartagena")
    )
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "7_dives_3_days"
    assert state.mixed_pending_cert_total_qty == 3

    await route_message(state, "1")  # last dive > 2 years -> yes
    assert state.step == Step.MIXED_CERT_REFRESH_INTEREST

    await route_message(state, "1")  # wants refresher -> yes
    assert state.step == Step.MIXED_CERT_REFRESH_QTY

    resp = await route_message(state, "2")  # 2 of 3 want the refresher
    assert state.step == Step.MIXED_CERT_SPLIT_REVIEW, resp
    assert "7" in resp, f"Plan missing from split review: {resp!r}"

    resp = await route_message(state, "1")  # continue
    assert state.step == Step.MIXED_ADD_PREVIEW, resp
    assert state.mixed_pending_qty_value == 3
    assert state.mixed_pending_qty_plan == "7_dives_3_days"

    await route_message(state, "1")  # confirm add to cart
    assert state.step == Step.MIXED_CART_REVIEW

    cert_items = [it for it in state.mixed_cart if it.get("type") == "cert"]
    refresh_items = [it for it in state.mixed_cart if it.get("type") == "refresh"]

    assert len(cert_items) == 1, f"Expected 1 cert item, got {cert_items}"
    assert cert_items[0]["plan"] == "7_dives_3_days"
    assert cert_items[0]["qty"] == 3

    assert len(refresh_items) == 1, f"Expected 1 refresh item, got {refresh_items}"
    assert refresh_items[0]["qty"] == 2
    assert refresh_items[0]["plan"] == "7_dives_3_days"


@pytest.mark.asyncio
async def test_refresher_split_with_dive_count_natural_language_group():
    """Same scenario, but the group states an explicit dive count instead of
    a day count ("5 inmersiones") — the other natural-language entry point."""
    state = ConversationState(conversation_id="refresh-split-dive-count")
    resp = await route_message(
        state, _group_dive_message(4, 5, ", desde cartagena")
    )
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_cert_total_qty == 4

    await route_message(state, "1")  # last dive > 2 years -> yes
    await route_message(state, "1")  # wants refresher -> yes
    resp = await route_message(state, "2")  # 2 of 4 want the refresher
    assert state.step == Step.MIXED_CERT_SPLIT_REVIEW, resp

    await route_message(state, "1")  # continue
    await route_message(state, "1")  # confirm add to cart
    assert state.step == Step.MIXED_CART_REVIEW

    cert_items = [it for it in state.mixed_cart if it.get("type") == "cert"]
    refresh_items = [it for it in state.mixed_cart if it.get("type") == "refresh"]
    assert cert_items == [
        {"type": "cert", "qty": 4, "plan": "5_dives_2_days", "label": cert_items[0]["label"]}
    ]
    assert refresh_items[0]["qty"] == 2
    assert refresh_items[0]["plan"] == "5_dives_2_days"


# ---------------------------------------------------------------------------
# 20) "Empezar de nuevo" (restart) while a narrow sub-menu is pending must wipe
#     the day/dive-count state too, not just the cart.
#
# Regression found while extending this suite: _reset_mixed_state cleared
# mixed_pending_qty_plan / _cart / etc. but NOT the three fields this session
# added (mixed_pending_cert_narrow_kind, detected_cert_dives, detected_cert_days).
# A restart while e.g. the "2day" sub-menu was showing left narrow_kind="2day"
# stuck in state — so if the user later organically reached the multi-day menu
# again for an unrelated request, a plain "1"/"2" would have been silently
# reinterpreted as an answer to a sub-menu question that was never asked this
# time. Fixed in decision_tree.py's _reset_mixed_state.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restart_while_narrow_menu_pending_clears_all_cert_count_state():
    state = ConversationState(conversation_id="restart-narrow")
    await route_message(state, _day_message(2, ", desde cartagena"))
    assert state.mixed_pending_cert_narrow_kind == "2day"

    async def _answer_question(message, **kwargs):
        return orchestrator.OrchestratorDecision(tool=orchestrator.TOOL_ANSWER_QUESTION)

    with patch("src.agents.orchestrator.orchestrate", new=_answer_question), \
         patch(
             "src.agents.supervisor.classify_menu_intent", new_callable=AsyncMock, return_value="restart"
         ):
        await route_message(state, "quiero empezar de cero")

    assert state.step == Step.MIXED_ENTRY
    assert state.mixed_pending_cert_narrow_kind is None
    assert state.detected_cert_dives is None
    assert state.detected_cert_days is None
    assert state.mixed_pending_qty_plan is None


# ---------------------------------------------------------------------------
# 21) Redis persistence round-trip: the three fields this session added must
#     survive serialize_state/deserialize_state (used on every turn to save/
#     load conversation state from Redis) without crashing or losing their
#     value, and the conversation must be resumable afterwards.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_narrow_menu_state_survives_serialization_round_trip():
    state = ConversationState(conversation_id="serialize-narrow")
    await route_message(state, _day_message(1, ", desde cartagena"))
    assert state.mixed_pending_cert_narrow_kind == "1day"

    restored = deserialize_state(serialize_state(state))
    assert restored.mixed_pending_cert_narrow_kind == "1day"
    assert restored.step == Step.MIXED_ADD_CERT_MULTI_DAY

    # The conversation must be resumable exactly where it left off.
    await route_message(restored, "2")  # 3 dives
    assert restored.mixed_pending_qty_plan == "3_dives_1_day"
    assert restored.mixed_pending_cert_narrow_kind is None


@pytest.mark.asyncio
async def test_detected_cert_counts_survive_serialization_round_trip():
    """detected_cert_dives/days are only set transiently (before location is
    known) — confirm they don't get lost if Redis round-trips the state in
    between the dive-count message and the location answer."""
    state = ConversationState(conversation_id="serialize-detected")
    await route_message(state, _day_message(3))
    assert state.step == Step.MIXED_LOCATION
    assert state.detected_cert_days == 3

    restored = deserialize_state(serialize_state(state))
    assert restored.detected_cert_days == 3

    await route_message(restored, "cartagena")
    assert restored.mixed_pending_qty_plan == "7_dives_3_days"


# ---------------------------------------------------------------------------
# 22) Real-world use case: a mixed group where only PART of the people want
#     certified multi-day diving and the rest want a different activity
#     (snorkel), stated in one message with a natural-language dive/day count
#     for the cert subgroup. Confirms our count resolution integrates
#     correctly with group_allocation splitting — cert_total_qty must be the
#     cert SUBGROUP size, not the whole group, and the other activity must
#     already be queued/added on its own.
#
# Note: the exact count must be stated in its own clause, not spliced inside
# the split clause itself ("...certificados 5 inmersiones y 2 hacen snorkel"
# fails to split at all — see the KNOWN GAP comment on _detect_group_info in
# intent_detector.py, a pre-existing fragility unrelated to this session's work).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_group_cert_multiday_dive_count_plus_snorkel():
    state = ConversationState(conversation_id="usecase-mixed-dive")
    resp = await route_message(
        state,
        "somos 5, 3 bucean y 2 hacen snorkel, queremos 5 inmersiones, desde cartagena",
    )
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_cert_total_qty == 3, "must be the cert subgroup, not the whole group of 5"
    assert state.mixed_cart == [
        {"type": "snorkel", "qty": 2, "plan": "snorkeling", "label": "Snorkel"}
    ]


@pytest.mark.asyncio
async def test_mixed_group_cert_multiday_day_count_plus_snorkel():
    state = ConversationState(conversation_id="usecase-mixed-day")
    resp = await route_message(
        state,
        "somos 5, 3 bucean y 2 hacen snorkel, queremos un paquete de 3 dias, desde cartagena",
    )
    assert state.step == Step.MIXED_CERT_LAST_DIVE, resp
    assert state.mixed_pending_qty_plan == "7_dives_3_days"
    assert state.mixed_pending_cert_total_qty == 3
    assert state.mixed_cart == [
        {"type": "snorkel", "qty": 2, "plan": "snorkeling", "label": "Snorkel"}
    ]


@pytest.mark.asyncio
async def test_mixed_group_ambiguous_day_count_still_shows_narrow_menu():
    """The narrow sub-menu logic must still kick in even inside a mixed-group
    booking (not just the simple single-cert-group path)."""
    state = ConversationState(conversation_id="usecase-mixed-narrow")
    resp = await route_message(
        state,
        "somos 5, 3 bucean y 2 hacen snorkel, queremos un paquete de 2 dias, desde cartagena",
    )
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY, resp
    assert state.mixed_pending_cert_narrow_kind == "2day"
    assert state.mixed_pending_cert_total_qty == 3

    await route_message(state, "2")  # 5 dives
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_qty_value == 3


# ---------------------------------------------------------------------------
# 23) Real-world use case: the customer asks an unrelated info question WHILE
#     a narrow sub-menu is showing, instead of answering it. Must answer via
#     RAG (the "plain info question" short-circuit) without losing the
#     pending sub-menu — and the customer must still be able to resume it
#     afterwards (either via the "continue" button's reused value, or by
#     typing the other option directly).
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_info_question_mid_narrow_menu_preserves_state_and_answers_via_rag():
    state = ConversationState(conversation_id="usecase-info-question")
    await route_message(state, _day_message(2, ", desde cartagena"))
    assert state.mixed_pending_cert_narrow_kind == "2day"

    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED_RAG_ANSWER"):
        resp = await route_message(state, "que incluye el paquete de buceo")

    assert resp == "CANNED_RAG_ANSWER"
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
    assert state.mixed_pending_cert_narrow_kind == "2day", "must not lose the pending sub-menu"
    assert state.mixed_pending_qty_plan is None


@pytest.mark.asyncio
async def test_resume_narrow_menu_after_info_question_with_the_other_option():
    """After the info-question detour, quick_replies get swapped for a
    "continue booking" button that reuses the sub-menu's first option value —
    but the customer must still be able to type the OTHER option's raw digit
    and have it resolve correctly (not just the button's own primary value)."""
    state = ConversationState(conversation_id="usecase-info-question-resume")
    await route_message(state, _day_message(2, ", desde cartagena"))
    with patch("src.agents.supervisor.rag_answer", new_callable=AsyncMock, return_value="CANNED"):
        await route_message(state, "que incluye el paquete de buceo")
    assert state.mixed_pending_cert_narrow_kind == "2day"

    await route_message(state, "2")  # 5 dives — the non-primary option
    assert state.mixed_pending_qty_plan == "5_dives_2_days"
    assert state.mixed_pending_cert_narrow_kind is None


# ---------------------------------------------------------------------------
# 24) Real-world use case: the customer asks to switch currency mid-narrow-menu
#     ("los precios en pesos"). Must apply the switch without disturbing the
#     pending sub-menu state.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_currency_switch_mid_narrow_menu_preserves_state():
    state = ConversationState(conversation_id="usecase-currency-switch")
    await route_message(state, _day_message(1, ", desde cartagena"))
    assert state.mixed_pending_cert_narrow_kind == "1day"

    with patch(
        "src.agents.supervisor.classify_menu_intent",
        new_callable=AsyncMock,
        return_value="currency_switch_cop",
    ):
        await route_message(state, "los precios en pesos porfa")

    assert state.mixed_display_currency == "COP"
    assert state.step == Step.MIXED_ADD_CERT_MULTI_DAY
    assert state.mixed_pending_cert_narrow_kind == "1day"

    await route_message(state, "1")  # still resolvable afterwards
    assert state.mixed_pending_qty_plan == "2_dives_1_day"
