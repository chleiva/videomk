# Legitimate interests assessment: use ratings and abuse records (2026-11-27)

Controller: Agilegency Ltd (company number 16838077, ICO reference ZC137157), contact hello@videomk.com. Service: videomk, for people aged 16 and over.

Status: a first assessment written without a lawyer. It is not legal advice. It records the reasoning the ICO asks for before relying on legitimate interests; section 7 lists what a lawyer should check. Review it when either feature changes, and at the latest 12 months from this date.

It covers two separate processing activities, because they have different purposes and different effects on people:

* **A. Use ratings** (tracker R140): each video request gets a rating from 1 to 5 for the kind and seriousness of use, and a short summary is kept per account.
* **B. Abuse records** (tracker R137, R141): stops by the safety check and their category recorded against the account, account warnings and suspensions, the free-credit record kept after account deletion, device checks and IP limits.

Published text that matches this assessment: Privacy Policy sections 2, 3, 7, 10, 13 and 17, Terms sections 5, 8, 9 and 16 (`frontend/src/data/legal/`, English and Spanish).

## 1. The method

The ICO says that to rely on legitimate interests "you must do the three-part test": "(1) The purpose test (identify the legitimate interest). (2) The necessity test (consider if your use of the personal information is necessary). (3) The balancing test (consider the person's interests)." It calls the record of that test a legitimate interests assessment, "a type of light-touch risk assessment", and says "You should record your LIA and the outcome" [ICO-2]. There are "no purposes that automatically constitute a legitimate interest for this lawful basis" [ICO-3], so both activities are tested below.

## 2. Activity A: use ratings

### 2.1 What is done
* When a request is checked, the same AI model call (inside the company's AWS account) returns a number from 1 to 5 for the kind and seriousness of the use: 5 is a proper business or publishing use, 1 is a throwaway test.
* A rolling summary is kept per account. Only the people who run videomk can see it (admin report).
* A person uses the report to understand who the users are, to improve the product, and to decide which accounts to contact with offers or to give extra credits.

This is profiling: the UK GDPR definition quoted by the ICO is "Any form of automated processing of personal data consisting of the use of personal data to evaluate certain personal aspects relating to a natural person" [ICO-4].

### 2.2 Purpose test
* Why: a small company with no funding to waste needs to know which of its users have a real use for the product, where to spend free credits, and what to build next. Those are commercial interests of the company. They are lawful, specific and real, not speculative.
* Benefit to users: better-targeted product work, and offers or extra credits for some of them. There is no claimed wider public benefit; the ICO warns against "vague statements about wider presumed benefits" for marketing purposes [ICO-3].
* Direct marketing is a purpose for which the UK GDPR says the basis "may" apply [ICO-3]. The ICO adds: "if you use profiling to target your direct marketing, you must be specific about this to show that it's necessary" [ICO-3]. The privacy policy is specific about it (section 17).
* Outcome: a legitimate interest exists.

### 2.3 Necessity test
The ICO's questions include "Can you achieve your purpose without using the personal information, or by using less information?" and whether there is a "more obvious or less intrusive way" [ICO-2].
* Aggregate statistics alone would answer "what is videomk used for" but not "which accounts should we talk to or reward". That second purpose needs a per-account signal.
* Less intrusive options considered: (a) asking users what they use it for (planned as a complement; most people do not answer, and the answers of those who do are not checked against use); (b) counting videos only (cheap to game and says nothing about the kind of use); (c) a person reading prompts (far more intrusive than a number, and the privacy policy says staff do not read prompts as a matter of course).
* Data is minimised: the rating reuses the request text that is already processed to make the video and to check it; nothing new is collected; what is stored is a number, a broad kind of use and a summary, not a description of the person.
* Outcome: necessary and proportionate for the per-account purpose, provided the safeguards in 2.5 are built.

### 2.4 Balancing test
* Nature of the data: request text can contain anything a person types, including personal or sensitive subjects. The rating must not record the subject. No special category data is inferred or stored.
* Reasonable expectations: the ICO says "This is an objective test" and that you should show that "a reasonable person would expect the processing in the particular circumstances" [ICO-2]. A person using an online service would expect the provider to look at how the service is used and to send offers to engaged customers. They may not expect each request to be rated by an AI model. That gap is closed by telling them plainly: the policy has an "at a glance" line and its own section.
* Likely impact: low. The rating brings only benefits (offers, extra credits). It does not change price, features, video quality or enforcement. The realistic harms are (i) a feeling of being watched, (ii) unwanted marketing, (iii) unequal treatment, because some users receive credits that others do not, (iv) a wrong rating. (i) and (ii) are answered by the notice and the opt-out; (iii) is limited to discretionary gifts and never removes anything a user already has; (iv) has no adverse consequence.
* Children: the service is for people aged 16 and over, so some users are 16 or 17. The ICO says "children's interests need particular protection" [ICO-3]. The same safeguards apply, and no marketing is sent without the marketing rule in 2.6 being met. See open point 7.6.
* Right to object: for direct marketing "This includes any profiling of information that is related to direct marketing. This is an absolute right" [ICO-5]. For other legitimate-interest processing the right is qualified, but videomk will not argue "compelling legitimate grounds": every objection is honoured, the rating stops and the ratings and summary are deleted. The ICO requires that "You must bring details of this right specifically to their attention" [ICO-4]; the policy does so in the glance list, section 13 and section 17.
* Automated decisions: for a decision to be solely automated "there must be no human involvement in the decision-making process" [ICO-4]. Here a person decides whom to contact and what to offer, and the effect (an offer or free credits) is not a legal or similarly significant effect. The policy states that no such decision is made from the rating.

### 2.5 Safeguards the engineering work must deliver (conditions of this assessment)
1. Rate the use, not the person: the stored fields are the number, a broad kind of use and counts. No free-text reasoning about the person.
2. No sensitive inferences: the model is told not to infer or output health, ethnic origin, religion or beliefs, political opinions, sex life, sexual orientation, trade union membership, or criminal matters, and requests on such subjects are not labelled by subject.
3. Opt-out: an account flag that stops rating and deletes the ratings and summary; honoured on an email to hello@videomk.com; no reason needed; no effect on the service.
4. Admin-only access: readable only through the admin report; never returned by the API to apps, never shown to other users, never shared outside the company.
5. A human decides outreach: the report informs; it does not send messages or grant credits by itself.
6. Benefits, not detriment: the rating is never an input to pricing, limits, queue priority, video quality, safety enforcement, suspension or closure.
7. Retention: each rating for no more than 12 months; the summary only while the account exists; both deleted on objection and on account deletion. The policy states these periods, so the build must meet them.
8. Keep the rating out of records that cannot be deleted: do not put it in the Step Functions execution input (that history is kept by AWS for 90 days and cannot be removed earlier) or in logs.
9. Add the ratings store to the account-deletion coverage guard.

### 2.6 Marketing messages
Deciding whom to contact is one thing; sending the message is another, and it has its own rules (PECR). The ICO: "you must not send electronic mail marketing to individuals, unless: they have specifically consented to electronic mail from you; or they are an existing customer who bought (or negotiated to buy) a similar product or service from you in the past, and you gave them a simple way to opt out both when you first collected their details and in every message you have sent" [ICO-6]. And: "If PECR require consent, you must not use legitimate interests as your lawful basis for using personal information for that purpose" [ICO-3].

Consequences today: videomk has no paying customers and sign-up shows no marketing opt-out, so the soft opt-in is probably not available for current accounts. Until a lawyer says otherwise, send offers by email only to people who have opted in (a switch in Settings or a tick at sign-up, off by default). Extra credits added to an account with no message are not an electronic marketing message. An in-app notice or a push notification about an offer may be; treat it like email until checked.

### 2.7 Outcome for A
Legitimate interests can be relied on for the rating and the summary, with the safeguards in 2.5 as conditions. Email marketing itself runs on consent (or the soft opt-in only where its conditions are really met).

## 3. Activity B: abuse records

### 3.1 What is done
* Requests are checked automatically for prohibited content. A stop leaves a record for 90 days: category, time, the first 160 characters, a one-way fingerprint of the request. Requests that pass leave none.
* Repeated or serious stops lead to a warning, a 24-hour pause, a hold or suspension reviewed by a person, or closure decided by a person.
* One free allowance per person: a salted HMAC of the normalised email address, of the Google or Apple sign-in identity and of the app's device key. It has no account id, cannot be reversed without a secret held in AWS Secrets Manager, and is kept for 2 years, including after account deletion, solely to prevent repeat claims.
* Device integrity checks in the apps (Apple App Attest and DeviceCheck, Google Play Integrity) and limits per IP address and network block (counters kept up to 8 days).

### 3.2 Purpose test
* Preventing the service being used to make illegal or harmful content, protecting other people, and protecting the company from fraud on its free credits (each free video costs real money, and the owner's stated concern is that free usage must not make the business unviable).
* These are interests of the company, of other users and of third parties who could be harmed by content. Security of systems is a purpose for which the UK GDPR says the basis "may" apply [ICO-3].
* The ICO also describes a separate basis, recognised legitimate interest, whose pre-approved purposes include "preventing, detecting or investigating crimes (including fraud)" [ICO-3]. This assessment does not rely on it; whether part of activity B could is open point 7.3.
* Outcome: a legitimate interest exists.

### 3.3 Necessity test
* Without a record of stops the service could not tell one mistake from a pattern, so it could not escalate in proportion or review an appeal with evidence. The record is minimal (160 characters, not the full request) and short (90 days).
* Without a marker that survives account deletion, deleting and re-registering resets the free allowance, which defeats the limit. Less intrusive alternatives considered: no free allowance at all (available as a setting, but removes the product's trial); requiring a payment card (far more data); keeping the email address itself (more intrusive than a keyed hash). The keyed hash is the least intrusive option that works.
* Device checks and IP limits address bots and bulk sign-ups that an email-based rule cannot. videomk receives a verdict and an app-installation key, not hardware identifiers.
* Outcome: necessary and proportionate.

### 3.4 Balancing test
* Reasonable expectations: people expect an online service to check for prohibited content, to act on abuse and to limit free offers to one per person. The Terms state the rules and the consequences; the privacy policy describes each record.
* Impact: higher than activity A, because the outcome can be adverse (a refused request, a suspension, a closed account, no free credits). Safeguards: nothing is charged for a stopped request; pauses are short; a hold or suspension is reviewed by a person; closure is decided only by a person; reasons are given where reasonably possible; anyone can ask for a human review by email and mistakes are reversed.
* The free-credit record after deletion is the point most likely to surprise someone who has deleted their account. Mitigations: it is disclosed in the privacy policy (sections 2, 7, 10 and 13) and on the delete-account page; it contains no account details; it serves one purpose; it expires after 2 years; its only effect is that free credits are not granted a second time, and the account can still watch and pay.
* A keyed hash of an email address is still personal data while the key exists (pseudonymised, not anonymous). It is treated as such here.
* Automated effects: the stop and the 24-hour pause happen automatically. A refused video request or a one-day pause of a free creative tool is unlikely to be a "legal or similarly significant" effect, but this is the nearest part of the design to that line: see open point 7.2. A human review is offered in all cases.
* Outcome: the company's and third parties' interests are not overridden, given the safeguards.

### 3.5 Safeguards (conditions)
1. Human review of every hold, suspension and closure; permanent closure only by an admin; an audit log of who did what and why.
2. Notice and reason to the user where reasonably possible; an appeal path by email with a human answer.
3. Stop records: 90 days, admin-only, re-keyed to a scrambled reference on account deletion (as built).
4. Free-credit record: keyed hash only, secret in Secrets Manager, no account id, 2-year expiry, used for nothing else.
5. IP counters keyed by a hash of the address, 8 days.
6. Abuse data and use ratings are kept apart: an abuse record is never an input to the rating and the rating is never an input to enforcement.

## 4. EU AI Act: the prohibition on social scoring

Regulation (EU) 2024/1689, Article 5(1)(c), prohibits "the placing on the market, the putting into service or the use of AI systems for the evaluation or classification of natural persons or groups of persons over a certain period of time based on their social behaviour or known, inferred or predicted personal or personality characteristics, with the social score leading to either or both of the following: (i) detrimental or unfavourable treatment of certain natural persons or groups of persons in social contexts that are unrelated to the contexts in which the data was originally generated or collected; (ii) detrimental or unfavourable treatment of certain natural persons or groups of persons that is unjustified or disproportionate to their social behaviour or its gravity" [AIA-1]. Recital 31 adds: "That prohibition should not affect lawful evaluation practices of natural persons that are carried out for a specific purpose in accordance with Union and national law" [AIA-2]. Article 5 has applied since 2 February 2025.

Why this design stays outside it, on our reading:
* The use rating does classify people's use over time with an AI system, so the first half of the definition is arguably met. The prohibition then needs one of the two outcomes, and neither occurs.
* (i) Unrelated context: the rating is produced from use of videomk and used only inside videomk, for videomk's own offers. It is not shared, sold or used in any other context.
* (ii) Unjustified or disproportionate detriment: the rating leads to no detriment. It can only lead to an offer or extra credits, and it is never used for price, access, quality or enforcement. Not receiving a discretionary gift is the one arguable "unfavourable treatment"; it is the ordinary result of a loyalty or promotion scheme and it is tied to the same context.
* Enforcement (activity B) is not a score of the person: it responds to specific prohibited requests, in the same context, with graduated and reviewable consequences proportionate to their gravity.
* To stay outside: never use the rating to penalise, restrict or price; never share it; never combine it with data from outside videomk; never rate personality or social behaviour.

The AI Act applies only if videomk is offered to people in the EU (it is: the policy addresses EU users). The UK has no equivalent prohibition in force that we know of; UK GDPR applies as above.

Seen while checking the text, outside this assessment but relevant to a video generator: the copy of Article 5 we read [AIA-1] shows amendments marked as applying from 2 December 2026 that add prohibitions about AI systems generating child sexual abuse material and non-consensual intimate imagery. We did not verify this against the Official Journal. A lawyer should confirm what it requires of videomk's safety check.

## 5. Decision

| Activity | Basis | Outcome |
|---|---|---|
| A. Use ratings and per-account summary | Legitimate interests (understanding users, improving and growing the service) | Can proceed once the safeguards in 2.5 are built and the privacy policy is live. Tell existing users before the rating starts |
| A. Marketing emails | Consent (soft opt-in only where its conditions are met) | Build an opt-in before sending any |
| B. Safety stops, escalation, suspension | Legitimate interests (preventing harm); legal obligation where the law requires action | Can proceed with 3.5 |
| B. Free-credit record, device checks, IP limits | Legitimate interests (preventing abuse of free credits) | Can proceed with 3.5 |

## 6. Sources (all fetched on 2026-11-27; quotations are copied from the pages as served that day)

* [ICO-1] ICO, "Legitimate interests" (detailed guidance; latest update shown: 23 March 2026, "to reflect amendments introduced by the Data (Use and Access) Act"). https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/
* [ICO-2] ICO, "How do we apply legitimate interests in practice?" https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/how-do-we-apply-legitimate-interests-in-practice/
* [ICO-3] ICO, "When can we rely on legitimate interests?" https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/legitimate-interests/when-can-we-rely-on-legitimate-interests/
* [ICO-4] ICO, "Rights related to automated decision making including profiling". https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/rights-related-to-automated-decision-making-including-profiling/
* [ICO-5] ICO, "Right to object" (latest update shown: 2 November 2026). https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/individual-rights/individual-rights/right-to-object/
* [ICO-6] ICO, Guide to PECR, "Electronic mail marketing" (the page says: "Due to changes made by the Data (Use and Access) Act, this guidance is under review and may be subject to change"). https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/
* [AIA-1] Regulation (EU) 2024/1689, Article 5. Official text: https://eur-lex.europa.eu/eli/reg/2024/1689/oj (EUR-Lex returned an empty page to our tools on the day, so the wording quoted was read from the reproduction of the Official Journal text at https://artificialintelligenceact.eu/article/5/ ; check it against EUR-Lex).
* [AIA-2] Regulation (EU) 2024/1689, recital 31, read at https://artificialintelligenceact.eu/recital/31/ (same caveat).

## 7. Open points for a lawyer

1. **Soft opt-in for free accounts.** Whether people with a free account have "bought (or negotiated to buy)" anything, and whether an opt-out must be shown at sign-up for it to apply later. Until answered: consent only. Also whether in-app messages and push notifications about offers count as electronic mail under PECR.
2. **Automated decisions.** The ICO page still describes Article 22; the Data (Use and Access) Act 2025 changed the UK rules on automated decision-making. Confirm that (a) the rating involves no "significant decision", and (b) the automatic stop and 24-hour pause in activity B either are not significant decisions or meet the new safeguards (information, a way to contest, human intervention). Check the EU GDPR Article 22 position for EU users as well.
3. **Recognised legitimate interest.** Whether preventing fraud on free credits and detecting illegal content can rest on the recognised legitimate interest basis (crime prevention) instead of, or as well as, the balancing test here.
4. **The free-credit record after deletion.** Whether 2 years is defensible against the storage-limitation principle and the right to erasure (the argument: overriding legitimate grounds, minimal pseudonymised data, single purpose); whether a shorter period would do. Whether Apple's and Google's device markers (DeviceCheck bits, Play Integrity device recall), which survive app reinstall, need anything more than the disclosure given, including under the PECR rules on storing or reading information on a device.
5. **DPIA.** Whether profiling of requests by an AI model, plus enforcement decisions, calls for a data protection impact assessment. A short one is a prudent next step whatever the strict answer.
6. **Users aged 16 and 17.** Whether profiling for marketing should be off by default for them (check the profiling standard of the ICO's Children's code, which was not read for this assessment), and how age would be known. videomk does not collect age today.
7. **EU users.** Whether an EU representative is needed (Article 27 EU GDPR), and whether EU authorities' stricter line on legitimate interests for marketing-related profiling changes the answer for EU users (consent instead).
8. **Google sign-in data.** The policy says videomk follows Google's API Services User Data Policy, including Limited Use. Confirm that using the Google identity for the free-credit record (abuse prevention) and the Google-supplied email for opted-in offers is compatible.
9. **Terms.** Fairness under the Consumer Rights Act 2015 of: closure without notice "where the law requires it or where that is needed to protect people, other users or the service"; no refund of unused paid credits on closure for breach (drafted "so far as the law allows"); the discretion to change or withdraw free and promotional credits; and the refund promised when an account is ended for a reason that is not the user's breach. Also what must legally be preserved and reported (for example child sexual abuse material: the UK and US reporting duties, and that preserving such material is itself tightly regulated).
10. **AI Act.** The reading in section 4, and the December 2026 amendments noted there.
11. **Notice to existing users.** Whether the in-app or email notice planned before the rating starts is enough, and its timing (the Terms promise 14 days' notice of material changes).
