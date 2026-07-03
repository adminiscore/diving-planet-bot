"""
Booking Agent.

Phase 2: Handles the booking flow by generating deep links
to the Roverd booking system (book.divingplanet.org) with
pre-filled parameters when possible.

Current status: booking-link resolution is already handled inline by
`decision_tree._resolve_service_booking_url` (picks the Cartagena vs.
island link per service) and the checkout handlers, which either send the
link directly (international clients) or escalate to an advisor. This module
is a placeholder for a future, centralized Roverd deep-link generator that
pre-fills date / group size once Roverd's URL parameter structure is known.

Responsibilities (future):
- Generate correct booking URLs based on service + location.
- Pre-fill Roverd query params (date, group size) when the schema is known.
- Track booking conversions for the owner dashboard.

Note: there is no longer a "Colombian discount" flow — Colombian/resident
clients simply pay in COP and international clients in USD (same price,
currency only). See data/knowledge_base/discounts.json (colombian_cop_pricing).
"""

# TODO: Implement centralized Roverd deep-link generation (and optional
# Roverd API integration if available). Until then, booking links are
# resolved inline in the decision tree.
