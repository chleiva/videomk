import type { LegalContent, Locale } from "./types";
import { CONTACT_EMAIL, SITE } from "../legal";
import { esSupport } from "./support.es";

function en(): LegalContent {
	const glance = [`Email ${CONTACT_EMAIL} for help, privacy requests, account deletion or to report a video.`, "Please include the email address of your account and, for a video, its title."];
	const sections = [
		{ title: "Get help", paras: [`Write to ${CONTACT_EMAIL}. We usually reply within two working days.`, "Tell us which app or device you use, the email address of your account (not your password) and what happened. For a video, add its title."] },
		{ title: "Report a video", paras: ["If a video made with VideoMK seems harmful, unlawful or infringing, email us with the subject “Notice”, the video’s title and what is wrong. We review it and remove it if it breaks our Terms. Copyright notices should follow section 15 of the Terms."] },
		{ title: "Video creation paused or on hold, or a request stopped by mistake", paras: [`Email ${CONTACT_EMAIL} from your account address. A person looks at it and lifts the pause or hold if it was a mistake.`] },
		{ title: "Your data and your account", paras: [`Read the Privacy Policy at ${SITE}/privacy and the Terms at ${SITE}/terms. To delete your account and data, see ${SITE}/delete-account. For any privacy request (a copy of your data, correction, objection) email ${CONTACT_EMAIL}.`] },
	];
	return { title: "Support", intro: "How to contact VideoMK.", glance, sections };
}

export function getSupport(locale: Locale): LegalContent {
	return locale === "es" ? esSupport() : en();
}
