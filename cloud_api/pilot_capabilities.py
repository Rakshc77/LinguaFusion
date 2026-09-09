"""Managed-policy gateway for the tested provider adapters (readiness gate 6).

Every dispatch must clear TWO independent ledgers before a request leaves this
process:

  1. the per-user managed policy — monthly attempt count and monthly USD budget,
     owned by the owner console and persisted per user; and
  2. the shared lifetime test allowance, which PilotProviders reserves from
     itself inside `_post`, once, immediately before dispatch.

Neither ledger alone is sufficient. The policy stops one user from spending
everyone's money; the lifetime allowance stops every user combined from
exceeding the approved total. Do not collapse them into one check, and do not
let a route call PilotProviders directly and bypass the policy.

Holds are retained, never automatically refunded, whenever a request may have
reached a provider. The single exception is an input or budget rejection raised
BEFORE dispatch, where this process knows for certain that nothing was sent.
"""
import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timezone

from fastapi import HTTPException

from cloud_api.pilot_providers import LAST_USAGE, ProviderFailure, settled_micro

# Flat conservative hold per request, matching what PilotProviders reserves from
# the lifetime allowance. These adapters are not billed per token here, so a
# single ceiling is used rather than a token estimate that would understate a
# failed or oversized call.
PILOT_HOLD_MICRO = 10000

log = logging.getLogger('linguafusion.cloud')

# Recent provider failures, kept in memory so the owner can see them in the app.
# Cloud Logging is still written to, but a log line the owner cannot find from a
# phone is not a diagnosis. Bounded, and it holds NO user content: capability,
# provider, status and time only.
RECENT_FAILURE_LIMIT = 25
_recent_failures = deque(maxlen=RECENT_FAILURE_LIMIT)


def record_failure(capability, reason):
    _recent_failures.append({
        'at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'capability': capability,
        'reason': str(reason)[:200],
    })


def recent_failures():
    """Newest first. Per-instance and lost on restart, which is honest: this is
    for 'what just went wrong', not an audit trail."""
    return list(reversed(_recent_failures))

# Translation models the owner has reviewed and approved. Anything outside this
# map is refused: the caller must never be able to name an arbitrary model, both
# for cost control and because an unreviewed model has unknown behaviour.
# The registry lives with the provider code: the price ceiling sent to
# OpenRouter is provider knowledge, and keeping it beside the model list
# stops the two drifting apart.
from cloud_api.pilot_providers import (DEFAULT_TRANSLATION_MODEL,  # noqa: F401
                                       MODEL_GUIDANCE_IS_MEASURED, TRANSLATION_MODELS)


def translation_charge_id(model):
    """The ledger label for a chosen model, so the owner's spending breakdown
    shows which model actually cost the money."""
    if model not in TRANSLATION_MODELS:
        raise HTTPException(422, 'That translation model is not approved.')
    return 'pilot:openrouter/' + model


# `charge_id` is what lands in the policy ledger and in the owner's spending
# breakdown, so it names the provider AND the exact model actually dispatched.
CAPABILITIES = {
    'translate': {
        'provider': 'openrouter',
        'charge_id': 'pilot:openrouter/mistralai/mistral-nemo',
        'summary': 'Cloud translation via OpenRouter, pinned to one provider.',
    },
    'pronounce': {
        'provider': 'openrouter',
        'charge_id': 'pilot:openrouter/google/gemma-3-27b-it',
        'summary': 'Latin-script pronunciation guide. Approximate, never a translation.',
    },
    'transcribe': {
        'provider': 'groq',
        'charge_id': 'pilot:groq/whisper-large-v3-turbo',
        'summary': 'Cloud speech transcription of one short mono WAV.',
    },
    'ocr': {
        'provider': 'google_vision',
        'charge_id': 'pilot:google_vision/document-text',
        'summary': 'Cloud OCR of one PNG or JPEG.',
    },
}


class PilotGateway:
    def __init__(self, providers, policy, enabled_features=frozenset(), paid_ai_enabled=False):
        self.providers = providers
        self.policy = policy
        unknown = set(enabled_features) - set(CAPABILITIES)
        if unknown:
            raise RuntimeError('Unknown pilot capability configured: ' + ', '.join(sorted(unknown)))
        self.enabled_features = frozenset(enabled_features)
        # LF_CLOUD_AI_ENABLED is the single master switch for paid AI. It has to
        # gate these routes too: an owner who sets it to 0 to stop all paid
        # calls must actually stop them, not just the older translation route.
        self.paid_ai_enabled = bool(paid_ai_enabled)

    def available(self, capability):
        return bool(self.paid_ai_enabled and self.providers and self.policy
                    and capability in self.enabled_features)

    async def run(self, capability, uid, call, charge_id=None):
        """Reserve against the managed policy, then dispatch exactly once.

        `call` receives no arguments and performs one provider request. It is
        never retried here: a retry would risk paying twice for a request the
        provider may already have completed.
        """
        if capability not in CAPABILITIES:
            raise HTTPException(422, 'Unsupported cloud capability.')
        if not self.available(capability):
            raise HTTPException(503, 'This cloud feature is not enabled by the owner.')
        charge_id = charge_id or CAPABILITIES[capability]['charge_id']
        # Reserve the per-user hold BEFORE the lifetime allowance is touched.
        # A wasted per-user hold resets next month and the owner can raise the
        # budget; a wasted lifetime hold is permanent, so it must be risked last.
        reservation = await asyncio.to_thread(self.policy.reserve, uid, charge_id, PILOT_HOLD_MICRO)
        LAST_USAGE.set(None)
        try:
            result = await call()
        except ValueError as error:
            # Raised by input validation or by the exhausted lifetime allowance,
            # both strictly before dispatch. Nothing was sent, so recording zero
            # is the honest settlement -- this is NOT a refund of an uncertain
            # charge. The monthly attempt still counts, deliberately.
            await asyncio.to_thread(self.policy.settle, reservation, 0)
            raise HTTPException(422, str(error) or 'This request could not be sent.') from None
        except ProviderFailure as failure:
            # The request may have reached the provider and may be billable.
            # Keep the hold; never settle and never retry.
            #
            # Record WHY server-side. The adapter's message carries the provider
            # and its HTTP status but never a response body or credential, and
            # the caller still gets a generic message. Without this a provider
            # outage is indistinguishable from a bug in our own code.
            record_failure(capability, failure)
            log.warning(json.dumps({'event': 'provider_failure', 'capability': capability,
                                    'reason': str(failure)[:200]}))
            raise HTTPException(502, 'The cloud provider could not complete this request; '
                                     'the reserved amount is retained.') from None
        # Succeeded. Settle the hold against what the provider said it cost,
        # when it said anything. The hold is a conservative ceiling -- $0.01 a
        # request, roughly fifty times a real translation -- so leaving it
        # standing made the ledger unreadable and burned the shared allowance
        # far faster than actual spending.
        #
        # When a provider reports no usage, the hold deliberately stands. An
        # unresolved hold says "this cost at most a cent", which is true;
        # settling at a guess would say something we do not know.
        reported = LAST_USAGE.get()
        if reported:
            actual = settled_micro(reported)
            if actual is not None:
                await asyncio.to_thread(self.policy.settle, reservation,
                                        min(actual, PILOT_HOLD_MICRO))
        return result


class ManagedBudget:
    """Lifetime-ledger stand-in for when the managed policy already owns it.

    FirestorePolicy enforces the shared US$5 ceiling itself, inside the same
    transaction that records the per-user hold. By the time a provider
    dispatches, PilotGateway has ALREADY reserved against that ceiling, so
    reserving again here would charge one request twice and halve the allowance.

    The provider name is still validated, so an unapproved destination is
    refused at exactly the point TestBudget would refuse it.
    """

    APPROVED = frozenset({'openrouter', 'groq', 'google_vision'})

    def reserve(self, provider, maximum_micro):
        if provider not in self.APPROVED:
            raise ValueError('Provider outside approved test scope')
        if type(maximum_micro) is not int or maximum_micro <= 0:
            raise ValueError('A positive maximum charge is required')
        return 'managed-by-policy'

    def settle(self, request_id, actual_micro):
        # Settlement belongs to whoever holds the reservation: the policy.
        return None
