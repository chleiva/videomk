import type { LegalContent } from "./types";
import { CONTACT_EMAIL, SITE } from "../legal";

export function esSupport(): LegalContent {
	const glance = [`Escribe a ${CONTACT_EMAIL} para pedir ayuda, hacer solicitudes de privacidad, eliminar tu cuenta o denunciar un video.`, "Indica el correo de tu cuenta y, si es sobre un video, su título."];
	const sections = [
		{ title: "Pedir ayuda", paras: [`Escribe a ${CONTACT_EMAIL}. Normalmente respondemos en dos días hábiles.`, "Cuéntanos qué app o dispositivo usas, el correo de tu cuenta (no tu contraseña) y qué pasó. Si es sobre un video, añade su título."] },
		{ title: "Denunciar un video", paras: ["Si un video creado con videomk te parece dañino, ilegal o infractor, escríbenos con el asunto “Notice”, el título del video y qué está mal. Lo revisamos y lo retiramos si incumple nuestros Términos. Los avisos de derechos de autor deben seguir la sección 15 de los Términos."] },
		{ title: "Creación de videos en pausa o en espera, o una petición detenida por error", paras: [`Escribe a ${CONTACT_EMAIL} desde la dirección de tu cuenta. Una persona lo revisa y levanta la pausa o la espera si fue un error.`] },
		{ title: "Tus datos y tu cuenta", paras: [`Lee la Política de privacidad en ${SITE}/es/privacy y los Términos en ${SITE}/es/terms. Para eliminar tu cuenta y tus datos, consulta ${SITE}/es/delete-account. Para cualquier solicitud de privacidad (una copia de tus datos, corrección, oposición), escribe a ${CONTACT_EMAIL}.`] },
	];
	return { title: "Soporte", intro: "Cómo contactar con videomk.", glance, sections };
}
