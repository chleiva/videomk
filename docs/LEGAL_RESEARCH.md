# Legal research behind the privacy policy and terms (seen 2026-11-26)

Purpose: check our drafts against what responsible products cover. Structure and coverage only: no wording is copied. Not legal advice. Pages were read through a summarising fetch tool, so a "not mentioned" below means "not found in what the tool returned", not proof of absence.

## Sources (URL, date seen 2026-11-26, version date the page showed)
| Product | Pages | Version shown |
|---|---|---|
| Anthropic consumer | https://www.anthropic.com/legal/privacy ; https://www.anthropic.com/legal/consumer-terms | privacy 10 Sep 2026; consumer terms 8 Oct 2025 (UK version) |
| Anthropic commercial | https://www.anthropic.com/legal/commercial-terms | 17 Jun 2025 |
| OpenAI | https://openai.com/policies/privacy-policy/ ; https://openai.com/policies/terms-of-use/ | privacy 25 Aug 2026; EU terms 16 Jan 2026 |
| Google | https://policies.google.com/privacy ; YouTube https://www.youtube.com/t/terms | privacy 16 Oct 2026; YouTube terms 17 Mar 2025 |
| Pictory | https://pictory.ai/privacy-policy ; https://pictory.ai/terms | no date shown |
| HeyGen | https://www.heygen.com/privacy ; https://www.heygen.com/terms | privacy 15 Oct 2026; terms 16 Oct 2026 |
| Synthesia | https://www.synthesia.io/de/legal/privacy-policy ; https://www.synthesia.io/legal/user-terms-of-service | privacy 1 Oct 2026; user terms 23 Feb 2024 |
| Canva | https://www.canva.com/policies/privacy-policy/ ; https://www.canva.com/policies/terms-of-use/ | privacy 2 Nov 2026; terms 16 Nov 2026 |
| Descript | https://www.descript.com/privacy ; https://www.descript.com/terms | privacy 14 Apr 2025; terms 25 Feb 2025 |
| Runway | https://runway.com/terms-of-use (privacy page redirected and then failed to load) | terms 23 Oct 2026 |
| Notion | not retrieved (three URLs returned 404/redirect); dropped | - |
Provider facts used for our own statements: AWS Bedrock data protection (https://docs.aws.amazon.com/bedrock/latest/userguide/data-protection.html: model makers have no access to prompts or logs), cross-Region inference (https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference.html: global profiles may route to any commercial region), Step Functions quotas (https://docs.aws.amazon.com/step-functions/latest/dg/service-quotas.html: execution history kept 90 days after close, 30 on request), Tavily privacy policy (https://www.tavily.com/privacy, updated 24 Nov 2025: may use query data to improve its service; may pass queries to search index providers such as Google).

## Coverage matrix (Y covered, P partly or by reference, - not found)
Columns: A Anthropic, O OpenAI, G Google/YouTube, Pi Pictory, H HeyGen, S Synthesia, C Canva, D Descript, R Runway, **V = our drafts**.
| Topic | A | O | G | Pi | H | S | C | D | R | V |
|---|---|---|---|---|---|---|---|---|---|---|
| Data collected (account, content, usage, device) | Y | Y | Y | Y | Y | Y | Y | Y | P | Y |
| Purposes | Y | Y | Y | Y | Y | Y | Y | Y | P | Y |
| Legal bases table (GDPR Art. 6/13) | Y | Y | Y | - | Y | Y | Y | Y | P | Y |
| Sharing and named processors | Y | Y | Y | P | P | P | Y | P | P | Y |
| International transfers and safeguards | Y | Y | Y | P | Y | Y | Y | P | P | Y |
| Retention periods | P | Y | P | P | Y | P | P | P | P | Y (table) |
| Security | P | P | Y | - | - | P | - | - | - | Y |
| Children and minimum age | 18 | 13 / 18 | P | 13 | 18 | 16/18 | 13 | 13 | 13 | 13 |
| Rights (access, deletion, portability, objection, complaint) | Y | Y | Y | Y | Y | Y | Y | Y | P | Y |
| CCPA/CPRA, do not sell/share | P | - | - | Y | Y | P | Y | Y | - | Y |
| Cookies and analytics | Y | Y | Y | Y | Y | Y | Y | Y | P | Y |
| Training on user content, opt-out | Y (opt-out) | Y (opt-out) | Y | P | Y | P | Y | Y | Y (no opt-out) | Y (none) |
| Human review of content | P | - | P | - | - | - | - | Y | P | Y |
| Output ownership and accuracy | Y | Y | - | Y | Y | Y | Y | Y | Y | Y |
| AI-disclosure duty on users | - | P | - | - | Y | P | - | - | - | Y |
| Likeness and voice consent | - | P | - | Y | Y | Y | - | Y | P | Y |
| User content licence | Y | Y | Y | Y | Y | P | Y | Y | Y | Y (minimal) |
| Acceptable use | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y (real categories) |
| IP / copyright notices | P | Y | Y | Y | - | - | Y | Y | Y | Y |
| Third-party stock content and credits | - | - | - | Y | - | P | Y | - | - | Y |
| Payments, credits, refunds | Y | Y | - | Y | Y | P | Y | - | Y | Y (no payments yet) |
| Suspension and termination | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y (with appeal) |
| Disclaimers | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Liability cap with consumer carve-outs | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Indemnity | P | Y (business) | - | Y | Y | - | Y | Y | Y | Y (light) |
| Changes and notice | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y (14 days) |
| Governing law and disputes | Y | Y | Y | Y (AAA) | Y (AAA) | Y | Y (AAA) | Y (AAA) | Y (JAMS) | Y (courts) |
| Contact | Y | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Accessibility | - | - | - | - | - | - | - | - | - | - (see notes) |

Summary: the union of topics is all present in our drafts except accessibility (no one covered it in the pages read; we have a plain-language layout, semantic headings, tables with headers). Our drafts go further than the comparables on retention (a table with real periods), on naming processors and what each receives, and on safety enforcement and appeal.

## Good practices copied in spirit
1. A short "at a glance" list before the legalese (several; ours already had it).
2. A legal-basis table that maps each purpose to a basis (OpenAI, Anthropic, HeyGen).
3. Named processors and what each gets, plus a link to the provider list (Synthesia, HeyGen).
4. Explicit retention times, including how long deleted data lingers in backups (HeyGen 60 days, OpenAI 30 days): ours says 35 days and 90 days honestly.
5. Separate rules for biometric and likeness data with explicit consent (HeyGen, Synthesia): we adapted it as a likeness and consent clause and a no-voice-cloning statement.
6. UK/EU consumer-style terms: law of the consumer's country preserved, no arbitration (OpenAI EU, YouTube UK, Anthropic UK).
7. Liability cap with "greater of fees paid in 12 months or a small fixed sum", with statutory carve-outs (Anthropic UK).
8. Advance notice (30 days) of material changes (OpenAI, Anthropic): ours promises 14 days.
9. Stock-content licences explained next to the product (Canva, Pictory), with a ban on using the content standalone.
10. An appeal path for takedowns and enforcement (Anthropic, YouTube).

## Clauses that look unusual or risky for a small company (we did not copy them)
1. Perpetual, irrevocable, sublicensable licences to user content, including training rights without opt-out (Runway, HeyGen, Descript): invites complaints and, in the EU, unfair-term findings.
2. Mandatory US arbitration, class waivers, fee shifting and one-year claim limits (HeyGen, Descript, Runway, Canva): unenforceable or void against EU/UK consumers.
3. "No expectation of privacy" and consent to monitoring (Runway) and employer takeover of accounts: conflicts with GDPR transparency.
4. Terms changes accepted by continued use with no notice (Pictory, Descript): weak under UK/EU consumer law.
5. Broad, uncapped user indemnities (Canva, Descript, Pictory): our version is limited to third-party claims caused by the user and excludes consumers beyond what the law allows.
Also note the comparables are inconsistent in themselves (wrong cross references, undefined terms): re-read our cross-references (`support.astro` points to Terms section 15; Privacy cross-references sections 4, 5, 7, 8, 9, 10, 13) whenever sections are added.
