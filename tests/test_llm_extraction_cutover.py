"""La línea `[EXTRACT][CUTOVER]` del relleno de huecos del núcleo (`conversational_core._understand`, la que lee
scripts/harvest_cutover_logs.py) lleva el mensaje entero: `supervisor._log_safe_message`.

s4-1 (19-oct) borró el cutover por dominio antiguo (`supervisor._maybe_apply_llm_extraction_cutover`), que no llamaba
nadie desde 308488d (28-jul), y sus tests. Queda este, que con él fijaba que el registro no corta el mensaje.
"""

from src.agents import supervisor


def test_cutover_log_line_does_not_truncate_the_message():
    """Real bug found live (2026-07-21): the [EXTRACT][CUTOVER] log line cut the
    message to 60 chars, so candidates harvested by scripts/harvest_cutover_logs.py
    lost the end of the customer's actual message — the exact opposite of what
    Fase 6 (bucle de datos reales) needs. Full messages must survive in the log."""
    long_message = (
        "hey never been underwater before, kinda nervous, wanna give it a try, "
        "just me, is this a good idea for someone with no experience at all"
    )
    assert len(long_message) > 60
    assert supervisor._log_safe_message(long_message) == long_message
