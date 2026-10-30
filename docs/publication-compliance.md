# Mandatory campaign publication checks

Broad `requirements_verified` and `rights_verified` flags do not establish that
a particular rendered video meets the brief. Approval and publication now require
a separate `publication_spec` reviewed against the full official brief. Existing
records remain readable; missing specifications block approval and publishing.
`REWARDS_LIVE_PUBLISHING=false` remains configured.

## Review the actual brief

The specification retains the complete text, its SHA256, official HTTPS source,
review date and an explicit completeness review. Every mandatory clause needs
an inventory item, including additional clauses within the same category.
The inventory covers platform, duration, format, aspect ratio, content, title,
caption, hashtags, mentions, account rules, deadline, minimum views, livestream,
submission, rights and disclosures. A category with no requirement still needs
a dated, evidenced conclusion; an omitted or unknown category is not permission.
Completeness is an operator review, not a claim that a parser understands every
campaign clause. Provider imports cannot attest their own completeness.

Applicable physical constraints use measurements from the actual rendered file.
Checks compare duration, aspect ratio, container brand, exact platform and
required title/caption fragments, hashtag tokens and mentions. MOV and MP4 share
an FFprobe demuxer name, so renaming a MOV to `.mp4` does not pass the MP4 check.
Unsupported technical conditions must remain critical and unknown until a
supported check exists; the format check alone does not establish arbitrary
codec, frame-rate or resolution requirements.

Content, account, material rights, disclosures and human participation need
individual evidence when applicable. The proof binds the exact rendered bytes,
metadata, current campaign evidence and target account. Changes invalidate that
review. A complete human livestream cannot be replaced with a fabricated or
prerecorded substitute. Publicly accessible footage is not a reuse license.

## Review a rendered deliverable

The operator can record individual proof entries in a private JSON file keyed
by inventory requirement ID. Each proof has `status`, `evidence_url` and `note`.
Use only actual evidence and secure private storage; do not commit owner records,
credentials or campaign briefs to this public repository.

```sh
rewards review-compliance JOB_ID /private/path/proofs.json
rewards preflight JOB_ID
# Only after actual owner approval and a successful compliance review:
rewards approve JOB_ID --reason 'Record the actual owner review'
```

For Instagram, provide the approved immutable `--video-url` when recording the
review, before its digest is bound. Recording proof never approves publication.
Approval, the staged video immediately before the first provider write, and
Instagram's final publication step all enforce the gate. Unknown/unmet critical
requirements, changed evidence, missing payout eligibility or unknown qualifying
terms stop the operation. Existing write claims and reconciliation barriers
remain in place; a compliance review cannot overwrite an in-progress upload.

## Prepare and retain the queue

Automatic preparation applies reviewed duration bounds and literal required
metadata that the existing editor supports. Unsupported constraints, invalid
renders and measured mismatches are deferred so another eligible campaign can
be considered. Smaller offers stay queued. A rendered draft still needs its
applicable manual proofs and explicit owner publication approval.

Minimum views and later submission evidence remain pending after publication;
the system does not require future views before the initial post, treat pending
requirements as passed, or infer reward acceptance from a successful upload.
The submission ledger is operator-recorded evidence, not an automated provider
submission/approval/payout integration. Actual write permissions and the approved
campaign submission process must be verified before enabling such automation.

## Current real execution result

Both known Whop bounty details were retrieved using the documented public
detail API and compared with the authorized listings. Full private checklists
were retained. Both are temporarily deferred: one requires attached clip assets
and a live editing demonstration; the other requires a TikTok slideshow and an
uncut creation/posting livestream. Neither is a verified automated YouTube or
Instagram publication opportunity. No campaign-approved licensed source files
or authorized social accounts are configured. No real video can honestly be
presented for approval yet, and no reward is promised.
