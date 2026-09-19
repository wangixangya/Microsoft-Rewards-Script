// ---------------------------------------------------------------------------
// Fork enhancement: persist the rewards.bing.com session ticket ("tifacfaatcs").
//
// WHY THIS EXISTS
// `rewards.bing.com/api/getuserinfo` (the primary dashboard endpoint, marked
// "// Legacy, avoid!" upstream) answers with a ~36KB text/html
// "JavaScript required to sign in" placeholder to any plain-HTTP caller unless
// the request carries the `tifacfaatcs` cookie. That cookie is NOT a login
// credential and is NOT issued by the /earn page: only an actual navigation to
// an /api/* endpoint under rewards.bing.com makes the site hand it out. The
// script's browser therefore never receives it, the HTTP client never sends it,
// and the primary dashboard endpoint degrades to the Bing flyout fallback on
// every single run - which leaves `punchCards`, `dailyPromotions`, `morePromotions`
// and `promotionalItems` empty.
//
// WHAT THIS DOES
// Before the dashboard is fetched, navigate the *existing* browser context to
// the legacy endpoint once. That navigation makes the site issue `tifacfaatcs`
// into the context; the normal cookie synchronisation upstream already performs
// then persists it into sessions.db, so subsequent runs carry it and the primary
// endpoint returns the full JSON.
//
// VERIFIED (2026-09-19, single-variable A/B on rewards.bing.com/api/getuserinfo)
//   1. saved cookies only              -> 35,955 B text/html, not JSON
//   2. saved + only this one cookie    -> 624,142 B JSON   (dashboard complete)
//   3. all post-handshake cookies      -> 624,142 B JSON
//   4. post-handshake minus this cookie-> 35,877 B text/html, not JSON
// => the cookie is both necessary and sufficient; expiry is ~14 days.
//
// CONFLICT-AVOIDANCE (this is a fork that tracks upstream)
//   * Self-contained module: upstream has no equivalent file, so no conflict.
//   * Only ONE call site, guarded, additive. If upstream ever fixes this itself,
//     delete this file and the two lines in index.ts that reference it.
// ---------------------------------------------------------------------------

import type { BrowserContext, Page } from 'patchright'
import type { MicrosoftRewardsBot } from '../index'
import { URLs } from '../constants/urls'

/** Name of the session ticket cookie issued by rewards.bing.com /api/* endpoints. */
export const REWARDS_SESSION_TICKET = 'tifacfaatcs'

/** How long to wait for the ticket to appear after navigating (ms). */
const TICKET_WAIT_MS = 10_000
/** Poll interval while waiting for the ticket (ms). */
const TICKET_POLL_MS = 500

function sleep(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms))
}

function hasTicket(cookies: Array<{ name: string; domain?: string }>): boolean {
    return cookies.some(cookie => cookie.name === REWARDS_SESSION_TICKET)
}

/**
 * Ensures the rewards session ticket is present in the given browser context.
 *
 * Returns `true` when the ticket is available afterwards, `false` otherwise.
 * Never throws: a failure here only means the run continues with the existing
 * flyout fallback, which is the pre-existing behaviour.
 */
export async function ensureRewardsSessionTicket(
    bot: MicrosoftRewardsBot,
    context: BrowserContext,
    source = 'REWARDS-TICKET'
): Promise<boolean> {
    try {
        if (hasTicket(await context.cookies())) {
            bot.logger.debug(bot.isMobile, source, `${REWARDS_SESSION_TICKET} already present in context`)
            return true
        }

        // A navigation (not a fetch) is required: the endpoint only issues the
        // cookie when the request is a document load with the session cookies.
        const page: Page = await context.newPage()
        try {
            await page
                .goto(URLs.rewards.userInfoApi, { waitUntil: 'domcontentloaded', timeout: 60_000 })
                .catch(() => undefined)

            const deadline = Date.now() + TICKET_WAIT_MS
            while (Date.now() < deadline) {
                if (hasTicket(await context.cookies())) {
                    bot.logger.info(
                        bot.isMobile,
                        source,
                        `Acquired ${REWARDS_SESSION_TICKET} - primary dashboard endpoint should now return full JSON`
                    )
                    return true
                }
                await sleep(TICKET_POLL_MS)
            }

            bot.logger.debug(
                bot.isMobile,
                source,
                `${REWARDS_SESSION_TICKET} not issued after navigation; continuing with existing fallback`
            )
            return false
        } finally {
            await page.close().catch(() => undefined)
        }
    } catch (error) {
        bot.logger.debug(
            bot.isMobile,
            source,
            `Could not ensure ${REWARDS_SESSION_TICKET} | ${error instanceof Error ? error.message : String(error)}`
        )
        return false
    }
}

/**
 * Best-effort wrapper for call sites that already hold a Page. Swallows every
 * error so a ticket failure can never break the surrounding flow.
 */
export async function ensureRewardsSessionTicketFromPage(
    bot: MicrosoftRewardsBot,
    page: Page | null | undefined,
    source = 'REWARDS-TICKET'
): Promise<boolean> {
    if (!page || page.isClosed()) return false
    try {
        return await ensureRewardsSessionTicket(bot, page.context(), source)
    } catch {
        return false
    }
}
