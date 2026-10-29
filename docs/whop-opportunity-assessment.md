# Fixed-bounty assessment

`rank_whop_bounties(report)` assesses the private, authenticated result of the official Whop bounty reader. It does not import a bounty as a CPM campaign. A fixed reward pays per approved deliverable; a CPM offer pays for qualifying views under separate terms. The adapter never invents a view count to convert between them.

The owner authorization broker requests only **`bounty:basic:read`**, verified
against Whop's live [issuer metadata](https://api.whop.com/.well-known/openid-configuration)
and [List Bounties contract](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md)
on 2026-10-29. `bounty` and `bounty:basic` are not advertised scopes. Having the
read permission does not establish creator or campaign eligibility and grants
no submission, publication or payout authority.

Each result places `weaknesses` first. Discovery alone leaves `selectable=false` and `score_out_of_10=null`. `evidence_score_out_of_10` is a partial research score, not a verified opportunity recommendation or earnings forecast. It can help prioritize which briefs to review while eligibility is blocked.

An operator must separately review and retain dated, bounty-specific `BountyVerification` evidence for:

- This creator's Jordan residency admission and payout eligibility, including applicable account verification.
- Explicit acceptance of a new account with a zero-follower minimum.
- The exact material rights, available approved materials, current requirements, deadline and reward conditions.
- Provider and advertiser permission for the proposed automated workflow and permission for the intended YouTube or Instagram account.

The verification model records a separate HTTPS source reference, review date and conclusion for every fact. It rejects ambiguous boolean strings, naive timestamps, and credential-bearing or query-bearing evidence URLs. Keep these owner-specific records private. Import adapters must not create verifications from campaign text or self-reported booleans. Operators must verify evidence belongs to the currently authorized owner and target social account before using it.

Every required fact and the authenticated observation must be no more than seven days old. Expired, unknown or unreviewed deadlines block selection; an explicitly reviewed absence of a deadline is supported. A closed bounty, no available slots, a residency mismatch, an unsupported goal or an unknown/nonpositive quoted reward also blocks selection. A numeric score cannot override a blocker. Publication remains unapproved regardless of this assessment.

Personal capacity is a separate gate: the authenticated
`viewer_accepted_submissions_count` must be below a positive
`accepted_submissions_per_user_limit`, which cannot exceed the bounty's total
`accepted_submissions_limit`. Missing fields in older saved reports remain
unknown and block selection until refreshed; the provider's documented default
of one is never fabricated locally. A zero cap is not unlimited. Global open
slots do not override an exhausted personal allowance. Whop permits one attempt
at a time per creator and bounty, and wins plus proofs awaiting review cannot
exceed the personal cap. Global `unresolved_submissions_count` cannot establish
this owner's pending attempts; current personal attempt status must still be
checked through permitted methods before execution. See the official
[List Bounties contract](https://docs.whop.com/api-reference/beta/bounties/list-bounties.md).

The fixed-bounty heuristic totals at most 10 points:

| Component | Maximum | Evidence and limitation |
| --- | ---: | --- |
| Quoted net fixed reward | 3 | USD only, `3 × net / (net + 25)`; other currencies receive no invented conversion. Production costs, tax, payout costs and approval risk remain unknown. |
| Creator-country and account eligibility | 2 | Fresh country, new-account and payout evidence, plus the provider's residency match. |
| Competition | 1.5 | `1.5 / (1 + competing_entries / 100)` only with separate fresh evidence. Accepted or pending submissions do not establish all competitors. |
| Observed open capacity | 2 | `2 × spots_remaining / (spots_remaining + 10)` with fresh observations. Slots do not establish unreserved cash budget. |
| Requirements and permissions | 1.5 | Fresh requirements, materials, rights, automation and platform evidence. |

Only opportunities that pass every gate receive `score_out_of_10`; verified entries sort before unverified research entries. Remaining cash budget is explicitly unverified unless supported by a separate documented source. The function does not submit, reserve a slot, publish content or mark earnings as received.

## Optional economic planning

Economic planning requires separate, fresh operator-reviewed evidence for each
assumption: `production_cost_usd` with `production_cost_evidence`,
`production_hours` with `production_time_evidence`, and
`acceptance_probability` with `acceptance_probability_evidence`. All default to
unknown. Cost is nonnegative, time must be positive, and probability is between
zero and one. An acceptance estimate needs its own documented basis; accepted
and pending submission counts do not establish a probability for this creator.
Importing provider observations does not create these reviews.

Only a fresh positive USD reward and all three separately reviewed assumptions
produce an `economic_scenario`:

- `expected_net_usd = quoted_net_reward × acceptance_probability − production_cost_usd`
- `expected_net_per_hour_usd = expected_net_usd / production_hours`

Production cost applies to every attempted deliverable, including rejection.
The operator must include the actual planned costs; taxes and unmodeled fees may
reduce the result. These are planning scenarios based on reviewed assumptions,
not verified earnings, payment promises, or spending authorization. Missing,
stale or unconfirmed evidence, another currency, and nonfinite calculation
results produce null estimates with an explanation. No conversion, costs,
production time or acceptance probability are invented.

The main queue keeps its evidence-score ordering, so unknown economics are not
treated as zero or pushed behind modeled offers. A separate
`economic_priority_rank` compares only eligible offers with complete scenarios:
higher estimated net per hour first, then higher estimated net per attempt,
then evidence score and bounty ID. Unknown or blocked offers have a null
economic rank. The two orders serve different purposes; economic rank does not
establish campaign admission or change the score out of 10. All positive quoted
rewards remain in the queue, including small rewards and negative modeled net
results. Neither ordering introduces a minimum reward or authorizes execution.
