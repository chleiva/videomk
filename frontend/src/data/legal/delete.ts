import type { LegalContent, Locale } from "./types";
import { CONTACT_EMAIL } from "../legal";
import { esDelete } from "./delete.es";

function en(): LegalContent {
	const glance = ["The quickest way is in the iPhone or Android app: Settings, Delete account. The website has no delete button yet: use the email route below.", "If you cannot sign in, email us from the address on your account and we do it for you.", "Deleting removes your videos, photos, credits and sign-in. It cannot be undone.", "A few copies disappear on their own timetable (up to 90 days): see \"What can remain for a while\"."];
	const sections = [
		{ title: "Delete your account in the app", bullets: [
			"Open videomk, go to Settings, then Delete account, and confirm. For your security we ask you to sign in again first.",
			"We delete your videos, narration and photos, your My media library, your credit balance and history, and the plan behind each video. This cannot be undone, and any credits you have left are lost.",
			"Your data is removed within minutes. Your sign-in is switched off straight away and removed completely within about an hour or two; until then you cannot use it, and you should wait that long before signing up again with the same email.",
			"If you signed in with Apple, the app also asks Apple to stop sharing your account with videomk, and you can check it any time in your iPhone’s Settings under your name, Sign in with Apple. If you signed in with Google, you can remove videomk in your Google Account under Security, Third-party access."] },
		{ title: "If you cannot sign in", bullets: [
			`Email ${CONTACT_EMAIL} from the address you use to sign in to videomk, with the subject “Delete my videomk account”.`,
			"If you signed in with Apple and chose Hide My Email, write from the account email shown in the app (Settings), because we cannot find your account from Apple’s private relay address.",
			"We may ask you to confirm it is you, for example by replying to a message we send to that address. We finish within 30 days and confirm by email."] },
		{ title: "What can remain for a while", paras: [
			"Some copies are outside our control or kept for a fixed time, and then disappear by themselves:",
		], bullets: [
			"Workflow records kept by AWS for each video (they include the text of your request and options) are removed by AWS 90 days after the video was made. We cannot delete them sooner.",
			"Database backups can hold deleted data for up to 35 days.",
			"Technical logs are deleted after 14 days. They hold your account id but not your email address.",
			"If our safety check stopped a request of yours, a short record (type of reason, time, the first 160 characters and a fingerprint of the request) is kept for the rest of its 90 days under a scrambled reference, not your account details.",
			"If we are ever legally required to keep purchase records for accounting, only those are kept, for the period the law requires. Purchases made through Apple or Google stay in their records; cancel any subscription with them.",
			"Free credits are not restored if you sign up again: deleting your account removes your balance. To make sure of that, we keep a salted, one-way fingerprint of your email address, of your Google or Apple sign-in identity and of the app’s device key for 2 years from the day the free credits were given. It holds no account details and cannot be turned back into them, and it is used solely to stop free credits being collected twice."] },
		{ title: "Delete only some videos", paras: [`In the app you can delete any video, or all your photos in My media, without deleting your account. For anything else, email ${CONTACT_EMAIL} with the video titles.`] },
	];
	return { title: "Delete your account", intro: "How to delete your videomk account and data.", glance, sections };
}

export function getDelete(locale: Locale): LegalContent {
	return locale === "es" ? esDelete() : en();
}
