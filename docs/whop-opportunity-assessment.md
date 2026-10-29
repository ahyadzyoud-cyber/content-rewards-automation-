# Fixed-bounty assessment

`rank_whop_bounties(report)` assesses the private, authenticated result of the official Whop bounty reader. It does not import a bounty as a CPM campaign. A fixed reward pays per approved deliverable; a CPM offer pays for qualifying views under separate terms. The adapter never invents a view count to convert between them.

Each result places `weaknesses` first. Discovery alone leaves `selectable=false` and `score_out_of_10=null`. `evidence_score_out_of_10` is a partial research score, not a verified opportunity recommendation or earnings forecast. It can help prioritize which briefs to review while eligibility is blocked.

An operator must separately review and retain dated, bounty-specific `BountyVerification` evidence for:

- This creator's Jordan residency admission and payout eligibility, including applicable account verification.
- Explicit acceptance of a new account with a zero-follower minimum.
- The exact material rights, available approved materials, current requirements, deadline and reward conditions.
- Provider and advertiser permission for the proposed automated workflow and permission for the intended YouTube or Instagram account.

The verification model records a separate HTTPS source reference, review date and conclusion for every fact. It rejects ambiguous boolean strings, naive timestamps, and credential-bearing or query-bearing evidence URLs. Keep these owner-specific records private. Import adapters must not create verifications from campaign text or self-reported booleans. Operators must verify evidence belongs to the currently authorized owner and target social account before using it.

Every required fact and the authenticated observation must be no more than seven days old. Expired, unknown or unreviewed deadlines block selection; an explicitly reviewed absence of a deadline is supported. A closed bounty, no available slots, a residency mismatch, an unsupported goal or an unknown/nonpositive quoted reward also blocks selection. A numeric score cannot override a blocker. Publication remains unapproved regardless of this assessment.

The fixed-bounty heuristic totals at most 10 points:

| Component | Maximum | Evidence and limitation |
| --- | ---: | --- |
| Quoted net fixed reward | 3 | USD only, `3 × net / (net + 25)`; other currencies receive no invented conversion. Production costs, tax, payout costs and approval risk remain unknown. |
| Creator-country and account eligibility | 2 | Fresh country, new-account and payout evidence, plus the provider's residency match. |
| Competition | 1.5 | `1.5 / (1 + competing_entries / 100)` only with separate fresh evidence. Accepted or pending submissions do not establish all competitors. |
| Observed open capacity | 2 | `2 × spots_remaining / (spots_remaining + 10)` with fresh observations. Slots do not establish unreserved cash budget. |
| Requirements and permissions | 1.5 | Fresh requirements, materials, rights, automation and platform evidence. |

Only opportunities that pass every gate receive `score_out_of_10`; verified entries sort before unverified research entries. Remaining cash budget is explicitly unverified unless supported by a separate documented source. The function does not submit, reserve a slot, publish content or mark earnings as received.
