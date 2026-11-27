import type { LegalContent } from "./types";
import { CONTACT_EMAIL } from "../legal";

export function esDelete(): LegalContent {
	const glance = ["Lo más rápido es hacerlo en la app de iPhone o Android: Ajustes, Eliminar cuenta. El sitio web todavía no tiene un botón para eliminar: usa la vía del correo que se explica abajo.", "Si no puedes iniciar sesión, escríbenos desde el correo de tu cuenta y lo hacemos por ti.", "Al eliminar se borran tus videos, fotos, créditos e inicio de sesión. No se puede deshacer.", "Algunas copias desaparecen solas según su propio plazo (hasta 90 días): consulta \"Lo que puede permanecer un tiempo\"."];
	const sections = [
		{ title: "Eliminar tu cuenta en la app", bullets: [
			"Abre videomk, ve a Ajustes, luego a Eliminar cuenta, y confirma. Por tu seguridad, antes te pedimos que inicies sesión de nuevo.",
			"Eliminamos tus videos, narración y fotos, tu biblioteca Mi biblioteca, tu saldo e historial de créditos y el plan de cada video. No se puede deshacer, y los créditos que te queden se pierden.",
			"Tus datos se eliminan en pocos minutos. Tu inicio de sesión se desactiva de inmediato y se elimina por completo en una o dos horas aproximadamente; hasta entonces no puedes usarlo, y conviene esperar ese tiempo antes de registrarte de nuevo con el mismo correo.",
			"Si iniciaste sesión con Apple, la app también le pide a Apple que deje de compartir tu cuenta con videomk, y puedes comprobarlo en cualquier momento en Ajustes del iPhone, bajo tu nombre, Iniciar sesión con Apple. Si iniciaste sesión con Google, puedes quitar videomk en tu cuenta de Google, en Seguridad, Acceso de terceros."] },
		{ title: "Si no puedes iniciar sesión", bullets: [
			`Escribe a ${CONTACT_EMAIL} desde la dirección con la que inicias sesión en videomk, con el asunto “Eliminar mi cuenta de videomk”.`,
			"Si iniciaste sesión con Apple y elegiste Ocultar mi correo, escribe desde el correo de la cuenta que aparece en la app (Ajustes), porque no podemos encontrar tu cuenta a partir de la dirección de retransmisión privada de Apple.",
			"Podemos pedirte que confirmes que eres tú, por ejemplo respondiendo a un mensaje que enviemos a esa dirección. Terminamos en un plazo de 30 días y te lo confirmamos por correo."] },
		{ title: "Lo que puede permanecer un tiempo", paras: [
			"Algunas copias quedan fuera de nuestro control o se conservan durante un plazo fijo, y después desaparecen solas:",
		], bullets: [
			"Los registros del flujo de trabajo que AWS conserva de cada video (incluyen el texto de tu petición y las opciones) los elimina AWS 90 días después de que se creó el video. No podemos eliminarlos antes.",
			"Las copias de seguridad de la base de datos pueden conservar datos eliminados hasta 35 días.",
			"Los registros técnicos se eliminan a los 14 días. Contienen el identificador de tu cuenta, pero no tu correo.",
			"Si nuestro control de seguridad detuvo una petición tuya, se conserva un registro breve (tipo de motivo, hora, los primeros 160 caracteres y una huella de la petición) durante el resto de sus 90 días bajo una referencia codificada, no con los datos de tu cuenta.",
			"Si alguna vez la ley nos obliga a conservar registros de compras por motivos contables, se conservan solo esos, durante el tiempo que exija la ley. Las compras hechas a través de Apple o Google permanecen en sus registros; cancela cualquier suscripción con ellos.",
			"Los créditos gratuitos no se restituyen si te registras de nuevo: al eliminar tu cuenta se elimina tu saldo. Para garantizarlo, conservamos una huella irreversible y con sal de tu correo electrónico, de tu identidad de inicio de sesión de Google o Apple y de la clave de dispositivo de la app durante 2 años desde el día en que se concedieron los créditos gratuitos. No contiene datos de la cuenta ni puede convertirse de nuevo en ellos, y se usa únicamente para evitar que los créditos gratuitos se obtengan dos veces."] },
		{ title: "Eliminar solo algunos videos", paras: [`En la app puedes eliminar cualquier video, o todas tus fotos de Mi biblioteca, sin eliminar tu cuenta. Para cualquier otra cosa, escribe a ${CONTACT_EMAIL} con los títulos de los videos.`] },
	];
	return { title: "Eliminar tu cuenta", intro: "Cómo eliminar tu cuenta de videomk y tus datos.", glance, sections };
}
